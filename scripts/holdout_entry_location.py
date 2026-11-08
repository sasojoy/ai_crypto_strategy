"""
ONE-SHOT 2026 holdout for the pre-registered entry-location diagnostic
(RESEARCH_FINDINGS.md 2026-10-31). Run ONCE, after prereg_entry_location.py.

Population = scripts/holdout_short_crowding_trades.csv (v7 close-entry
proxy, 50 coins, frozen per-coin volume cutoffs, 2026-01-01..). Only the
features are recomputed here from data/backtest_cache/holdout_2026/*_1h.csv,
with the DEV-frozen quintile cut points (scripts/entry_location_cuts.json).
Test: Q5 - Q1 mean R, one-sided within-coin permutation p < 0.05, same sign
as dev. Features that FAILED in dev are reported descriptively only.

Also descriptive: the forward tracker's 2026-10 trades (data/forward/
forward_trades.csv, 1h files in data/forward/) placed into the same frozen
quintiles.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import prereg_entry_location as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLD = os.path.join(ROOT, 'data', 'backtest_cache', 'holdout_2026')
FWD = os.path.join(ROOT, 'data', 'forward')
ALPHA = 0.05


def add_features(trades, loader):
    rows = []
    for b, g in trades.groupby('coin'):
        df = loader(b)
        if df is None:
            continue
        df = P.prep(df)
        ts = df['timestamp'].values
        for t in g.itertuples():
            i = int(np.searchsorted(ts, np.datetime64(t.time)))
            if i >= len(ts) or ts[i] != np.datetime64(t.time):
                continue
            f = P.features_at(df, i, int(t.sgn))
            if f is None:
                continue
            rows.append(dict(coin=b, time=t.time, sgn=int(t.sgn), r=t.r, **f))
    return pd.DataFrame(rows)


def hold_loader(b):
    p = os.path.join(HOLD, f'{b}_USDT_1h.csv')
    return pd.read_csv(p, parse_dates=['timestamp']) if os.path.exists(p) else None


def fwd_loader(b):
    p = os.path.join(FWD, f'{b}_USDT_1h.csv')
    return pd.read_csv(p, parse_dates=['timestamp']) if os.path.exists(p) else None


def main():
    with open(P.CUTS_PATH) as fh:
        frozen = json.load(fh)
    cuts, dev_res = frozen['cuts'], frozen['results']
    rng = np.random.default_rng(2026)

    h = pd.read_csv(os.path.join(ROOT, 'scripts', 'holdout_short_crowding_trades.csv'), parse_dates=['time'])
    h = add_features(h, hold_loader)
    print(f'2026 holdout population: {len(h)} trades, {h.coin.nunique()} coins, mean R {h.r.mean():+.4f}')
    for f in P.FEATURES:
        q = P.assign(h[f].values, cuts[f])
        real, p = P.perm_p(h, q, rng)
        dev_sign = np.sign(dev_res[f]['stat'])
        same = np.sign(real) == dev_sign
        verdict = ('PASS' if (real < 0 and p < ALPHA and same) else 'FAIL') if dev_res[f]['passed'] else 'descriptive (failed dev)'
        print('\n' + '=' * 90)
        print(f'{f}: 2026 Q5-Q1 = {real:+.3f}R  one-sided perm p = {p:.4f}  dev stat {dev_res[f]["stat"]:+.3f}  -> {verdict}')
        P.table(h, q, '2026')
        for lab, m in (('long', h.sgn == 1), ('short', h.sgn == -1)):
            print(f'  {lab}: Q5-Q1 {P.stat(h[m], q[m.values]):+.3f}R (n={m.sum()})')
        h['q'] = pd.PeriodIndex(h.time, freq='Q').astype(str)
        for lab, g in h.groupby('q'):
            print(f'  {lab}: Q5-Q1 {P.stat(g, q[(h.q == lab).values]):+.3f}R (n={len(g)})')
    h.to_csv(os.path.join(ROOT, 'scripts', 'holdout_entry_location_trades.csv'), index=False)

    # descriptive: forward tracker 2026-10 trades
    fw = pd.read_csv(os.path.join(FWD, 'forward_trades.csv'), parse_dates=['time'])
    fw = fw[fw.status != 'OPEN'].copy()
    fw['sgn'] = np.where(fw.direction == 'long', 1, -1)
    fw = add_features(fw[['coin', 'time', 'sgn', 'r']], fwd_loader)
    print('\n' + '=' * 90)
    print(f'FORWARD 2026-10 (descriptive): {len(fw)} closed trades, mean R {fw.r.mean():+.3f}')
    for f in P.FEATURES:
        q = P.assign(fw[f].values, cuts[f])
        share = np.bincount(q, minlength=5) / len(q)
        print(f'  {f}: share in Q1..Q5 = ' + ' '.join(f'{100*s:4.1f}%' for s in share)
              + f'   mean R by Q: ' + ' '.join(f'{fw.r[q==k].mean():+.2f}' if (q == k).any() else '  n/a' for k in range(5)))


if __name__ == '__main__':
    main()
