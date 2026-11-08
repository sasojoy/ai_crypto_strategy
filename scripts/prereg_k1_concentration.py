"""
PRE-REGISTERED P2 (RESEARCH_FINDINGS.md 2026-11-08): K1 short-leg
concentration RISK DIAGNOSTIC. Not a rule change.

K1x = K1 with one causal exclusion: a coin that was in K1's actual short
leg in EACH of the previous 8 weekly books may not be shorted this week;
the short leg skips it and takes the next-highest funding coin. Longs,
k, costs, funding all unchanged. Reported for 2020-25 (dev) and 2026
(already seen by K1 -- diagnostic), 50 and 35 coins.

Pre-set reading: dev 50-coin Sharpe(K1x) < Sharpe(K1) - 0.3 => the
structural high-funding shorts are a material return source
(concentration = real risk); within +/-0.3 => concentration without
return dependence; K1x higher => they were a drag. All three only recorded.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = sys.argv[:1]

from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402
from prereg_xs_momentum import COST_PER_SIDE  # noqa: E402
import prereg_xs_funding as K  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT, HSTART, HEND = pd.Timestamp('2024-01-01'), pd.Timestamp('2026-01-01'), pd.Timestamp('2026-10-01')
STREAK = 8


def run(weeks, coins, exclude):
    """Returns weekly net return series, price/funding parts, and excluded coin-weeks."""
    rets, parts, prev_w, excluded = [], [], pd.Series(dtype=float), []
    streak = {}  # coin -> consecutive past weeks in the short leg (from actual books)
    for s, score, fwd, fsum in weeks:
        cols = [c for c in score.index if c in coins]
        if len(cols) < 5:
            continue
        order = list(score[cols].sort_values(ascending=False).index)  # longs = lowest funding (end of list)
        k = max(1, int(len(cols) * 0.2))
        longs = order[-k:]
        banned = {c for c in cols if exclude and streak.get(c, 0) >= STREAK}
        shorts = [c for c in order if c not in banned][:k]
        excluded += [(s, c) for c in banned if c in order[:k]]
        w = pd.Series(0.0, index=cols)
        w[longs] = 0.5 / k
        w[shorts] = -0.5 / k
        turnover = w.subtract(prev_w, fill_value=0).abs().sum()
        price, fund = (w * fwd[cols]).sum(), -(w * fsum[cols]).sum()
        rets.append((s, price + fund - turnover * COST_PER_SIDE))
        parts.append((s, price, fund))
        prev_w = w
        for c in cols:
            streak[c] = streak.get(c, 0) + 1 if c in shorts else 0
    r = pd.Series(dict(rets))
    p = pd.DataFrame(parts, columns=['s', 'price', 'funding']).set_index('s')
    return r, p, excluded


def stats(r, p):
    eq = (1 + r).cumprod()
    return dict(n=len(r), ann=r.mean() * 52 * 100, sharpe=K.sharpe(r), mdd=(1 - eq / eq.cummax()).max() * 100,
                price=p.price.mean() * 52 * 100, funding=p.funding.mean() * 52 * 100)


def main():
    px, fund = full_daily_panel()
    px = px[(px.index >= pd.Timestamp('2020-01-01')) & (px.index < HEND)]
    coins = list(px.columns)
    unseen = [c for c in coins if c not in set(ORIGINAL + MAJORS)]
    weeks = [w for w in K.funding_weeks(px, fund) if w[0] + pd.Timedelta(days=7) < HEND]
    print(f'coins={len(coins)} weeks={len(weeks)} {weeks[0][0].date()}..{weeks[-1][0].date()}')
    res = {}
    for label, cs in [('50', coins), ('35', unseen)]:
        base, bp, _ = run(weeks, cs, exclude=False)
        var, vp, exc = run(weeks, cs, exclude=True)
        for per, m in [('2020-23', base.index < SPLIT), ('2024-25', (base.index >= SPLIT) & (base.index < HSTART)),
                       ('dev', base.index < HSTART), ('2026', base.index >= HSTART)]:
            b, v = stats(base[m], bp[m]), stats(var[m], vp[m])
            res[(label, per)] = (b, v)
            print(f'  {label} {per:8s} weeks={b["n"]:3d}  K1  ann={b["ann"]:+6.1f}% Sharpe={b["sharpe"]:+.2f} mdd={b["mdd"]:4.1f}% price={b["price"]:+6.1f}% fund={b["funding"]:+5.1f}%'
                  f'  |  K1x ann={v["ann"]:+6.1f}% Sharpe={v["sharpe"]:+.2f} mdd={v["mdd"]:4.1f}% price={v["price"]:+6.1f}% fund={v["funding"]:+5.1f}%'
                  f'  |  dSharpe={v["sharpe"]-b["sharpe"]:+.2f}')
        ex = pd.DataFrame(exc, columns=['week', 'coin'])
        if len(ex):
            ex['per'] = np.where(ex.week < HSTART, 'dev', '2026')
            print(f'    excluded coin-weeks: dev {int((ex.per=="dev").sum())}, 2026 {int((ex.per=="2026").sum())}; '
                  f'top coins: {ex.coin.value_counts().head(8).to_dict()}')
        if label == '50':
            pd.DataFrame({'K1': base, 'K1x': var}).to_csv(os.path.join(ROOT, 'scripts', 'k1_concentration_weekly.csv'))
    b, v = res[('50', 'dev')]
    d = v['sharpe'] - b['sharpe']
    verdict = ('structural shorts are a MATERIAL return source (concentration = real risk)' if d < -0.3 else
               'structural shorts were a DRAG' if d > 0.3 else 'concentration WITHOUT return dependence')
    print(f'\nREADING (dev 50 coins): Sharpe K1 {b["sharpe"]:+.2f} vs K1x {v["sharpe"]:+.2f} (d={d:+.2f}) -> {verdict}')
    print('No rule change.')


if __name__ == '__main__':
    main()
