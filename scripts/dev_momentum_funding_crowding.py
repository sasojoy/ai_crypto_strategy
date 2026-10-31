"""
DEV-WINDOW ONLY (< 2026-01-01). Funding-rate crowding as a filter / risk
scaler for the v7 signal (optimization track, 2026-09-30).

Idea: when a long signal fires while longs are already paying high funding
(crowded), the move may be late and prone to a squeeze; mirror for shorts.
Caveat recorded before running: test #9 found extreme funding leans toward
CONTINUATION at the 1H scale, so the effect could go the other way -- both
directions are reported, and nothing is acted on unless consistent.

Pre-registered:
  Crowding = trade direction x mean of the last 3 SETTLED funding rates
    (24h) known at the trigger bar's close (secondary: the last one only).
    Positive = the crowd is already on our side.
  Terciles per coin, thresholds fixed from that coin's 2020-23 signals,
    applied unchanged to 2024-25.
  Rule: only if the most-crowded tercile has the lowest avgR in BOTH
    periods, test (a) skipping it and (b) half risk on it; judged on total
    R per period and coins improved. Symmetric check for the least-crowded
    tercile (in case crowding helps).

Basket: 15 coins; v7 locked spec, 1H close trigger, SL 2 / TP 4 ATR.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi
from dev_coin_personality import ORIGINAL, MAJORS, load
from dev_momentum_pullback_entry import signals
from dev_momentum_partial_tp import simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND_DIR = os.path.join(ROOT, 'data', 'backtest_cache', 'funding_basket')
SPLIT = pd.Timestamp('2024-01-01')


def build():
    rows = []
    for b in ORIGINAL + MAJORS:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        f = pd.read_csv(os.path.join(FUND_DIR, f'{b}_USDT_funding.csv'))
        f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
        f['f24'] = f['funding_rate'].rolling(3).mean()
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp']
        s = signals(df).copy()
        s['close_time'] = ts.values[s['i']] + np.timedelta64(1, 'h')
        s = pd.merge_asof(s.sort_values('close_time'), f[['timestamp', 'funding_rate', 'f24']].sort_values('timestamp'),
                          left_on='close_time', right_on='timestamp', direction='backward')
        for r in s.itertuples():
            if np.isnan(r.f24):
                continue
            rows.append(dict(coin=b, time=pd.Timestamp(ts.values[r.i]), sgn=r.sgn,
                             crowd24=r.sgn * r.f24, crowd_last=r.sgn * r.funding_rate,
                             r=simulate(c, h, l, r.i, r.sgn, atr[r.i])))
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, 'disc', 'conf')
    return d


def disc_terciles(d, col):
    out = pd.Series(index=d.index, dtype=object)
    for coin, g in d.groupby('coin'):
        ref = g.loc[g.period == 'disc', col]
        lo, hi = ref.quantile(1 / 3), ref.quantile(2 / 3)
        out.loc[g.index] = np.where(g[col] <= lo, 'T1_against', np.where(g[col] <= hi, 'T2_mid', 'T3_crowded'))
    return out


def main():
    d = build()
    print(f"signals with funding: {len(d)}  (2020-23 {int((d.period == 'disc').sum())}, 2024-25 {int((d.period == 'conf').sum())})")
    print(f"median funding per 8h: {d.crowd24.abs().median()*100:.4f}%\n")
    for col in ('crowd24', 'crowd_last'):
        d['t'] = disc_terciles(d, col)
        print('=' * 100 + f'\n{col}: avgR by crowding tercile (T1 = crowd against us, T3 = crowd already on our side)')
        tab = {}
        for p in ('disc', 'conf'):
            g = d[d.period == p].groupby('t').r
            tab[p] = g.mean()
            print(f"  {p}: " + '   '.join(f"{t}: n={n:4d} win={w*100:4.1f}% avgR={m:+.3f}"
                                         for t, n, w, m in zip(g.mean().index, g.size(), g.apply(lambda x: (x > 0).mean()), g.mean())))
        for p in ('disc', 'conf'):
            for sgn, name in ((1, 'long'), (-1, 'short')):
                g = d[(d.period == p) & (d.sgn == sgn)].groupby('t').r.mean()
                print(f"    {p} {name:5s}: " + '  '.join(f"{t}={v:+.3f}" for t, v in g.items()))
        crowded_worst = all(tab[p].idxmin() == 'T3_crowded' for p in ('disc', 'conf'))
        against_worst = all(tab[p].idxmin() == 'T1_against' for p in ('disc', 'conf'))
        print(f"  most-crowded worst in both periods: {crowded_worst}   least-crowded worst in both: {against_worst}")
        target = 'T3_crowded' if crowded_worst else ('T1_against' if against_worst else None)
        if target is None:
            print('  -> pre-registered rule not met; no filter tested for this definition.\n')
            continue
        print(f'  -> testing skip / half risk on {target}')
        for label, w in (('baseline', 1.0), (f'skip {target}', 0.0), (f'half risk {target}', 0.5)):
            wt = np.where(d.t == target, w, 1.0)
            cells = []
            for p in ('disc', 'conf'):
                m = d.period == p
                cells.append(f"{p}: totalR={(d.r * wt)[m].sum():+7.1f}")
            by = pd.Series(d.r * wt).groupby(d.coin).sum() - d.groupby('coin').r.sum()
            print(f"    {label:22s} " + ' | '.join(cells) + (f"   coins better {(by > 0).sum()}/15" if w != 1.0 else ''))
        print()


if __name__ == '__main__':
    main()
