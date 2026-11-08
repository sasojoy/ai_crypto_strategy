"""
PRE-REGISTERED P4 (RESEARCH_FINDINGS.md 2026-11-08): position-layer
variants of K1 that spread single-coin squeeze risk.

  K1   base: 20% per side, equal 0.5/k
  K1w  wider: 30% per side, equal 0.5/k
  K1v  inverse-vol within each side (sigma = trailing 30-day daily-return
       std, causal), normalised to 0.5 per side, per-coin cap 2x equal weight

Reading (pre-set): a variant "reduces single-coin risk at no cost" iff dev
50-coin Sharpe >= K1 - 0.2 AND worst week AND maxDD are no worse than K1
in BOTH 2020-23 and 2024-25. 2026 reported alongside (K1 has seen 2026);
flag "2026 not supportive" if variant Sharpe < K1 - 0.3 there.
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
VARIANTS = {'K1': dict(frac=0.2, invvol=False), 'K1w': dict(frac=0.3, invvol=False), 'K1v': dict(frac=0.2, invvol=True)}


def side_weights(names, sigma, total, invvol, cap_mult=2.0):
    n = len(names)
    if not invvol:
        return pd.Series(total / n, index=names)
    s = sigma.reindex(names)
    s = s.fillna(s.median()).clip(lower=1e-6)
    w = (1 / s)
    w = w / w.sum() * total
    cap = cap_mult * total / n
    for _ in range(10):  # iterative cap + redistribute
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over
        if under.any():
            w[under] += excess * w[under] / w[under].sum()
    return w


def run(weeks, px, coins, frac, invvol):
    rets, parts, maxw, prev_w = [], [], [], pd.Series(dtype=float)
    daily = px.pct_change()
    for s, score, fwd, fsum in weeks:
        cols = [c for c in score.index if c in coins]
        if len(cols) < 5:
            continue
        order = list(score[cols].sort_values(ascending=False).index)
        k = max(1, int(len(cols) * frac))
        longs, shorts = order[-k:], order[:k]
        sigma = daily.loc[:s, cols].tail(30).std() if invvol else None
        w = pd.Series(0.0, index=cols)
        w[longs] = side_weights(longs, sigma, 0.5, invvol)
        w[shorts] = -side_weights(shorts, sigma, 0.5, invvol)
        turnover = w.subtract(prev_w, fill_value=0).abs().sum()
        price, fund = (w * fwd[cols]).sum(), -(w * fsum[cols]).sum()
        rets.append((s, price + fund - turnover * COST_PER_SIDE))
        parts.append((s, price, fund, turnover))
        maxw.append(w.abs().max())
        prev_w = w
    r = pd.Series(dict(rets))
    p = pd.DataFrame(parts, columns=['s', 'price', 'funding', 'turnover']).set_index('s')
    return r, p, float(np.mean(maxw))


def stats(r, p):
    eq = (1 + r).cumprod()
    return dict(n=len(r), ann=r.mean() * 52 * 100, sharpe=K.sharpe(r), mdd=(1 - eq / eq.cummax()).max() * 100,
                worst=r.min() * 100, price=p.price.mean() * 52 * 100, funding=p.funding.mean() * 52 * 100,
                turnover=p.turnover.mean())


def main():
    px, fund = full_daily_panel()
    px = px[(px.index >= pd.Timestamp('2020-01-01')) & (px.index < HEND)]
    coins = list(px.columns)
    unseen = [c for c in coins if c not in set(ORIGINAL + MAJORS)]
    weeks = [w for w in K.funding_weeks(px, fund) if w[0] + pd.Timedelta(days=7) < HEND]
    print(f'coins={len(coins)} weeks={len(weeks)} {weeks[0][0].date()}..{weeks[-1][0].date()}')
    periods = [('2020-23', lambda i: i < SPLIT), ('2024-25', lambda i: (i >= SPLIT) & (i < HSTART)),
               ('dev', lambda i: i < HSTART), ('2026', lambda i: i >= HSTART)]
    res, out = {}, {}
    for label, cs in [('50', coins), ('35', unseen)]:
        for name, cfg in VARIANTS.items():
            r, p, mw = run(weeks, px, cs, **cfg)
            if label == '50':
                out[name] = r
            for per, f in periods:
                m = f(r.index)
                st = stats(r[m], p[m])
                res[(label, name, per)] = st
                print(f'  {label} {name:3s} {per:8s} weeks={st["n"]:3d} ann={st["ann"]:+6.1f}% Sharpe={st["sharpe"]:+.2f} '
                      f'mdd={st["mdd"]:4.1f}% worst wk={st["worst"]:+5.1f}% price={st["price"]:+6.1f}% fund={st["funding"]:+5.1f}% '
                      f'turnover={st["turnover"]:.2f} maxw={mw*100:.1f}%')
            if name == 'K1' and label == '50':
                pass
        print()
    pd.DataFrame(out).to_csv(os.path.join(ROOT, 'scripts', 'k1_sizing_weekly.csv'))
    print('READING (dev 50 coins, pre-set):')
    base = {per: res[('50', 'K1', per)] for per, _ in periods}
    for name in ('K1w', 'K1v'):
        v = {per: res[('50', name, per)] for per, _ in periods}
        c1 = v['dev']['sharpe'] >= base['dev']['sharpe'] - 0.2
        c2 = all(v[per]['worst'] >= base[per]['worst'] for per in ('2020-23', '2024-25'))
        c3 = all(v[per]['mdd'] <= base[per]['mdd'] for per in ('2020-23', '2024-25'))
        ok = c1 and c2 and c3
        h = '2026 not supportive' if v['2026']['sharpe'] < base['2026']['sharpe'] - 0.3 else '2026 ok'
        print(f'  {name}: Sharpe dev {v["dev"]["sharpe"]:+.2f} vs K1 {base["dev"]["sharpe"]:+.2f} ({"ok" if c1 else "FAIL"}); '
              f'worst week no worse both periods: {c2}; maxDD no worse both periods: {c3}  -> {"PASS" if ok else "FAIL"}; {h}')
    print('No change to the running K1.')


if __name__ == '__main__':
    main()
