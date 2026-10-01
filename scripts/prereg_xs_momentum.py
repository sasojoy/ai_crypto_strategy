"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md, commit ef4b640). DEV WINDOW ONLY.
New strategy candidate 3: cross-sectional momentum (market neutral).

Daily UTC closes, 50 coins (eligible once they have 28 days of history).
Every Sunday close (= Monday 00:00 UTC) rank eligible coins by their
trailing LOOKBACK-day return; long the top 20%, short the bottom 20%,
equal weight per side, 0.5 gross per side. Hold one week.
Costs: |weight change| x 0.07% per rebalance; funding from actual history
(long pays, short receives, settlements inside the holding week).
Primary LOOKBACK = 28 days; 7-day run is descriptive only.
Pass (28d): (1) annualized return > 0 in 2020-23 and in 2024-25 on all 50
coins; (2) same on the 35 unseen coins alone; (3) full-period Sharpe beats
>= 95% of 1,000 random weekly rankings (same sizes, same cost model).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_coin_personality import ORIGINAL, MAJORS, load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
U1H = os.path.join(CACHE, 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')
COST_PER_SIDE = 0.0007
N_RANDOM = 1000


def load_panel():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    closes, funding = {}, {}
    for b in basket + others:
        df = load(b)
        closes[b] = df.set_index('timestamp')['close'].resample('1D').last()
        fdir = 'funding_basket' if b in basket else 'funding_universe'
        f = pd.read_csv(os.path.join(CACHE, fdir, f'{b}_USDT_funding.csv'))
        f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
        funding[b] = f.set_index('timestamp')['funding_rate']
    px = pd.DataFrame(closes)
    px = px[px.index < '2026-01-01']
    return px, funding, others


def weekly_inputs(px, funding, lookback):
    sundays = px.index[px.index.dayofweek == 6]
    rows = []
    for s in sundays:
        prev, nxt = s - pd.Timedelta(days=lookback), s + pd.Timedelta(days=7)
        if prev not in px.index or nxt not in px.index:
            continue
        score = px.loc[s] / px.loc[prev] - 1
        fwd = px.loc[nxt] / px.loc[s] - 1
        ok = score.notna() & fwd.notna()
        # funding paid by a long over (s close, next s close]: settlements in (s+1d, nxt+1d]
        lo, hi = s + pd.Timedelta(days=1), nxt + pd.Timedelta(days=1)
        fsum = pd.Series({c: funding[c][(funding[c].index > lo) & (funding[c].index <= hi)].sum() for c in px.columns})
        rows.append((s, score[ok], fwd[ok], fsum[ok.index[ok]]))
    return rows


def backtest(weeks, coins, rank_fn):
    rets, prev_w = [], pd.Series(dtype=float)
    for s, score, fwd, fsum in weeks:
        cols = [c for c in score.index if c in coins]
        if len(cols) < 5:
            continue
        order = rank_fn(score[cols])
        k = max(1, int(len(cols) * 0.2))
        longs, shorts = order[-k:], order[:k]
        w = pd.Series(0.0, index=cols)
        w[longs] = 0.5 / k
        w[shorts] = -0.5 / k
        turnover = w.subtract(prev_w, fill_value=0).abs().sum()
        gross = (w * fwd[cols]).sum() - (w * fsum[cols]).sum()  # long pays funding, short receives
        rets.append((s, gross - turnover * COST_PER_SIDE))
        prev_w = w
    return pd.Series(dict(rets))


def stats(r):
    eq = (1 + r).cumprod()
    dd = (1 - eq / eq.cummax()).max()
    return dict(ann=r.mean() * 52 * 100, sharpe=r.mean() / r.std() * np.sqrt(52) if r.std() > 0 else np.nan,
                cagr=(eq.iloc[-1] ** (52 / len(r)) - 1) * 100, mdd=dd * 100, n=len(r))


def show(label, r):
    for p, m in (('2020-23', r.index < SPLIT), ('2024-25', r.index >= SPLIT), ('all', slice(None))):
        s = stats(r[m])
        print(f"  {label:22s} {p:8s} weeks={s['n']:3d} ann={s['ann']:+7.1f}%  CAGR={s['cagr']:+7.1f}%  Sharpe={s['sharpe']:+.2f}  maxDD={s['mdd']:5.1f}%")


def main():
    px, funding, others = load_panel()
    all_coins = list(px.columns)
    momentum = lambda sc: list(sc.sort_values().index)
    rng = np.random.default_rng(7)
    for lookback in (28, 7):
        weeks = weekly_inputs(px, funding, lookback)
        print('=' * 110 + f'\nLOOKBACK {lookback} DAYS' + ('  (primary)' if lookback == 28 else '  (descriptive only)'))
        r50 = backtest(weeks, all_coins, momentum)
        r35 = backtest(weeks, others, momentum)
        show('50 coins', r50)
        show('35 unseen coins', r35)
        if lookback != 28:
            continue
        sims = []
        for _ in range(N_RANDOM):
            rr = backtest(weeks, all_coins, lambda sc: list(rng.permutation(sc.index)))
            sims.append(rr.mean() / rr.std() * np.sqrt(52))
        sims = np.array(sims)
        real = stats(r50)['sharpe']
        c1 = all(stats(r50[m])['ann'] > 0 for m in (r50.index < SPLIT, r50.index >= SPLIT))
        c2 = all(stats(r35[m])['ann'] > 0 for m in (r35.index < SPLIT, r35.index >= SPLIT))
        c3 = (real > sims).mean() >= 0.95
        print(f"\n  random weekly rankings: Sharpe median {np.median(sims):+.2f}, 95th pct {np.percentile(sims, 95):+.2f}; real {real:+.2f} beats {(real > sims).mean()*100:.1f}%")
        print(f"  (1) 50-coin both periods > 0: {c1}   (2) 35-coin both periods > 0: {c2}   (3) beats >= 95% random: {c3}")
        print(f"  XS MOMENTUM 28d {'PASSES' if (c1 and c2 and c3) else 'FAILS'}")


if __name__ == '__main__':
    main()
