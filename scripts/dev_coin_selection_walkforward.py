"""
DEV-WINDOW ONLY (< 2026-01-01). Does PICKING coins for the v7 signal work,
done the way it would be done live? (User, 2026-09-30: the goal is to
select the coins that suit our strategy, then keep optimizing on them.)

Walk-forward, rolling: at the start of each test year Y (2022..2025), rank
the 15 candidate coins using ONLY the two previous years' v7 trades, pick
coins by a fixed rule, and trade only those in year Y. Compare with
trading all 15, with the current fixed 5 (BTC ETH SOL NEAR AVAX), and with
random picks of the same size.

Selection rules (pre-registered):
  top5_avgR      the 5 coins with the best lookback avgR (n >= 30)
  positive       every coin with lookback avgR > 0 (n >= 30)
  top5_consist   the 5 coins with the most positive lookback QUARTERS
                 (ties broken by avgR) -- consistency over raw average

Signal: v7 locked spec, close-of-bar entry proxy (dev_coin_personality.py
mom_trades), SL 2xATR / TP 4xATR, 0.14% friction, results in R.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi
from dev_coin_personality import ORIGINAL, MAJORS, load, mom_trades

TEST_YEARS = [2022, 2023, 2024, 2025]
LOOKBACK_YEARS = 2
MIN_N = 30
N_RANDOM = 5000


def build():
    parts = []
    for b in ORIGINAL + MAJORS:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        t = mom_trades(df)
        t['coin'] = b
        parts.append(t)
    t = pd.concat(parts, ignore_index=True)
    t['year'] = t.time.dt.year
    t['q'] = t.time.dt.to_period('Q')
    return t


def pick(t, year, rule):
    lb = t[(t.year >= year - LOOKBACK_YEARS) & (t.year < year)]
    g = lb.groupby('coin')
    s = pd.DataFrame({'n': g.size(), 'avgR': g.r.mean(),
                      'pos_q': lb.groupby(['coin', 'q']).r.sum().gt(0).groupby('coin').sum()})
    s = s[s.n >= MIN_N]
    if rule == 'top5_avgR':
        return list(s.nlargest(5, 'avgR').index)
    if rule == 'positive':
        return list(s[s.avgR > 0].index)
    if rule == 'top5_consist':
        return list(s.sort_values(['pos_q', 'avgR'], ascending=False).head(5).index)
    raise ValueError(rule)


def main():
    t = build()
    coins = sorted(t.coin.unique())
    rng = np.random.default_rng(9)
    rules = ['top5_avgR', 'positive', 'top5_consist']
    print('=' * 110 + '\nWALK-FORWARD COIN SELECTION (pick with the previous 2 years, trade the next year)')
    print(f"{'year':>4} {'all 15':>16} {'fixed orig 5':>16} " + ' '.join(f"{r:>28}" for r in rules))
    totals = {k: [] for k in ['all', 'orig'] + rules}
    beats = {r: 0 for r in rules}
    pct_vs_random = {r: [] for r in rules}
    for y in TEST_YEARS:
        ty = t[t.year == y]
        all_ = ty.r
        orig = ty[ty.coin.isin(ORIGINAL)].r
        cells = [f"{all_.mean():+.3f} ({len(all_):4d})", f"{orig.mean():+.3f} ({len(orig):4d})"]
        totals['all'].append(all_)
        totals['orig'].append(orig)
        for r in rules:
            chosen = pick(t, y, r)
            sel = ty[ty.coin.isin(chosen)].r
            totals[r].append(sel)
            k = len(chosen)
            rand = [ty[ty.coin.isin(rng.choice(coins, k, replace=False))].r.mean() for _ in range(N_RANDOM // 10)]
            pct = (sel.mean() > np.array(rand)).mean() * 100
            pct_vs_random[r].append(pct)
            beats[r] += sel.mean() > all_.mean()
            cells.append(f"{sel.mean():+.3f} ({len(sel):4d}) k={k:2d} r{pct:3.0f}%")
        print(f"{y:>4} {cells[0]:>16} {cells[1]:>16} " + ' '.join(f"{c:>28}" for c in cells[2:]))
    print('      format: avgR (n);  k = coins picked;  r = beats that % of random picks of the same size')

    print('\n' + '=' * 110 + '\nPOOLED 2022-2025')
    for k, v in totals.items():
        x = pd.concat(v)
        pf = x[x > 0].sum() / -x[x < 0].sum()
        extra = f"   beat 'all 15' in {beats[k]}/{len(TEST_YEARS)} years, mean random-percentile {np.mean(pct_vs_random[k]):.0f}%" if k in beats else ''
        print(f"  {k:14s} n={len(x):5d} win={(x > 0).mean()*100:5.1f}% avgR={x.mean():+.3f} PF={pf:.3f} totalR={x.sum():+7.1f}{extra}")

    print('\n' + '=' * 110 + '\nWHICH COINS GOT PICKED (top5_consist / top5_avgR)')
    for y in TEST_YEARS:
        print(f"  {y}: consist={pick(t, y, 'top5_consist')}   avgR={pick(t, y, 'top5_avgR')}")

    print('\n' + '=' * 110 + '\nPER COIN, per year avgR (for reference)')
    print(t.pivot_table(index='coin', columns='year', values='r', aggfunc='mean').round(3).to_string())


if __name__ == '__main__':
    main()
