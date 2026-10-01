"""
FORWARD TRACKER for the strategy switcher (pre-registered 2026-10-01, see
RESEARCH_FINDINGS.md). Frozen rules -- do not edit:

  streams  XSM7, XSR7, XSM28, XSR28 (cross-sectional momentum / reversal,
           50 coins, weekly, prereg_xs_momentum.py rules) and V7, BRK4H
           (weekly sum of R from the two frozen forward trackers)
  history  scripts/regime_switch_raw_frozen.csv (weeks up to 2026-09-27),
           forward weeks appended from 2026-10-04 (holding Oct 5 -> Oct 12)
  normalize  each stream x 1% / its trailing 26-week std, lagged one week
  rule     POSEW: equal weight across streams whose trailing-L-week mean
           of normalized returns is > 0 (else cash); L = 30 and L = 39
A week counts once it is FINAL: the cross-sectional week has closed and no
V7/BRK4H trade entered that week is still open. Interim reports only; the
first look at a verdict is after 52 final forward weeks (Sharpe > 0).

Run after forward_tracker.py and brk4h.py forward (forward_weekly_report.py
does this).
"""
import os
import sys
import time

import ccxt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_holdout_2026 import coins
from prereg_xs_momentum import weekly_inputs, backtest
from dev_regime_switch import normalize, week_of
from forward_tracker import OUT as FWD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = os.path.join(ROOT, 'scripts', 'regime_switch_raw_frozen.csv')
FIRST_WEEK = pd.Timestamp('2026-10-04')
LS = (30, 39)


def forward_xs():
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    closes, funding = {}, {}
    for b in coins():
        h = pd.read_csv(os.path.join(FWD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
        full = h.groupby(h['timestamp'].dt.floor('D')).size()
        d = h.set_index('timestamp')['close'].resample('1D').last()
        closes[b] = d[full.reindex(d.index).fillna(0) == 24]
        rows, since = [], ex.parse8601('2026-08-01T00:00:00Z')
        while since < ex.milliseconds():
            fr = ex.fetch_funding_rate_history(f'{b}/USDT:USDT', since=since, limit=1000)
            if not fr:
                break
            rows += [(x['timestamp'], x['fundingRate']) for x in fr]
            if fr[-1]['timestamp'] + 1 <= since:
                break
            since = fr[-1]['timestamp'] + 1
        f = pd.DataFrame(rows, columns=['timestamp', 'funding_rate']).drop_duplicates('timestamp')
        f['timestamp'] = pd.to_datetime(f['timestamp'], unit='ms')
        funding[b] = f.set_index('timestamp')['funding_rate']
        time.sleep(0.1)
    px = pd.DataFrame(closes)
    out = {}
    for lb in (7, 28):
        weeks = [w for w in weekly_inputs(px, funding, lb) if w[0] >= FIRST_WEEK]
        out[f'XSM{lb}'] = backtest(weeks, list(px.columns), lambda sc: list(sc.sort_values().index))
        out[f'XSR{lb}'] = backtest(weeks, list(px.columns), lambda sc: list(sc.sort_values(ascending=False).index))
    return out


def forward_trades(csv):
    d = pd.read_csv(os.path.join(FWD, csv), parse_dates=['time'])
    d['week'] = d.time.map(week_of)
    d = d[d.week >= FIRST_WEEK]
    closed = d[d.status != 'OPEN'].groupby('week').r.sum()
    open_weeks = set(d.loc[d.status == 'OPEN', 'week'])
    return closed, open_weeks


def run():
    hist = pd.read_csv(FROZEN, index_col=0, parse_dates=True)
    hist = hist[hist.index < FIRST_WEEK]
    xs = forward_xs()
    v7, v7_open = forward_trades('forward_trades.csv')
    brk, brk_open = forward_trades('forward_trades_brk4h.csv')
    xs_weeks = sorted(set().union(*[s.index for s in xs.values()]))
    fwd = pd.DataFrame(index=pd.DatetimeIndex(xs_weeks, name=hist.index.name))
    for k, s in xs.items():
        fwd[k] = s
    fwd['V7'] = v7.reindex(fwd.index).fillna(0.0)
    fwd['BRK4H'] = brk.reindex(fwd.index).fillna(0.0)
    final = [w for w in fwd.index if w not in v7_open and w not in brk_open]
    raw = pd.concat([hist, fwd[hist.columns]]).sort_index()
    streams = pd.DataFrame({k: normalize(raw[k]) for k in raw.columns}).fillna(0.0)

    lines = []
    for L in LS:
        trail = streams.rolling(L).mean().shift(1)
        pos = trail > 0
        r = ((streams * pos).sum(axis=1) / pos.sum(axis=1).replace(0, np.nan)).fillna(0.0)
        fr = r[r.index.isin(final)]
        line = f"L={L}: 前瞻已確定 {len(fr)} 週，累計 {fr.sum()*100:+.2f}%（每週目標波動1%）"
        if len(fr) >= 4 and fr.std() > 0:
            line += f"，Sharpe {fr.mean() / fr.std() * np.sqrt(52):+.2f}"
        nxt = streams.rolling(L).mean().iloc[-1]
        holding = [k for k in streams.columns if nxt[k] > 0]
        line += f"\n    下週持有：{'、'.join(holding) if holding else '空手'}"
        lines.append(line)
    pend = len(fwd) - len(final)
    msg = '\n'.join(lines) + (f"\n  （另有 {pend} 週因交易未結束尚未確定）" if pend else '')
    print(msg)
    return msg


if __name__ == '__main__':
    run()
