"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向D", 2026-10-17). DEV WINDOW
ONLY (< 2026-01-01). 50 coins, Binance USDT-M 5-minute klines
(data/backtest_cache/universe_5m, from fetch_5m_universe.py).

  m_t  = sum of the last 3 five-minute log returns (a 15-minute move)
  z_t  = m_t / (std of the previous 288 five-minute returns * sqrt(3)),
         causal (shifted one bar), >= 144 bars of history
  extreme: |z_t| > 2, no re-trigger within 3 bars of the same coin

  H_D1  statistical reversal: mean(-sign(z_t) * log(c[t+3]/c[t])) > 0
  H_D2  maker-tradable: limit order at c[t] against the move; filled only
        if bar t+1 trades through it by 2 bp (buy: low < P*(1-2e-4)),
        otherwise cancelled; exit at market at close of bar t+4
        (3 bars after the fill bar). Cost: maker 0.02% in, taker 0.05% +
        0.02% slippage out = 0.09% round trip. mean net return > 0.

Inference: trades averaged per coin x day first (same-day trades of a coin
are correlated), then one-sided t-test and 10,000x bootstrap on that
series. Pass (each hypothesis, Bonferroni alpha 0.025): mean > 0, p < 0.025,
same sign in 2020-23 and 2024-25, same sign in the 15-coin and 35-coin
subsamples. Breakdowns are printed only after a pass; nothing is re-tuned.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U5M = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_5m')
SPLIT = pd.Timestamp('2024-01-01')
Z_CUT = 2.0
COOLDOWN = 3
HOLD = 3
THROUGH = 2e-4
COST = 0.0009
N_BOOT = 10000
ALPHA = 0.025
SEED = 20261017


def coin_list():
    basket = ORIGINAL + MAJORS
    files = sorted(f.split('_USDT_')[0] for f in os.listdir(U5M) if f.endswith('_5m.csv'))
    return [(b, '15' if b in basket else '35') for b in files]


def trades_for(base):
    df = pd.read_csv(os.path.join(U5M, f'{base}_USDT_5m.csv'), parse_dates=['timestamp'])
    df = df[df['timestamp'] < '2026-01-01'].reset_index(drop=True)
    c, h, l = df['close'].values, df['high'].values, df['low'].values
    r = np.log(df['close']).diff()
    m = r.rolling(3).sum()
    sd = r.rolling(288, min_periods=144).std().shift(1)
    z = (m / (sd * np.sqrt(3))).values
    idx = np.where(np.abs(z) > Z_CUT)[0]
    rows, last = [], -10
    n = len(c)
    for t in idx:
        if t - last < COOLDOWN or t + HOLD + 1 >= n:
            continue
        last = t
        d = -np.sign(z[t])
        y1 = d * np.log(c[t + HOLD] / c[t])
        P = c[t]
        filled = (l[t + 1] < P * (1 - THROUGH)) if d > 0 else (h[t + 1] > P * (1 + THROUGH))
        y2 = d * np.log(c[t + 1 + HOLD] / P) - COST if filled else np.nan
        rows.append((df['timestamp'].iloc[t], d, z[t], y1, filled, y2))
    out = pd.DataFrame(rows, columns=['time', 'dir', 'z', 'y1', 'filled', 'y2'])
    out['coin'] = base
    return out


def infer(series, rng):
    g = series.dropna().values
    if len(g) < 30:
        return np.nan, np.nan, np.nan, len(g)
    mean = g.mean()
    t = mean / (g.std(ddof=1) / np.sqrt(len(g)))
    boot = rng.choice(g, size=(N_BOOT, len(g)), replace=True).mean(axis=1)
    return mean, t, (boot <= 0).mean(), len(g)


def run(d, col, name, rng):
    print(f'\n=== {name} ===')
    d = d.dropna(subset=[col])
    grp = d.groupby(['coin', 'day', 'sample', 'period'])[col].mean().reset_index()
    res = {}
    for label, sub in [('all', grp), ('15', grp[grp['sample'] == '15']), ('35', grp[grp['sample'] == '35'])]:
        for per in ['2020-23', '2024-25', 'full']:
            s = sub if per == 'full' else sub[sub['period'] == per]
            mean, t, p, n = infer(s[col], rng)
            res[(label, per)] = (mean, p)
            print(f'  {label:>3} {per:8} mean={mean*1e4:+7.2f} bp  t={t:+5.2f}  p={p:.4f}  coin-days={n}')
    ok = (res[('all', 'full')][0] > 0 and res[('all', 'full')][1] < ALPHA
          and res[('all', '2020-23')][0] > 0 and res[('all', '2024-25')][0] > 0
          and res[('15', 'full')][0] > 0 and res[('35', 'full')][0] > 0)
    print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}')
    return ok


def breakdown(d, col):
    d = d.dropna(subset=[col]).copy()
    years = (d['time'].max() - d['time'].min()).days / 365.25
    print(f'    trades={len(d)}  per year={len(d)/years:.0f}  mean={d[col].mean()*1e4:+.2f} bp  '
          f'sum={d[col].sum()*100:+.1f}%  win={ (d[col]>0).mean()*100:.1f}%')
    top3 = d[col].nlargest(3).sum() / d[col].clip(lower=0).sum() * 100
    print(f'    top-3 share of gross gains={top3:.1f}%')
    for lab, mask in [('long (after drop)', d['dir'] > 0), ('short (after spike)', d['dir'] < 0)]:
        print(f'    {lab:22} n={mask.sum()}  mean={d.loc[mask, col].mean()*1e4:+.2f} bp')
    hr = d['time'].dt.hour
    for lab, mask in [('02-04 UTC low-vol', hr.isin([2, 3, 4])), ('13-16 UTC high-vol', hr.isin([13, 14, 15, 16]))]:
        print(f'    {lab:22} n={mask.sum()}  mean={d.loc[mask, col].mean()*1e4:+.2f} bp')
    for y, g in d.groupby(d['time'].dt.year):
        print(f'    {y}: n={len(g)}  mean={g[col].mean()*1e4:+.2f} bp  sum={g[col].sum()*100:+.1f}%')


def main():
    rng = np.random.default_rng(SEED)
    parts = []
    for base, sample in coin_list():
        t = trades_for(base)
        t['sample'] = sample
        parts.append(t)
        print(f'{base}: {len(t)} extremes, fill rate {t["filled"].mean()*100:.0f}%', flush=True)
    d = pd.concat(parts, ignore_index=True)
    d['day'] = d['time'].dt.floor('D')
    d['period'] = np.where(d['time'] < SPLIT, '2020-23', '2024-25')
    print(f'\ncoins={d.coin.nunique()}  extremes={len(d)}  filled={int(d.filled.sum())}')

    ok1 = run(d, 'y1', 'H_D1 statistical 15-min reversal after |z|>2', rng)
    ok2 = run(d, 'y2', 'H_D2 maker-entry tradable (net of 0.09%)', rng)
    if ok1:
        print('\n  H_D1 breakdown (gross, no cost):')
        breakdown(d, 'y1')
    if ok2:
        print('\n  H_D2 breakdown (net):')
        breakdown(d, 'y2')
    d.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'intraday_reversal_trades.csv'), index=False)


if __name__ == '__main__':
    main()
