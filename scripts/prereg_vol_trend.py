"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md, commit 2effc3d). DEV WINDOW ONLY
(< 2026-01-01). Two hypotheses suggested by the descriptive 2026 regime
study (dev_regime_2026.py):

  H_vol    v7 signals fired while the coin is QUIET relative to its own
           past year do worse. vol_rel = (1H ATR / price) / its trailing
           365-day median (causal, >= 180 days of history). Bad group =
           bottom tercile per coin, thresholds from 2020-23, frozen.
  H_trend  v7 signals AGAINST BTC's 30-day trend do worse. align =
           direction x BTC 720-bar return. Bad group = align < 0.

Sample: 50 coins (15-coin basket + 35 unseen universe coins). v7 locked
spec, 1H close entry proxy, SL 2 / TP 4 ATR, 0.14% friction.
Pass (each hypothesis separately): bad-group avgR < rest; within-coin
permutation (10,000x) one-sided p < 0.025 (Bonferroni for 2); same
direction in 2020-23 and 2024-25; same direction in the 15-coin and 35-coin
subsamples. Only then: 0.5x risk on the bad group, renormalized over all
signals (mean risk 1), per period x subsample.
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
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')
N_PERM = 10000
ALPHA = 0.025


def build():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    btc = load('BTC')
    btc_ret30 = btc.set_index('timestamp')['close'].pct_change(720)
    rows = []
    for b in basket + others:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        atr_pct = df['atr'] / df['close']
        df['vol_rel'] = atr_pct / atr_pct.rolling(365 * 24, min_periods=180 * 24).median()
        df['btc30'] = btc_ret30.reindex(df['timestamp']).values
        c, h, l, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        for s in signals(df).itertuples():
            vr, b30 = df['vol_rel'].iloc[s.i], df['btc30'].iloc[s.i]
            if np.isnan(vr) or np.isnan(b30):
                continue
            rows.append(dict(coin=b, sample='15' if b in basket else '35', time=df['timestamp'].iloc[s.i],
                             sgn=s.sgn, vol_rel=vr, align=s.sgn * b30, r=simulate(c, h, l, s.i, s.sgn, atr[s.i])))
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, 'disc', 'conf')
    d['bad_vol'] = False
    for coin, g in d.groupby('coin'):
        cut = g.loc[g.period == 'disc', 'vol_rel'].quantile(1 / 3)
        d.loc[g.index, 'bad_vol'] = g['vol_rel'] <= cut
    d['bad_trend'] = d['align'] < 0
    return d


def gap(x, col):
    return x.loc[x[col], 'r'].mean() - x.loc[~x[col], 'r'].mean()


def perm_p(d, col, rng):
    real = gap(d, col)
    r = d['r'].values
    lab = d[col].values
    idx = [np.flatnonzero(d['coin'].values == c) for c in d['coin'].unique()]
    worse = 0
    for _ in range(N_PERM):
        sh = lab.copy()
        for ix in idx:
            sh[ix] = rng.permutation(sh[ix])
        worse += (r[sh].mean() - r[~sh].mean()) <= real
    return worse / N_PERM


def main():
    d = build()
    rng = np.random.default_rng(2026)
    print(f"signals: {len(d)} on {d.coin.nunique()} coins (15-basket {int((d['sample'] == '15').sum())}, 35-unseen {int((d['sample'] == '35').sum())})")
    for col, name in (('bad_vol', 'H_vol   (quiet vs own past year)'), ('bad_trend', 'H_trend (against BTC 30d trend)')):
        print('\n' + '=' * 110 + f'\n{name}: bad group share {d[col].mean()*100:.1f}%')
        cells = {}
        for lab, m in (('all', slice(None)), ('2020-23', d.period == 'disc'), ('2024-25', d.period == 'conf'),
                       ('15-basket', d['sample'] == '15'), ('35-unseen', d['sample'] == '35')):
            x = d[m]
            cells[lab] = gap(x, col)
            print(f"  {lab:10s} bad n={int(x[col].sum()):5d} avgR={x.loc[x[col], 'r'].mean():+.3f}   "
                  f"rest n={int((~x[col]).sum()):5d} avgR={x.loc[~x[col], 'r'].mean():+.3f}   gap={cells[lab]:+.3f}")
        for lab, sub in (('long', d[d.sgn == 1]), ('short', d[d.sgn == -1])):
            print(f"  ({lab}s: gap {gap(sub, col):+.3f})")
        p = perm_p(d, col, rng)
        consistent = all(cells[k] < 0 for k in ('all', '2020-23', '2024-25', '15-basket', '35-unseen'))
        passed = p < ALPHA and consistent
        print(f"  permutation p = {p:.4f} (need < {ALPHA})   same direction in both periods and both subsamples: {consistent}")
        print(f"  {name.split()[0]} {'PASSES' if passed else 'FAILS'}")
        if passed:
            for per in ('disc', 'conf'):
                for smp in ('15', '35'):
                    x = d[(d.period == per) & (d['sample'] == smp)]
                    w = np.where(x[col], 0.5, 1.0)
                    new = (x.r * w).sum() / w.mean()
                    print(f"    reallocation {per} {smp}-coin: {x.r.sum():+8.1f}R -> {new:+8.1f}R")


if __name__ == '__main__':
    main()
