"""
Hourly volume-burst scanner (P6, RESEARCH_FINDINGS.md 2026-11-08).

Runs the pre-registered S1 system live on public data and NOTIFIES ONLY
when S1 is true; everything else is logged silently as the forward sample.
  event : last closed 1H bar, volume / 20-bar mean > the coin's frozen cutoff
          (scripts/forward_frozen_cutoffs.json), direction = sign(close-open)
  F1    : BTC funding 30-day annualised (last 90 settlements) > 10%
  F2    : coin's 7-day mean funding percentile among the 50 research coins
          < 0.8 for longs / > 0.2 for shorts
  S1    : event & F1 & F2  -> Telegram, with SL 2x / TP 4x ATR(14) frame
Dev result (prereg_vol_burst_scanner.py): S1 n=12,134, +0.054R/trade,
t=4.1, both periods and both coin sets > 0. S1 has NO 2026 sample (funding
never exceeded 10% in 2026) -- this log IS its out-of-sample test.
S2 (event & F2 without the regime filter) FAILED dev and is -0.08R in 2026,
so nothing is sent while the regime is off.

Files: data/forward/vol_burst_signals.csv (all events with flags),
       data/forward/vol_burst_last_run.txt (heartbeat for watchdog.py).
--report evaluates logged signals' outcomes (SL/TP/168h) and prints S1 vs
all-event mean R so far.
"""
import csv
import os
import sys
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGS, sys.argv = sys.argv[1:], sys.argv[:1]
from fetch_holdout_2026 import coins  # noqa: E402
from src.notifier import send_telegram_msg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
OUT = os.path.join(ROOT, 'data', 'forward')
LOG = os.path.join(OUT, 'vol_burst_signals.csv')
HEART = os.path.join(OUT, 'vol_burst_last_run.txt')
GATE, MAX_HOLD, COST = 0.10, 168, 0.0014
COLS = ['bar_time', 'coin', 'direction', 'vol_ratio', 'cutoff', 'ann30', 'F1', 'pct', 'F2', 'S1', 'price', 'atr', 'sl', 'tp', 'logged_utc']


def ex_public():
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    return ex


def tradable(ex, bases):
    return [b for b in bases if f'{b}/USDT:USDT' in ex.markets and ex.markets[f'{b}/USDT:USDT'].get('active', True)]


def ann30(ex):
    h = ex.fetch_funding_rate_history('BTC/USDT:USDT', limit=90)
    return float(np.mean([x['fundingRate'] for x in h]) * 3 * 365)


def funding_pct(ex, bases):
    f = {}
    for b in bases:
        try:
            h = ex.fetch_funding_rate_history(f'{b}/USDT:USDT', limit=21)
            if h:
                f[b] = float(np.mean([x['fundingRate'] for x in h]))
        except Exception:
            pass
    s = pd.Series(f)
    return s.rank(pct=True)


def last_closed_bar(ex, b):
    o = ex.fetch_ohlcv(f'{b}/USDT:USDT', '1h', limit=60)
    df = pd.DataFrame(o, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).iloc[:-1]
    pc = df['close'].shift(1)
    tr = pd.concat([df['high'] - df['low'], (df['high'] - pc).abs(), (df['low'] - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    vr = df['volume'].iloc[-1] / df['volume'].iloc[-20:].mean()
    r = df.iloc[-1]
    return pd.Timestamp(int(r.ts), unit='ms', tz='UTC'), float(r.open), float(r.close), float(vr), float(atr)


def already_logged():
    if not os.path.exists(LOG):
        return set()
    d = pd.read_csv(LOG, usecols=['bar_time', 'coin'])
    return set(zip(d.bar_time, d.coin))


def scan():
    os.makedirs(OUT, exist_ok=True)
    ex = ex_public()
    import json
    with open(os.path.join(S, 'forward_frozen_cutoffs.json')) as fh:
        cut = json.load(fh)
    bases = [b for b in tradable(ex, coins()) if b in cut]
    g = ann30(ex)
    f1 = g > GATE
    pct = funding_pct(ex, bases)
    seen = already_logged()
    rows, alerts = [], []
    for b in bases:
        try:
            t, o, c, vr, a = last_closed_bar(ex, b)
        except Exception as e:  # noqa: BLE001
            print(f'{b}: fetch failed {e}')
            continue
        key = (t.strftime('%Y-%m-%d %H:%M'), b)
        if vr <= cut[b] or c == o or np.isnan(a) or key in seen:
            continue
        sgn = 1 if c > o else -1
        p = float(pct.get(b, np.nan))
        f2 = bool((p < 0.8) if sgn > 0 else (p > 0.2)) if not np.isnan(p) else False
        s1 = bool(f1 and f2)
        sl, tp = c - sgn * 2 * a, c + sgn * 4 * a
        rows.append(dict(bar_time=key[0], coin=b, direction='long' if sgn > 0 else 'short', vol_ratio=round(vr, 3),
                         cutoff=round(cut[b], 3), ann30=round(g, 4), F1=f1, pct=round(p, 3), F2=f2, S1=s1,
                         price=c, atr=a, sl=sl, tp=tp, logged_utc=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')))
        if s1:
            alerts.append(f'{b} {"多" if sgn > 0 else "空"} @ {c:.6g}  SL {sl:.6g}  TP {tp:.6g}  量比 {vr:.1f}  費率百分位 {p*100:.0f}')
    new = not os.path.exists(LOG)
    with open(LOG, 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(HEART, 'w') as fh:
        fh.write(datetime.now(timezone.utc).isoformat())
    print(f'ann30 {g*100:.1f}% gate {"ON" if f1 else "off"}; {len(bases)} coins; {len(rows)} new events; {len(alerts)} S1 alerts')
    if alerts:
        msg = (f'📣 量能爆發 S1 訊號（BTC 費率年化 {g*100:.1f}% > 10%）\n' + '\n'.join(alerts) +
               '\n框架：SL 2×／TP 4×ATR、最長 7 天，抱到出場不干預。\n'
               '依據：開發區 12,134 筆 +0.054R（兩段、15/35 幣皆正）；2026 無樣本，這是它的首次實測。')
        send_telegram_msg(msg)


def report():
    if not os.path.exists(LOG):
        print('no signals logged yet')
        return
    d = pd.read_csv(LOG, parse_dates=['bar_time'])
    ex = ex_public()
    out = []
    for b, g in d.groupby('coin'):
        since = int(pd.Timestamp(g.bar_time.min(), tz='UTC').timestamp() * 1000)
        o = ex.fetch_ohlcv(f'{b}/USDT:USDT', '1h', since=since, limit=1500)
        df = pd.DataFrame(o, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['t'] = pd.to_datetime(df.ts, unit='ms')
        df = df.iloc[:-1]
        for r in g.itertuples():
            after = df[df.t > r.bar_time].head(MAX_HOLD)
            if len(after) == 0:
                continue
            sgn = 1 if r.direction == 'long' else -1
            px, status = None, 'OPEN'
            for x in after.itertuples():
                if (x.low <= r.sl) if sgn > 0 else (x.high >= r.sl):
                    px, status = r.sl, 'SL'
                    break
                if (x.high >= r.tp) if sgn > 0 else (x.low <= r.tp):
                    px, status = r.tp, 'TP'
                    break
            if status == 'OPEN' and len(after) >= MAX_HOLD:
                px, status = after.close.iloc[-1], 'TIME'
            if px is None:
                continue
            R = (sgn * (px - r.price) / r.price - COST) / (2 * r.atr / r.price)
            out.append(dict(coin=b, bar_time=r.bar_time, direction=r.direction, S1=r.S1, F1=r.F1, F2=r.F2, status=status, r=R))
    x = pd.DataFrame(out)
    if x.empty:
        print('no closed signals yet')
        return
    x.to_csv(os.path.join(OUT, 'vol_burst_forward_closed.csv'), index=False)
    for lab, m in (('all events', x.index == x.index), ('S1', x.S1), ('F2 only (regime off)', x.F2 & ~x.F1)):
        g = x[m]
        if len(g):
            print(f'{lab:22s} n={len(g):5d} meanR={g.r.mean():+.3f} win={(g.r>0).mean()*100:4.1f}%')
        else:
            print(f'{lab:22s} n=0')


if __name__ == '__main__':
    report() if '--report' in ARGS else scan()
