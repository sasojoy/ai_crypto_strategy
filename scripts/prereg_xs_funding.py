"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "第三輪新方向 K", 2026-10-25).
DEV WINDOW 2020-01 .. 2025-12, 2026 untouched. Cross-sectional funding:
same weekly long/short machinery as prereg_xs_momentum (Sunday close
rebalance, long top 20 % / short bottom 20 % of the score, 0.5 per side,
0.07 % per side on weight change, actual funding), with the score
replaced by the trailing 7-day mean funding rate.

  H_K1 carry:    long the LOWEST-funding 20 %, short the HIGHEST-funding 20 %
  H_K2 momentum: long the HIGHEST-funding 20 %, short the LOWEST-funding 20 %

Pass (each, alpha 0.025 in spirit -- the gate is the same as H_E3):
annualised net return > 0 in BOTH 2020-23 and 2024-25, for the 50-coin
set AND the 35 unseen coins, and full-period Sharpe above the 95th
percentile of 1,000 random weekly rankings. Price / funding decomposition
is printed for both as description. Nothing is re-tuned.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402
from prereg_xs_momentum import weekly_inputs, backtest, COST_PER_SIDE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START, END, SPLIT = pd.Timestamp('2020-01-01'), pd.Timestamp('2026-01-01'), pd.Timestamp('2024-01-01')
N_RAND, SEED = 1000, 20261025


def funding_weeks(px, fund):
    """weekly_inputs rows with the score replaced by the trailing 7-day mean funding."""
    out = []
    for s, score, fwd, fsum in weekly_inputs(px, fund, 7):
        lo = s - pd.Timedelta(days=7)
        fm = pd.Series({c: fund[c][(fund[c].index > lo) & (fund[c].index <= s)].mean() for c in fwd.index})
        fm = fm.dropna()
        keep = [c for c in fm.index if c in fwd.index]
        out.append((s, fm[keep], fwd[keep], fsum[keep]))
    return out


def decompose(weeks, coins, rank_fn):
    """Weekly price-only and funding-only parts (no cost), same weights as backtest."""
    rows = []
    for s, score, fwd, fsum in weeks:
        cols = [c for c in score.index if c in coins]
        if len(cols) < 5:
            continue
        order = rank_fn(score[cols])
        k = max(1, int(len(cols) * 0.2))
        w = pd.Series(0.0, index=cols)
        w[order[-k:]] = 0.5 / k
        w[order[:k]] = -0.5 / k
        rows.append((s, (w * fwd[cols]).sum(), -(w * fsum[cols]).sum()))
    d = pd.DataFrame(rows, columns=['s', 'price', 'funding']).set_index('s')
    return d


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(52) if r.std() > 0 else np.nan


def main():
    rng = np.random.default_rng(SEED)
    px, fund = full_daily_panel()
    px = px[(px.index >= START) & (px.index < END)]
    basket = set(ORIGINAL + MAJORS)
    coins = list(px.columns)
    unseen = [c for c in coins if c not in basket]
    weeks = funding_weeks(px, fund)
    print(f'coins={len(coins)}  weeks={len(weeks)}  {weeks[0][0].date()}..{weeks[-1][0].date()}')
    rank = {'H_K1 carry (long low funding, short high funding)': lambda sc: list(sc.sort_values(ascending=False).index),
            'H_K2 funding momentum (long high funding, short low funding)': lambda sc: list(sc.sort_values().index)}
    for name, fn in rank.items():
        print(f'\n=== {name} ===')
        res = {}
        for label, cs in [('50', coins), ('35', unseen)]:
            r = backtest(weeks, cs, fn)
            dec = decompose(weeks, cs, fn)
            for per, m in [('2020-23', r.index < SPLIT), ('2024-25', r.index >= SPLIT), ('full', r.index == r.index)]:
                res[(label, per)] = r[m].mean() * 52 * 100
                dm = dec.loc[r.index[m]]
                print(f'  {label} coins {per:8s} weeks={m.sum():3d}  ann net={res[(label, per)]:+7.1f}%  Sharpe={sharpe(r[m]):+.2f}  '
                      f'price={dm.price.mean()*52*100:+7.1f}%  funding={dm.funding.mean()*52*100:+6.1f}%  maxDD={(1-(1+r[m]).cumprod()/(1+r[m]).cumprod().cummax()).max()*100:.0f}%')
            if label == '50':
                rand = []
                for _ in range(N_RAND):
                    rr = backtest(weeks, cs, lambda sc: list(sc.sample(frac=1, random_state=int(rng.integers(1e9))).index))
                    rand.append(sharpe(rr))
                res['sh'], res['p95'] = sharpe(r), np.percentile(rand, 95)
                print(f'  50 coins full Sharpe {res["sh"]:+.2f} vs random p95 {res["p95"]:+.2f}')
                r.to_csv(os.path.join(ROOT, 'scripts', f'xs_funding_{name.split()[0]}_weekly.csv'))
        ok = all(res[(l, p)] > 0 for l in ('50', '35') for p in ('2020-23', '2024-25')) and res['sh'] > res['p95']
        print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}')


if __name__ == '__main__':
    main()
