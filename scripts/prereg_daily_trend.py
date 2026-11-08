"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md, commit 12b1f25). DEV WINDOW ONLY.
New strategy candidate 2: daily trend following (Donchian), the classic
small-stake / large-payoff structure.

Daily UTC bars from 1H, 50 coins (15-coin basket + 35 unseen).
  entry   close above the previous 50-day high (long) / below the previous
          50-day low (short); one position per coin at a time
  stop    entry -/+ 2 x ATR(20d)
  exit    stop touched, or close below the previous 20-day low (long) /
          above the previous 20-day high (short); no target; max 365 days
  costs   0.14% round trip; R vs the initial stop distance
Random baseline: same coin, same direction mix, same exits, random entry
days, 1,000 matched draws.
Pass: (1) avgR > 0 in all 4 cells (2020-23 / 2024-25 x 15 / 35 coins);
(2) pooled avgR beats >= 95% of random draws; (3) pooled avgR still > 0
after removing the best 1% of trades.
Trades still open at the end of the dev window are excluded.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, ROUND_TRIP_FRICTION
from dev_coin_personality import ORIGINAL, MAJORS, load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')
MAX_HOLD = 365
N_RANDOM = 1000


def daily(df1h):
    x = df1h.set_index('timestamp').resample('1D').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna().reset_index()
    x = x[x['timestamp'] < '2026-01-01'].reset_index(drop=True)
    x['atr'] = compute_atr(x, length=20)
    x['hh50'] = x['high'].shift(1).rolling(50).max()
    x['ll50'] = x['low'].shift(1).rolling(50).min()
    x['hh20'] = x['high'].shift(1).rolling(20).max()
    x['ll20'] = x['low'].shift(1).rolling(20).min()
    return x


def exit_trade(x, t, sgn):
    """Returns (exit index, R) or None if the trade is still open at the end."""
    c, h, l, a = x['close'].values, x['high'].values, x['low'].values, x['atr'].values[t]
    hh20, ll20 = x['hh20'].values, x['ll20'].values
    entry = c[t]
    if np.isnan(a) or a <= 0:
        return None
    stop = entry - sgn * 2 * a
    risk = 2 * a / entry
    for j in range(t + 1, min(t + 1 + MAX_HOLD, len(c))):
        if (l[j] <= stop) if sgn > 0 else (h[j] >= stop):
            return j, (sgn * (stop - entry) / entry - ROUND_TRIP_FRICTION) / risk
        if (c[j] < ll20[j]) if sgn > 0 else (c[j] > hh20[j]):
            return j, (sgn * (c[j] - entry) / entry - ROUND_TRIP_FRICTION) / risk
        if j - t >= MAX_HOLD:
            return j, (sgn * (c[j] - entry) / entry - ROUND_TRIP_FRICTION) / risk
    return None


def real_trades(x):
    c, hh, ll = x['close'].values, x['hh50'].values, x['ll50'].values
    out, t = [], 0
    while t < len(x):
        if np.isnan(hh[t]):
            t += 1
            continue
        sgn = 1 if c[t] > hh[t] else (-1 if c[t] < ll[t] else 0)
        if sgn == 0:
            t += 1
            continue
        res = exit_trade(x, t, sgn)
        if res is None:
            break  # open at the end of the window
        out.append((x['timestamp'].iloc[t], sgn, res[1]))
        t = res[0] + 1  # one position at a time
    return out


def main():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    rng = np.random.default_rng(55)
    rows, pools = [], {}
    for b in basket + others:
        x = daily(load(b))
        for t, sgn, r in real_trades(x):
            rows.append(dict(coin=b, sample='15' if b in basket else '35', time=t, sgn=sgn, r=r))
        valid = np.nonzero(~np.isnan(x['hh50'].values) & ~np.isnan(x['atr'].values))[0]
        for sgn in (1, -1):
            picks = rng.choice(valid, size=min(600, len(valid)), replace=False)
            pools[(b, sgn)] = np.array([res[1] for i in picks if (res := exit_trade(x, i, sgn)) is not None])
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, '2020-23', '2024-25')

    def line(r):
        pf = r[r > 0].sum() / -r[r < 0].sum() if (r < 0).any() else np.inf
        return f"n={len(r):4d} win={(r > 0).mean()*100:5.1f}% avgR={r.mean():+.3f} PF={pf:4.2f} sumR={r.sum():+7.1f}"

    print('=' * 100 + '\nDAILY TREND FOLLOWING (Donchian 50 in / 20 out, 2 ATR initial stop)')
    c1 = True
    for p in ('2020-23', '2024-25'):
        for s in ('15', '35'):
            r = d[(d.period == p) & (d['sample'] == s)].r
            c1 &= r.mean() > 0
            print(f"  {p} {s}-coin: {line(r)}")
    print(f"  ALL:            {line(d.r)}")
    print(f"  longs avgR {d[d.sgn == 1].r.mean():+.3f} (n={int((d.sgn == 1).sum())})   shorts avgR {d[d.sgn == -1].r.mean():+.3f} (n={int((d.sgn == -1).sum())})")
    print(f"  biggest winners (R): {np.round(np.sort(d.r.values)[-5:][::-1], 1)}")

    counts = d.groupby(['coin', 'sgn']).size()
    sims = np.array([np.concatenate([rng.choice(pools[k], n) for k, n in counts.items() if len(pools[k])]).mean()
                     for _ in range(N_RANDOM)])
    beat = (d.r.mean() > sims).mean() * 100
    c2 = beat >= 95
    trimmed = np.sort(d.r.values)[:-max(1, int(round(len(d) * 0.01)))]
    c3 = trimmed.mean() > 0
    print(f"\n  (1) all 4 cells avgR > 0: {c1}")
    print(f"  (2) random baseline avgR median {np.median(sims):+.3f}; real beats {beat:.1f}% (need >= 95): {c2}")
    print(f"  (3) avgR without the best 1% of trades: {trimmed.mean():+.3f}: {c3}")
    print(f"  DAILY TREND {'PASSES' if (c1 and c2 and c3) else 'FAILS'}")
    d.to_csv(os.path.join(ROOT, 'scripts', 'daily_trend_trades.csv'), index=False)


if __name__ == '__main__':
    main()
