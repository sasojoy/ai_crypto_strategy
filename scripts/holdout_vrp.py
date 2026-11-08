"""
ONE-SHOT 2026 HOLDOUT for the volatility risk premium (RESEARCH_FINDINGS.md
"新方向B", registered 2026-10-17, commit 9b106d4). BTC only (ETH failed
2024-25 in the dev window and is not sent).

Same definitions as prereg_vrp.py: IV = DVOL at 00:00 UTC, RV = realised
vol of the next 720 hourly returns, non-overlapping 30-day windows from
2026-01-01. Price: *_1h_full.csv (to 2026-09-08) extended with
data/forward/*_1h.csv (to the latest hour).
Pass: BTC mean(IV - RV - 2) > 0. ~9 windows, so every window is printed.
Known leak: 2026 Q2-Q3 was already known to be a low-volatility period.
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
START = pd.Timestamp('2026-01-01')
WINDOW_H = 720
COST = 2.0


def main():
    cur = 'BTC'
    iv = pd.read_csv(os.path.join(CACHE, 'deribit', f'{cur}_dvol_1h.csv'), parse_dates=['timestamp']).set_index('timestamp')['close']
    full = pd.read_csv(os.path.join(CACHE, f'{cur}_USDT_1h_full.csv'), parse_dates=['timestamp'])
    fwd = pd.read_csv(os.path.join(ROOT, 'data', 'forward', f'{cur}_USDT_1h.csv'), parse_dates=['timestamp'])
    px = pd.concat([full, fwd]).drop_duplicates('timestamp').sort_values('timestamp').set_index('timestamp')['close']
    r2 = np.log(px).diff() ** 2
    fv = r2[::-1].rolling(WINDOW_H).sum()[::-1].shift(-1)
    rv = np.sqrt(fv * 8766 / WINDOW_H) * 100
    d = pd.DataFrame({'iv': iv, 'rv': rv}).dropna()
    d = d[(d.index >= START) & (d.index.hour == 0)]
    w = d.iloc[::30].copy()
    w['pnl'] = w['iv'] - w['rv'] - COST
    print(f'{cur} 2026 holdout: price data to {px.index[-1]}, {len(w)} non-overlapping windows')
    for ts, row in w.iterrows():
        print(f'  {ts.date()}  IV={row.iv:5.1f}  RV={row.rv:5.1f}  net={row.pnl:+6.1f}')
    mean = w['pnl'].mean()
    t = mean / (w['pnl'].std(ddof=1) / np.sqrt(len(w)))
    print(f'  mean net={mean:+.2f} vol-pts  t={t:+.2f}  positive={(w.pnl > 0).mean()*100:.0f}%  gross mean={(w.iv - w.rv).mean():+.2f}')
    print(f'  -> {"PASS" if mean > 0 else "FAIL"}')


if __name__ == '__main__':
    main()
