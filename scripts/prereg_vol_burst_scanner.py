"""
PRE-REGISTERED P6 (RESEARCH_FINDINGS.md 2026-11-08): the trade_check
"all green" combination tested as a complete system, so a scanner may (or
may not) be allowed to notify.

Event: 1H close whose volume ratio (vol / 20-bar mean) exceeds the coin's
frozen v7 cutoff (scripts/forward_frozen_cutoffs.json); direction = sign of
close - open; 8-bar cooldown per coin; entry at close.
F1 regime: BTC funding 30-day annualised as of the previous day > 10%.
F2 carry-aligned: coin's 7-day mean funding percentile among the 50 coins
(as of that day's 00:00 settlement) < 0.8 for longs, > 0.2 for shorts.
S1 = event & F1 & F2 ; S2 = event & F2.
Exit: SL 2 / TP 4 ATR(14), 168 h max, 0.14 % friction.
Pass (each): mean R > 0, bootstrap one-sided p < 0.025, both dev periods
> 0, 15- and 35-coin subsamples > 0. Holdout 2026 (passers; S1 has no
2026 sample because funding never exceeded 10 %) via --holdout.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGS, sys.argv = sys.argv[1:], sys.argv[:1]

from dev_volume_confirm import compute_atr  # noqa: E402
from dev_coin_personality import ORIGINAL, MAJORS, load  # noqa: E402
from dev_regime_switch import full_daily_panel, HOLD  # noqa: E402
from dev_momentum_partial_tp import simulate  # noqa: E402
from fetch_holdout_2026 import coins  # noqa: E402
from prereg_d1_regime import btc_ann30  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
SPLIT, DEV_END, HEND = pd.Timestamp('2024-01-01'), pd.Timestamp('2026-01-01'), pd.Timestamp('2026-10-01')
COOLDOWN, MAX_HOLD, N_BOOT, ALPHA = 8, 168, 10000, 0.025
GATE = 0.10


def funding_percentiles(funding):
    """Daily (00:00) cross-sectional percentile of each coin's trailing 7-day mean funding."""
    cols = {}
    for c, s in funding.items():
        s = s.sort_index()
        r = s.rolling(21, min_periods=15).mean()
        cols[c] = r.resample('1D').last().ffill(limit=3)
    f7 = pd.DataFrame(cols)
    return f7.rank(axis=1, pct=True)


def events(df, cut):
    df = df.sort_values('timestamp').reset_index(drop=True).copy()
    df['atr'] = compute_atr(df)
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    vr, o, c = df['vol_ratio'].values, df['open'].values, df['close'].values
    out, last = [], -10**9
    for i in range(200, len(df) - MAX_HOLD - 1):
        if i - last <= COOLDOWN or np.isnan(vr[i]) or vr[i] <= cut or c[i] == o[i]:
            continue
        out.append((i, 1 if c[i] > o[i] else -1))
        last = i
    return df, out


def build(frames, cut, ann, pct, basket):
    rows = []
    for b, df in frames.items():
        if b not in cut:
            continue
        df, ev = events(df, cut[b])
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp']
        for i, sgn in ev:
            t = ts.iloc[i]
            if np.isnan(atr[i]) or atr[i] <= 0:
                continue
            day = t.floor('D')
            a = ann.get(day - pd.Timedelta(days=1), np.nan)
            p = pct.at[day, b] if (day in pct.index and b in pct.columns) else np.nan
            if np.isnan(a) or np.isnan(p):
                continue
            rows.append(dict(coin=b, sample='15' if b in basket else '35', time=t, sgn=sgn, ann30=a, pct=p,
                             r=simulate(c, h, l, i, sgn, atr[i])))
        print(f'  {b}: {len(ev)} events', flush=True)
    d = pd.DataFrame(rows)
    d['F1'] = d.ann30 > GATE
    d['F2'] = np.where(d.sgn > 0, d.pct < 0.8, d.pct > 0.2)
    d['S1'] = d.F1 & d.F2
    d['S2'] = d.F2
    return d


def test(x, rng, alpha, label, need_split=True):
    r = x.r.values
    if len(r) < 30:
        print(f'  {label:28s} n={len(r)} too few')
        return False
    p = (rng.choice(r, (N_BOOT, len(r))).mean(1) <= 0).mean()
    t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    a, b = x[x.time < SPLIT].r, x[x.time >= SPLIT].r
    s15, s35 = x[x['sample'] == '15'].r, x[x['sample'] == '35'].r
    cons = (a.mean() > 0 and b.mean() > 0) if need_split else True
    ok = bool(r.mean() > 0 and p < alpha and cons and s15.mean() > 0 and s35.mean() > 0)
    print(f'  {label:28s} n={len(r):6d} meanR={r.mean():+.4f} win={(r>0).mean()*100:4.1f}% t={t:+.2f} p={p:.4f} | '
          f'20-23 {a.mean() if len(a) else np.nan:+.3f} (n={len(a)})  24-25 {b.mean() if len(b) else np.nan:+.3f} (n={len(b)}) | '
          f'15: {s15.mean() if len(s15) else np.nan:+.3f}  35: {s35.mean() if len(s35) else np.nan:+.3f}  -> {"PASS" if ok else "FAIL"}')
    return ok


def main():
    rng = np.random.default_rng(20261108)
    with open(os.path.join(S, 'forward_frozen_cutoffs.json')) as fh:
        cut = json.load(fh)
    _, funding = full_daily_panel()
    pct = funding_percentiles(funding)
    ann = btc_ann30()
    basket = set(ORIGINAL + MAJORS)
    if '--holdout' in ARGS:
        frames = {}
        for b in coins():
            p = os.path.join(HOLD, f'{b}_USDT_1h.csv')
            if os.path.exists(p):
                frames[b] = pd.read_csv(p, parse_dates=['timestamp'])
        d = build(frames, cut, ann, pct, basket)
        d = d[(d.time >= DEV_END) & (d.time < HEND)]
        d.to_csv(os.path.join(S, 'holdout_vol_burst_trades.csv'), index=False)
        print(f'\n2026: events {len(d)}, gate-on share {d.F1.mean()*100:.1f}%')
        for lab, m in (('all events', d.index == d.index), ('S1 event&F1&F2', d.S1), ('S2 event&F2', d.S2)):
            test(d[m], rng, 0.05, lab, need_split=False)
        for q, g in d.groupby(d.time.dt.quarter):
            print(f'    2026Q{q}: S2 n={int(g.S2.sum())} meanR={g[g.S2].r.mean():+.3f}   all n={len(g)} meanR={g.r.mean():+.3f}')
        return
    frames = {b: load(b) for b in coins()}
    frames = {b: f[f.timestamp < DEV_END] for b, f in frames.items()}
    d = build(frames, cut, ann, pct, basket)
    d.to_csv(os.path.join(S, 'vol_burst_trades.csv'), index=False)
    print(f'\nDEV events: {len(d)}  coins {d.coin.nunique()}  gate-on share {d.F1.mean()*100:.1f}%  F2 share {d.F2.mean()*100:.1f}%')
    print('decomposition (not judged):')
    test(d, rng, ALPHA, 'all events (no filter)')
    test(d[d.F1], rng, ALPHA, 'F1 only (regime on)')
    test(d[~d.F1], rng, ALPHA, 'regime OFF (contrast)')
    test(d[d.F2], rng, ALPHA, 'F2 only (carry aligned)')
    test(d[~d.F2], rng, ALPHA, 'against carry (contrast)')
    print('pre-registered systems:')
    s1 = test(d[d.S1], rng, ALPHA, 'S1 event&F1&F2')
    s2 = test(d[d.S2], rng, ALPHA, 'S2 event&F2')
    yrs = d[d.S1].groupby(d[d.S1].time.dt.year).size()
    print(f'  S1 signals per year: {yrs.to_dict()}  (per coin-year ~{yrs.mean()/50:.0f})')
    print(f'\nSUMMARY: S1 {"PASS" if s1 else "FAIL"}  S2 {"PASS" if s2 else "FAIL"}')


if __name__ == '__main__':
    main()
