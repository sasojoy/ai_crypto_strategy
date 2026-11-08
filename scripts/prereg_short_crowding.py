"""
PRE-REGISTERED TEST (written down and committed in RESEARCH_FINDINGS.md
before running, 2026-09-30). DEV WINDOW ONLY (< 2026-01-01).

Hypothesis H1 (found post hoc on the 15-coin basket in
dev_momentum_funding_crowding.py): v7 SHORT signals taken while shorts are
already crowded (the most-negative-funding tercile) do worse than the
other short signals.

Independent sample: the 35 universe coins NOT in the 15-coin basket.
Signal: v7 locked spec (1H close entry proxy, top volume tercile,
SL 2 / TP 4 ATR). Shorts only.
Crowding: -1 x mean of the last 3 settled funding rates known at the
trigger close. Terciles per coin, thresholds from that coin's 2020-23
shorts, frozen for the whole window.
Pass: T3 avgR < avgR of T1+T2, one-sided permutation p < 0.05 (labels
shuffled within coin, 10,000x), AND same direction in 2020-23 and 2024-25.
Only if it passes: effect of skipping T3 shorts on total R.
No re-tests with other definitions if it fails.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi
from dev_coin_personality import ORIGINAL, MAJORS
from dev_momentum_universe import load_universe_1h
from dev_momentum_pullback_entry import signals
from dev_momentum_partial_tp import simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND_DIR = os.path.join(ROOT, 'data', 'backtest_cache', 'funding_universe')
SPLIT = pd.Timestamp('2024-01-01')
N_PERM = 10000


def build():
    bases = sorted(f.split('_USDT_')[0] for f in os.listdir(FUND_DIR) if f.endswith('_funding.csv'))
    assert not set(bases) & set(ORIGINAL + MAJORS), 'sample must exclude the basket'
    rows = []
    for b in bases:
        df = load_universe_1h(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        f = pd.read_csv(os.path.join(FUND_DIR, f'{b}_USDT_funding.csv'))
        f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
        f['f24'] = f['funding_rate'].rolling(3).mean()
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        s = signals(df)
        s = s[s.sgn == -1].copy()
        s['close_time'] = ts[s['i']] + np.timedelta64(1, 'h')
        s = pd.merge_asof(s.sort_values('close_time'), f[['timestamp', 'f24']].sort_values('timestamp'),
                          left_on='close_time', right_on='timestamp', direction='backward')
        for r in s.itertuples():
            if np.isnan(r.f24):
                continue
            rows.append(dict(coin=b, time=pd.Timestamp(ts[r.i]), crowd=-r.f24, r=simulate(c, h, l, r.i, -1, atr[r.i])))
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, 'disc', 'conf')
    d['T3'] = False
    for coin, g in d.groupby('coin'):
        ref = g.loc[g.period == 'disc', 'crowd']
        if len(ref) < 6:
            d.loc[g.index, 'T3'] = np.nan
            continue
        d.loc[g.index, 'T3'] = g['crowd'] > ref.quantile(2 / 3)
    return d.dropna(subset=['T3']).assign(T3=lambda x: x['T3'].astype(bool)), bases


def gap(d):
    return d.loc[d.T3, 'r'].mean() - d.loc[~d.T3, 'r'].mean()


def main():
    d, bases = build()
    print(f"coins: {d.coin.nunique()} of {len(bases)} (need >= 6 short signals in 2020-23)   short signals: {len(d)}")
    for p, m in (('all', slice(None)), ('2020-23', d.period == 'disc'), ('2024-25', d.period == 'conf')):
        x = d[m]
        print(f"  {p:8s} T3 (shorts crowded): n={x.T3.sum():4d} avgR={x.loc[x.T3, 'r'].mean():+.3f}   "
              f"T1+T2: n={(~x.T3).sum():4d} avgR={x.loc[~x.T3, 'r'].mean():+.3f}   gap={gap(x):+.3f}")

    rng = np.random.default_rng(2026)
    real = gap(d)
    perm = np.empty(N_PERM)
    groups = [g.index.values for _, g in d.groupby('coin')]
    labels = d['T3'].values.copy()
    for k in range(N_PERM):
        shuffled = labels.copy()
        for idx in groups:
            pos = d.index.get_indexer(idx)
            shuffled[pos] = rng.permutation(shuffled[pos])
        perm[k] = d['r'].values[shuffled].mean() - d['r'].values[~shuffled].mean()
    p = (perm <= real).mean()
    same_dir = gap(d[d.period == 'disc']) < 0 and gap(d[d.period == 'conf']) < 0
    passed = p < 0.05 and same_dir
    print(f"\n  one-sided permutation p = {p:.4f}   same direction in both periods: {same_dir}")
    print(f"  H1 {'PASSES' if passed else 'FAILS'}")
    if passed:
        for pl, m in (('2020-23', d.period == 'disc'), ('2024-25', d.period == 'conf')):
            x = d[m]
            print(f"  skip T3 shorts, {pl}: total short R {x.r.sum():+.1f} -> {x.loc[~x.T3, 'r'].sum():+.1f}")
        by = d.groupby('coin').apply(lambda g: -g.loc[g.T3, 'r'].sum())
        print(f"  coins where skipping helps: {(by > 0).sum()}/{len(by)}")


if __name__ == '__main__':
    main()
