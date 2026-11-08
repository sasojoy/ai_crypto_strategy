"""
PRE-REGISTERED P5 (RESEARCH_FINDINGS.md 2026-11-08): total-exposure
controls on K1's weekly return series (scripts/k1_sizing_weekly.csv, K1
column, 50 coins, costs and funding included).

  V1 vol target:   L_t = 3% / sigma_{t-1} (26-week std, lagged, min 13 weeks), clipped 0.25..2.0
  V2 factor momentum: L_t = 0.5 if K1's trailing 4-week sum < 0 else 1.0
  V3 = V1 * V2
Leverage changes cost |dL| * 0.07% (one side).

Fair tail comparison: each variant is linearly scaled so its DEV weekly
std equals K1's dev std (Sharpe unaffected); the same scale is applied to
2026. Pass = dev Sharpe >= K1 - 0.1 AND scaled maxDD and worst week better
than K1 in BOTH 2020-23 and 2024-25 AND 2026 Sharpe >= K1 - 0.3.
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT, HSTART = pd.Timestamp('2024-01-01'), pd.Timestamp('2026-01-01')
TARGET, LMIN, LMAX, WIN, MINW, COST = 0.03, 0.25, 2.0, 26, 13, 0.0007


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(52) if r.std() > 0 else np.nan


def stats(r):
    eq = (1 + r).cumprod()
    return dict(n=len(r), ann=r.mean() * 52 * 100, sharpe=sharpe(r), mdd=(1 - eq / eq.cummax()).max() * 100, worst=r.min() * 100)


def apply(k1, lev):
    lev = lev.reindex(k1.index).fillna(1.0)
    cost = (lev - lev.shift(1).fillna(1.0)).abs() * COST
    return lev * k1 - cost, lev


def main():
    k1 = pd.read_csv(os.path.join(ROOT, 'scripts', 'k1_sizing_weekly.csv'), index_col=0, parse_dates=True)['K1'].dropna()
    sig = k1.rolling(WIN, min_periods=MINW).std().shift(1)
    l1 = (TARGET / sig).clip(LMIN, LMAX)
    l2 = pd.Series(np.where(k1.rolling(4).sum().shift(1) < 0, 0.5, 1.0), index=k1.index)
    variants = {'V1 vol target': l1, 'V2 factor momentum': l2, 'V3 both': l1 * l2}
    dev = k1.index < HSTART
    periods = [('2020-23', k1.index < SPLIT), ('2024-25', (k1.index >= SPLIT) & dev), ('dev', dev), ('2026', ~dev)]
    base = {p: stats(k1[m]) for p, m in periods}
    print(f'K1 weeks={len(k1)} {k1.index[0].date()}..{k1.index[-1].date()}')
    for p, _ in periods:
        b = base[p]
        print(f'  K1  {p:8s} n={b["n"]:3d} ann={b["ann"]:+6.1f}% Sharpe={b["sharpe"]:+.2f} mdd={b["mdd"]:4.1f}% worst={b["worst"]:+5.1f}%')
    out = pd.DataFrame({'K1': k1})
    for name, lev in variants.items():
        r, L = apply(k1, lev)
        scale = k1[dev].std() / r[dev].std()
        rs = r * scale
        out[name] = rs
        st = {p: stats(rs[m]) for p, m in periods}
        print(f'\n  {name}: mean leverage dev {L[dev].mean():.2f} (min {L[dev].min():.2f} max {L[dev].max():.2f}), 2026 {L[~dev].mean():.2f}; scale to K1 dev std = {scale:.2f}')
        for p, _ in periods:
            s = st[p]
            print(f'    {p:8s} n={s["n"]:3d} ann={s["ann"]:+6.1f}% Sharpe={s["sharpe"]:+.2f} mdd={s["mdd"]:4.1f}% worst={s["worst"]:+5.1f}%  '
                  f'(vs K1: Sharpe {s["sharpe"]-base[p]["sharpe"]:+.2f}, mdd {s["mdd"]-base[p]["mdd"]:+.1f}pt, worst {s["worst"]-base[p]["worst"]:+.1f}pt)')
        c1 = st['dev']['sharpe'] >= base['dev']['sharpe'] - 0.1
        c2 = all(st[p]['mdd'] < base[p]['mdd'] and st[p]['worst'] > base[p]['worst'] for p in ('2020-23', '2024-25'))
        c3 = st['2026']['sharpe'] >= base['2026']['sharpe'] - 0.3
        print(f'    dev Sharpe ok: {c1}; tail better both periods: {c2}; 2026 ok: {c3}  -> {"PASS" if (c1 and c2 and c3) else "FAIL"}')
    out.to_csv(os.path.join(ROOT, 'scripts', 'k1_exposure_weekly.csv'))
    print('\nNo change to the running K1.')


if __name__ == '__main__':
    main()
