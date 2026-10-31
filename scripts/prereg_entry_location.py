"""
PRE-REGISTERED DIAGNOSTIC (RESEARCH_FINDINGS.md, 2026-10-31, "v7 常在最後一漲
／最後一跌進場"). DEV WINDOW ONLY (< 2026-01-01). Not a rule change: nothing
here touches live_v7 / forward_tracker regardless of outcome.

Population: v7 close-entry proxy, 50 coins (15-coin basket + 35 unseen),
dev_momentum_pullback_entry.signals (RSI cross + per-coin top-tercile
volume), R from dev_momentum_partial_tp.simulate (SL 2 / TP 4 ATR, 168 h,
0.14% friction). Same population as the 2026-10-02 next-bar study.

Features at the entry bar i (window includes i), measured in the trade
direction so "large = the move has already run far":
  D1 runup24_atr  long: (close - min low[i-23..i]) / ATR_i ; short mirrored
  D2 pos168       long: (close - min low[i-167..i]) / (max high - min low) ; short mirrored
  D3 age24        long: bars since the window-24 low ; short: since the high

Test (each feature): pooled-dev quintiles (rank-based), statistic = mean R
in Q5 minus mean R in Q1, one-sided within-coin permutation (10,000x,
quintile labels shuffled inside each coin), alpha = 0.05/3. Pass also
requires the same sign in 2020-23 vs 2024-25 and in the 15 vs 35 coin
subsamples. Quintile cut points are saved (frozen) for the 2026 one-shot.
"""
import json
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
DEV_END = pd.Timestamp('2026-01-01')
N_PERM = 10000
FEATURES = ['runup24_atr', 'pos168', 'age24']
ALPHA = 0.05 / len(FEATURES)
CUTS_PATH = os.path.join(ROOT, 'scripts', 'entry_location_cuts.json')
OUT_CSV = os.path.join(ROOT, 'scripts', 'entry_location_trades.csv')


def universe():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    return basket, others


def prep(df):
    df = df.sort_values('timestamp').reset_index(drop=True).copy()
    df['rsi'] = compute_rsi(df['close'])
    df['atr'] = compute_atr(df)
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    return df


def features_at(df, i, sgn):
    """D1/D2/D3 at bar i for direction sgn; None if not enough history."""
    if i < 167:
        return None
    c = df['close'].values[i]
    a = df['atr'].values[i]
    if np.isnan(a) or a <= 0:
        return None
    h24 = df['high'].values[i - 23:i + 1]
    l24 = df['low'].values[i - 23:i + 1]
    h168 = df['high'].values[i - 167:i + 1]
    l168 = df['low'].values[i - 167:i + 1]
    rng = h168.max() - l168.min()
    if sgn > 0:
        d1 = (c - l24.min()) / a
        d2 = (c - l168.min()) / rng if rng > 0 else np.nan
        d3 = 23 - int(np.argmin(l24))
    else:
        d1 = (h24.max() - c) / a
        d2 = (h168.max() - c) / rng if rng > 0 else np.nan
        d3 = 23 - int(np.argmax(h24))
    if np.isnan(d2):
        return None
    return dict(runup24_atr=d1, pos168=d2, age24=d3)


def build():
    basket, others = universe()
    rows = []
    for b in basket + others:
        df = prep(load(b))
        df = df[df['timestamp'] < DEV_END].reset_index(drop=True)
        c, h, l, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        for s in signals(df).itertuples():
            f = features_at(df, s.i, s.sgn)
            if f is None:
                continue
            rows.append(dict(coin=b, sample='15' if b in basket else '35', time=df['timestamp'].iloc[s.i],
                             sgn=s.sgn, r=simulate(c, h, l, s.i, s.sgn, atr[s.i]), **f))
        print(f'  {b}: {sum(1 for x in rows if x["coin"] == b)} trades', flush=True)
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, '2020-23', '2024-25')
    return d


def quintile_cuts(x):
    """Rank-based cut points (20/40/60/80 pct) frozen for the holdout."""
    return [float(v) for v in np.quantile(x, [0.2, 0.4, 0.6, 0.8])]


def assign(x, cuts):
    return np.searchsorted(cuts, x, side='right')  # 0..4


def stat(d, q):
    return d.r[q == 4].mean() - d.r[q == 0].mean()


def perm_p(d, q, rng, n_perm=N_PERM):
    """One-sided (user's hypothesis: Q5 worse than Q1) within-coin permutation."""
    real = stat(d, q)
    r = d.r.values
    q = np.asarray(q)
    idx = [np.flatnonzero(d.coin.values == c) for c in d.coin.unique()]
    worse = 0
    for _ in range(n_perm):
        sh = q.copy()
        for ix in idx:
            sh[ix] = rng.permutation(sh[ix])
        worse += (r[sh == 4].mean() - r[sh == 0].mean()) <= real
    return real, (worse + 1) / (n_perm + 1)


def table(d, q, label):
    print(f'\n  {label}: n={len(d)}  quintile mean R / win% / n')
    for k in range(5):
        x = d.r[q == k]
        print(f'    Q{k+1}: {x.mean():+.3f}R  win {100*(x>0).mean():4.1f}%  n={len(x)}')


def main():
    rng = np.random.default_rng(20261031)
    d = build()
    d.to_csv(OUT_CSV, index=False)
    print(f'\nDEV population: {len(d)} trades, {d.coin.nunique()} coins, mean R {d.r.mean():+.4f}')
    cuts = {}
    results = {}
    for f in FEATURES:
        if f == 'age24':
            # discrete 0..23: rank with ties broken by order so quintiles are equal-sized in dev
            x = d[f].rank(method='first').values
            c = quintile_cuts(x)
            q = assign(x, c)
            cuts[f] = quintile_cuts(d[f].values)  # value-based cuts for the holdout
        else:
            cuts[f] = quintile_cuts(d[f].values)
            q = assign(d[f].values, cuts[f])
        d[f + '_q'] = q
        real, p = perm_p(d, q, rng)
        sub = {}
        for lab, m in (('2020-23', d.period == '2020-23'), ('2024-25', d.period == '2024-25'),
                       ('15', d['sample'] == '15'), ('35', d['sample'] == '35'),
                       ('long', d.sgn == 1), ('short', d.sgn == -1)):
            sub[lab] = stat(d[m], q[m.values])
        consistent = all(np.sign(sub[k]) == np.sign(real) for k in ('2020-23', '2024-25', '15', '35'))
        passed = bool(real < 0 and p < ALPHA and consistent)
        results[f] = dict(stat=real, p=p, sub=sub, passed=passed)
        print('\n' + '=' * 90)
        print(f'{f}: Q5-Q1 = {real:+.3f}R  one-sided perm p = {p:.4f}  (alpha {ALPHA:.4f})')
        print('  sub-samples Q5-Q1: ' + '  '.join(f'{k} {v:+.3f}' for k, v in sub.items()))
        print(f'  consistent sign across periods & samples: {consistent}  ->  {"PASS" if passed else "FAIL"}')
        table(d, q, 'pooled dev')
        for lab in ('2020-23', '2024-25'):
            m = (d.period == lab).values
            table(d[m], q[m], lab)
        # descriptive: what happens to total R if Q5 were dropped (NOT a rule)
        for lab in ('2020-23', '2024-25'):
            m = (d.period == lab).values
            allr, drop = d.r[m].sum(), d.r[m & (q != 4)].sum()
            print(f'  descriptive {lab}: total R all {allr:+.1f}  without Q5 {drop:+.1f}  (Q5 alone {allr-drop:+.1f})')
    with open(CUTS_PATH, 'w') as fh:
        json.dump(dict(cuts=cuts, alpha=ALPHA, n_dev=len(d),
                       results={k: dict(stat=v['stat'], p=v['p'], passed=v['passed']) for k, v in results.items()}),
                  fh, indent=2)
    d.to_csv(OUT_CSV, index=False)
    print('\nSUMMARY: ' + ', '.join(f'{k} {"PASS" if v["passed"] else "FAIL"} (p={v["p"]:.4f})' for k, v in results.items()))
    print(f'cuts frozen -> {CUTS_PATH}')


if __name__ == '__main__':
    main()
