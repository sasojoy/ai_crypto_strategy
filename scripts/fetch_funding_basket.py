"""
Fetches Binance USDT-M funding-rate history (2020-01-01 .. 2025-12-31, dev
window only) for the 15-coin optimization basket
(dev_coin_personality.py: ORIGINAL + MAJORS).

Output: data/backtest_cache/funding_basket/<BASE>_USDT_funding.csv
        columns: timestamp (funding settlement time, UTC), funding_rate
"""
import os
import sys
import time

import ccxt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'data', 'backtest_cache', 'funding_basket')
START = '2020-01-01T00:00:00Z'
END = pd.Timestamp('2026-01-01')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    for base in ORIGINAL + MAJORS:
        path = os.path.join(OUT_DIR, f'{base}_USDT_funding.csv')
        if os.path.exists(path):
            print(f'  {base}: cached', flush=True)
            continue
        rows, since = [], ex.parse8601(START)
        while True:
            batch = ex.fetch_funding_rate_history(f'{base}/USDT:USDT', since=since, limit=1000)
            if not batch:
                break
            rows += [(b['timestamp'], b['fundingRate']) for b in batch]
            since = batch[-1]['timestamp'] + 1
            if pd.Timestamp(batch[-1]['timestamp'], unit='ms') >= END:
                break
        df = pd.DataFrame(rows, columns=['timestamp', 'funding_rate'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[df['timestamp'] < END].drop_duplicates('timestamp').sort_values('timestamp')
        df.to_csv(path, index=False)
        print(f"  {base}: {len(df)} rows from {df['timestamp'].min()}", flush=True)
        time.sleep(0.2)


if __name__ == '__main__':
    main()
