"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md, commit 1f60c48). DEV WINDOW ONLY.
New strategy candidate 1: volatility-squeeze breakout, built for a small
account (small stop, large target).

4H bars resampled from 1H, 50 coins (15-coin basket + 35 unseen).
  squeeze   BB(20,2) width / close in the lowest 20% of its own trailing
            120 bars
  breakout  within 6 bars after a squeeze bar, close > previous 20-bar
            high (long) / < previous 20-bar low (short); first breakout
            per squeeze episode
  stop      midpoint of the previous 20-bar range
  exits     (a) fixed 3R target; (b) no target, chandelier trail at the
            best close since entry -/+ 3 x ATR(14 at entry), stop only
            tightens; max hold 180 bars
  costs     0.14% round trip; results in R
Control: the same breakout / stop / exits with no squeeze requirement
(first 20-bar breakout, 6-bar cooldown).
Pass: one exit variant with avgR > 0 AND > control in all 4 cells
(2020-23 / 2024-25 x 15-basket / 35-unseen).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, ROUND_TRIP_FRICTION
from dev_coin_personality import ORIGINAL, MAJORS, load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')
MAX_HOLD = 180


def to_4h(df):
    x = df.set_index('timestamp').resample('4h', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
    x['atr'] = compute_atr(x)
    mid = x['close'].rolling(20).mean()
    sd = x['close'].rolling(20).std()
    x['bbw'] = 4 * sd / x['close']
    x['squeeze'] = x['bbw'] <= x['bbw'].rolling(120).quantile(0.20)
    x['hh20'] = x['high'].shift(1).rolling(20).max()
    x['ll20'] = x['low'].shift(1).rolling(20).min()
    return x[x['timestamp'] < '2026-01-01'].reset_index(drop=True)


def run_exit(x, t, sgn, stop, mode):
    c, h, l, a = x['close'].values, x['high'].values, x['low'].values, x['atr'].values[t]
    entry = c[t]
    risk = sgn * (entry - stop) / entry
    if risk <= 0 or np.isnan(a):
        return None
    tp = entry + sgn * 3 * (entry * risk) if mode == 'fixed3R' else None
    best = entry
    end = min(t + 1 + MAX_HOLD, len(c))
    if t + 1 + MAX_HOLD > len(c):
        return None
    for j in range(t + 1, end):
        if (l[j] <= stop) if sgn > 0 else (h[j] >= stop):
            return (sgn * (stop - entry) / entry - ROUND_TRIP_FRICTION) / risk
        if tp is not None and ((h[j] >= tp) if sgn > 0 else (l[j] <= tp)):
            return (sgn * (tp - entry) / entry - ROUND_TRIP_FRICTION) / risk
        if mode == 'trail':
            best = max(best, c[j]) if sgn > 0 else min(best, c[j])
            trail = best - sgn * 3 * a
            stop = max(stop, trail) if sgn > 0 else min(stop, trail)
    return (sgn * (c[end - 1] - entry) / entry - ROUND_TRIP_FRICTION) / risk


def trades(x, coin, sample):
    c = x['close'].values
    sq = x['squeeze'].values
    hh, ll = x['hh20'].values, x['ll20'].values
    out = []
    last_sq, used_sq, last_ctrl = -10**9, -10**9, -10**9
    for t in range(140, len(x)):
        if sq[t - 1]:
            last_sq = t - 1
        if np.isnan(hh[t]):
            continue
        sgn = 1 if c[t] > hh[t] else (-1 if c[t] < ll[t] else 0)
        if sgn == 0:
            continue
        stop = (hh[t] + ll[t]) / 2
        kinds = []
        if t - last_ctrl > 6:
            kinds.append('control')
            last_ctrl = t
        if 1 <= t - last_sq <= 6 and last_sq > used_sq:
            kinds.append('squeeze')
            used_sq = last_sq
        for kind in kinds:
            for mode in ('fixed3R', 'trail'):
                r = run_exit(x, t, sgn, stop, mode)
                if r is not None:
                    out.append(dict(coin=coin, sample=sample, time=x['timestamp'].iloc[t], kind=kind, exit=mode,
                                    sgn=sgn, r=r))
    return out


def main():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    rows = []
    for b in basket + others:
        rows += trades(to_4h(load(b)), b, '15' if b in basket else '35')
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, '2020-23', '2024-25')

    def line(x):
        if len(x) == 0:
            return 'n=0'
        pf = x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.inf
        return f"n={len(x):5d} win={(x > 0).mean()*100:5.1f}% avgR={x.mean():+.3f} PF={pf:4.2f}"

    cells = [(p, s) for p in ('2020-23', '2024-25') for s in ('15', '35')]
    for mode in ('fixed3R', 'trail'):
        print('=' * 110 + f'\nEXIT {mode}')
        ok = True
        for p, s in cells:
            m = (d.exit == mode) & (d.period == p) & (d['sample'] == s)
            sq, ct = d[m & (d.kind == 'squeeze')].r, d[m & (d.kind == 'control')].r
            good = sq.mean() > 0 and sq.mean() > ct.mean()
            ok &= good
            print(f"  {p} {s}-coin  squeeze: {line(sq)}  | control: {line(ct)}  {'OK' if good else 'x'}")
        allsq = d[(d.exit == mode) & (d.kind == 'squeeze')].r
        print(f"  all squeeze: {line(allsq)}  longs avgR {d[(d.exit == mode) & (d.kind == 'squeeze') & (d.sgn == 1)].r.mean():+.3f}"
              f"  shorts avgR {d[(d.exit == mode) & (d.kind == 'squeeze') & (d.sgn == -1)].r.mean():+.3f}")
        print(f"  -> {mode} {'PASSES' if ok else 'FAILS'}")
    d.to_csv(os.path.join(ROOT, 'scripts', 'squeeze_breakout_trades.csv'), index=False)


if __name__ == '__main__':
    main()
