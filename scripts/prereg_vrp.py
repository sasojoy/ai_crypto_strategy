"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向B：波動率風險溢酬", 2026-10-17).
DEV WINDOW 2021-03-24 .. 2025-12-31 (2026 untouched).

IV_t: Deribit DVOL (30-day implied vol index, annualised %) at 00:00 UTC.
RV_t: realised vol of the NEXT 720 hourly log returns (Binance perp 1H),
      annualised % = sqrt(sum(r^2) * 8766 / 720) * 100.
Non-overlapping 30-day windows from 2021-03-24 for inference.

  H_B1  mean(IV - RV) > 0
  H_B2  mean(IV - RV - 2) > 0   (2 vol points per window = assumed cost)

Pass (each, alpha 0.025 one-sided): BTC > 0 and ETH > 0, pooled bootstrap
p < 0.025, same sign in 2021-23 and 2024-25. Breakdowns only after a pass.
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
START, END = pd.Timestamp('2021-03-24'), pd.Timestamp('2026-01-01')
SPLIT = pd.Timestamp('2024-01-01')
WINDOW_H = 720
COST = 2.0
N_BOOT = 10000
ALPHA = 0.025
SEED = 20261017


def series(cur):
    iv = pd.read_csv(os.path.join(CACHE, 'deribit', f'{cur}_dvol_1h.csv'), parse_dates=['timestamp']).set_index('timestamp')['close']
    px = pd.read_csv(os.path.join(CACHE, f'{cur}_USDT_1h_full.csv'), parse_dates=['timestamp']).set_index('timestamp')['close']
    r2 = np.log(px).diff() ** 2
    # forward 720-bar realised variance, aligned to the window's START hour
    fwd = r2[::-1].rolling(WINDOW_H).sum()[::-1].shift(-1)
    rv = np.sqrt(fwd * 8766 / WINDOW_H) * 100
    d = pd.DataFrame({'iv': iv, 'rv': rv}).dropna()
    d = d[(d.index >= START) & (d.index + pd.Timedelta(hours=WINDOW_H) < END)]
    daily = d[d.index.hour == 0].copy()
    daily['vrp'] = daily['iv'] - daily['rv']
    nonov = daily.iloc[::30].copy()
    nonov['cur'] = cur
    nonov['period'] = np.where(nonov.index < SPLIT, '2021-23', '2024-25')
    return daily, nonov


def infer(x, rng):
    x = np.asarray(x, float)
    mean = x.mean()
    t = mean / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, size=(N_BOOT, len(x)), replace=True).mean(axis=1)
    return mean, t, (boot <= 0).mean(), len(x)


def main():
    rng = np.random.default_rng(SEED)
    dailies, nonovs = {}, []
    for cur in ['BTC', 'ETH']:
        daily, nonov = series(cur)
        dailies[cur] = daily
        nonovs.append(nonov)
        print(f'{cur}: daily obs {len(daily)} ({daily.index[0].date()} .. {daily.index[-1].date()}), non-overlapping windows {len(nonov)}')
    pool = pd.concat(nonovs)

    for name, col_fn in [('H_B1 IV - RV', lambda x: x['vrp']), ('H_B2 IV - RV - 2 (cost)', lambda x: x['vrp'] - COST)]:
        print(f'\n=== {name} (non-overlapping 30-day windows, vol points) ===')
        res = {}
        for label, sub in [('pooled', pool), ('BTC', pool[pool.cur == 'BTC']), ('ETH', pool[pool.cur == 'ETH'])]:
            for per in ['2021-23', '2024-25', 'full']:
                s = sub if per == 'full' else sub[sub.period == per]
                mean, t, p, n = infer(col_fn(s), rng)
                res[(label, per)] = (mean, p)
                print(f'  {label:6} {per:8} mean={mean:+6.2f}  t={t:+5.2f}  p={p:.4f}  n={n}')
        ok = (res[('pooled', 'full')][0] > 0 and res[('pooled', 'full')][1] < ALPHA
              and res[('BTC', 'full')][0] > 0 and res[('ETH', 'full')][0] > 0
              and res[('pooled', '2021-23')][0] > 0 and res[('pooled', '2024-25')][0] > 0)
        print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}')
        if ok:
            x = col_fn(pool)
            print(f'    positive windows: {(x > 0).mean()*100:.0f}%')
            worst = pool.assign(pnl=x).nsmallest(5, 'pnl')
            print('    worst 5 windows:')
            for ts, row in worst.iterrows():
                print(f'      {row.cur} {ts.date()}  IV={row.iv:5.1f}  RV={row.rv:5.1f}  pnl={row.pnl:+6.1f}')
            for cur in ['BTC', 'ETH']:
                s = pool[pool.cur == cur].sort_index()
                eq = (col_fn(s)).cumsum()
                dd = (eq - eq.cummax()).min()
                print(f'    {cur}: cum pnl per unit vega={eq.iloc[-1]:+.1f} vol-pts over {len(s)} windows, max drawdown={dd:+.1f}')
            d = pool.copy()
            d['pnl'] = x
            d['iv_q'] = pd.qcut(d['iv'], 3, labels=['low IV', 'mid IV', 'high IV'])
            print('    by IV tercile (descriptive):', {k: round(v, 2) for k, v in d.groupby('iv_q', observed=True)['pnl'].mean().items()})
            for y, g in d.groupby(d.index.year):
                print(f'    {y}: n={len(g)}  mean={g.pnl.mean():+.2f}  positive={(g.pnl>0).mean()*100:.0f}%')


if __name__ == '__main__':
    main()
