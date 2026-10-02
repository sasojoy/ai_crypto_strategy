"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md, commit 17d5d27).
Does open interest rising during the v7 trigger hour (new money) mark better
trades than open interest falling (short covering / long liquidation)?

  dOI = OI at the trigger bar's close / OI at its open - 1 (5-minute
        snapshots from data.binance.vision metrics, nearest at or before,
        must be within 15 minutes)
  groups: dOI > 0 vs dOI <= 0 (terciles descriptive only)
  v7 signal: 1H close-entry proxy, coin's top volume tercile,
             SL 2 / TP 4 ATR, 168h, 0.14% costs
  periods: 2022-23 / 2024-25 / 2026 (Jan-Sep)
Pass: rising-OI avgR > falling-OI avgR in all 3 periods AND within-coin
permutation one-sided p < 0.05 on the pooled sample.

  python scripts/prereg_oi_filter.py basket   (stage 1, 15-coin basket)
  python scripts/prereg_oi_filter.py others   (stage 2, 35 unseen coins; only if stage 1 passes)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi
from dev_coin_personality import ORIGINAL, MAJORS
from fetch_holdout_2026 import coins
from prereg_three import load_full
from dev_momentum_pullback_entry import signals
from dev_momentum_partial_tp import simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MET = os.path.join(ROOT, 'data', 'backtest_cache', 'metrics')
N_PERM = 10000


def build(bases):
    rows = []
    for b in bases:
        path = os.path.join(MET, f'{b}USDT.csv')
        if not os.path.exists(path):
            print(f'  {b}: no metrics file, skipped')
            continue
        m = pd.read_csv(path, usecols=['create_time', 'sum_open_interest'])
        m['create_time'] = pd.to_datetime(m['create_time'])
        m = m.dropna().drop_duplicates('create_time').sort_values('create_time')
        df = load_full(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        sig = signals(df).copy()
        sig['t_open'] = ts[sig['i']]
        sig = sig[sig['t_open'] >= np.datetime64('2022-01-01')]
        sig['t_close'] = sig['t_open'] + np.timedelta64(1, 'h')
        for col in ('t_open', 't_close'):
            sig = pd.merge_asof(sig.sort_values(col), m.rename(columns={'create_time': f'{col}_m', 'sum_open_interest': f'oi_{col}'}),
                                left_on=col, right_on=f'{col}_m', direction='backward',
                                tolerance=pd.Timedelta(minutes=15))
        sig = sig.dropna(subset=['oi_t_open', 'oi_t_close'])
        for s in sig.itertuples():
            rows.append(dict(coin=b, time=pd.Timestamp(s.t_open), sgn=s.sgn,
                             doi=s.oi_t_close / s.oi_t_open - 1, r=simulate(c, h, l, s.i, s.sgn, atr[s.i])))
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < pd.Timestamp('2024-01-01'), '2022-23',
                           np.where(d.time < pd.Timestamp('2026-01-01'), '2024-25', '2026'))
    d['rising'] = d['doi'] > 0
    return d


def main():
    stage = sys.argv[1]
    bases = ORIGINAL + MAJORS if stage == 'basket' else [c for c in coins() if c not in ORIGINAL + MAJORS]
    d = build(bases)
    print(f"{stage}: {len(d)} signals on {d.coin.nunique()} coins, OI rising in {d.rising.mean()*100:.1f}%")
    ok = True
    for p, g in d.groupby('period'):
        up, dn = g[g.rising].r, g[~g.rising].r
        ok &= up.mean() > dn.mean()
        print(f"  {p}: OI rising n={len(up):4d} win={(up > 0).mean()*100:5.1f}% avgR={up.mean():+.3f}   "
              f"OI falling n={len(dn):4d} win={(dn > 0).mean()*100:5.1f}% avgR={dn.mean():+.3f}")
    for side, zh in ((1, 'longs'), (-1, 'shorts')):
        g = d[d.sgn == side]
        print(f"  ({zh}: rising {g[g.rising].r.mean():+.3f} vs falling {g[~g.rising].r.mean():+.3f})")
    terc = d.groupby('coin')['doi'].transform(lambda x: pd.qcut(x.rank(method='first'), 3, labels=['T1_down', 'T2', 'T3_up']))
    print('  terciles of dOI (descriptive): ' + '  '.join(f"{t}: {g.r.mean():+.3f} (n={len(g)})" for t, g in d.groupby(terc, observed=True)))

    rng = np.random.default_rng(17)
    real = d.loc[d.rising, 'r'].mean() - d.loc[~d.rising, 'r'].mean()
    r, lab = d['r'].values, d['rising'].values
    idx = [np.flatnonzero(d['coin'].values == c) for c in d['coin'].unique()]
    hits = 0
    for _ in range(N_PERM):
        sh = lab.copy()
        for ix in idx:
            sh[ix] = rng.permutation(sh[ix])
        hits += (r[sh].mean() - r[~sh].mean()) >= real
    p = hits / N_PERM
    print(f"\n  gap (rising - falling) {real:+.3f}R, permutation p = {p:.4f}; all 3 periods rising > falling: {ok}")
    print(f"  OI FILTER ({stage}) {'PASSES' if (ok and p < 0.05) else 'FAILS'}")


if __name__ == '__main__':
    main()
