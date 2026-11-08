"""
ONE-SHOT 2026 HOLDOUT for H_K1 cross-sectional funding carry (passed the
dev window 2026-10-25; RESEARCH_FINDINGS.md "第三輪新方向 K"). Rule exactly
as prereg_xs_funding.py: Sunday-close rebalance, score = trailing 7-day
mean funding, long the lowest 20 % / short the highest 20 %, 0.5 per
side, 0.07 % per side on weight change, actual funding. Weeks whose
forward window lies inside 2026-01-01 .. 2026-09-30.
Pass (fixed before running): 50-coin weekly net series mean > 0 with
one-sided bootstrap p < 0.05, AND the 35 unseen coins' annualised net > 0.
Run once. Diagnostics printed after: price/funding decomposition,
quarterly, turnover, and how concentrated the short leg is.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = sys.argv[:1]
import prereg_xs_funding as K  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from prereg_xs_momentum import backtest  # noqa: E402

HSTART, HEND = pd.Timestamp('2026-01-01'), pd.Timestamp('2026-10-01')


def main():
    rng = np.random.default_rng(K.SEED)
    px, fund = full_daily_panel()
    px = px[(px.index >= pd.Timestamp('2025-10-01')) & (px.index < HEND)]
    coins = list(px.columns)
    unseen = [c for c in coins if c not in set(ORIGINAL + MAJORS)]
    weeks = [w for w in K.funding_weeks(px, fund) if w[0] >= HSTART - pd.Timedelta(days=1) and w[0] + pd.Timedelta(days=7) < HEND]
    fn = lambda sc: list(sc.sort_values(ascending=False).index)  # noqa: E731
    print(f'holdout weeks={len(weeks)}  {weeks[0][0].date()}..{weeks[-1][0].date()}')
    res = {}
    for label, cs in [('50', coins), ('35', unseen)]:
        r = backtest(weeks, cs, fn)
        dec = K.decompose(weeks, cs, fn)
        x = r.values
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        p = (rng.choice(x, (10000, len(x))).mean(1) <= 0).mean()
        res[label] = (r.mean() * 52 * 100, p)
        print(f'  {label} coins weeks={len(r)}  ann net={res[label][0]:+.1f}%  Sharpe={K.sharpe(r):+.2f}  t={t:+.2f}  p={p:.4f}  '
              f'price={dec.price.mean()*52*100:+.1f}%  funding={dec.funding.mean()*52*100:+.1f}%  '
              f'maxDD={(1-(1+r).cumprod()/(1+r).cumprod().cummax()).max()*100:.0f}%  weeks>0={(r>0).mean()*100:.0f}%')
        if label == '50':
            for q, g in r.groupby(r.index.quarter):
                print(f'    2026Q{q}: weeks={len(g)}  ann net={g.mean()*52*100:+.1f}%')
            r.to_csv(os.path.join(K.ROOT, 'scripts', 'holdout_xs_funding_weekly.csv'))
    ok = res['50'][0] > 0 and res['50'][1] < 0.05 and res['35'][0] > 0
    print(f'  -> H_K1 2026 {"PASS" if ok else "FAIL"}')
    # concentration of the short leg (diagnostic)
    shorts = pd.Series(dtype=int)
    for s, score, fwd, fsum in weeks:
        order = fn(score)
        k = max(1, int(len(order) * 0.2))
        shorts = shorts.add(pd.Series(1, index=order[:k]), fill_value=0)
    print('  short-leg frequency (weeks):', shorts.sort_values(ascending=False).head(10).astype(int).to_dict())


if __name__ == '__main__':
    main()
