"""
Fetches HOLDOUT data (1H OHLCV + funding, 2025-10-01 warm-up .. now) for
the 50 coins used in the short-crowding study (15-coin basket + 35 unseen
universe coins), for the pre-registered holdout test
(RESEARCH_FINDINGS.md, commit 3ac5767). Run only after that commit.

Output: data/backtest_cache/holdout_2026/<BASE>_USDT_1h.csv and
        <BASE>_USDT_funding.csv
"""
import os
import sys
import time

import ccxt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'data', 'backtest_cache', 'holdout_2026')
START = '2025-10-01T00:00:00Z'


def coins():
    ufund = os.path.join(ROOT, 'data', 'backtest_cache', 'funding_universe')
    return ORIGINAL + MAJORS + sorted(f.split('_USDT_')[0] for f in os.listdir(ufund) if f.endswith('_funding.csv'))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    now = ex.milliseconds()
    for b in coins():
        sym = f'{b}/USDT:USDT'
        rows, since = [], ex.parse8601(START)
        while since < now:
            batch = ex.fetch_ohlcv(sym, '1h', since=since, limit=1500)
            if not batch:
                break
            rows += batch
            since = batch[-1][0] + 1
        px = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        px['timestamp'] = pd.to_datetime(px['timestamp'], unit='ms')
        px.drop_duplicates('timestamp').to_csv(os.path.join(OUT_DIR, f'{b}_USDT_1h.csv'), index=False)

        rows, since = [], ex.parse8601(START)
        while since < now:
            batch = ex.fetch_funding_rate_history(sym, since=since, limit=1000)
            if not batch:
                break
            rows += [(x['timestamp'], x['fundingRate']) for x in batch]
            since = batch[-1]['timestamp'] + 1
            if len(batch) < 2:
                break
        fr = pd.DataFrame(rows, columns=['timestamp', 'funding_rate'])
        fr['timestamp'] = pd.to_datetime(fr['timestamp'], unit='ms')
        fr.drop_duplicates('timestamp').to_csv(os.path.join(OUT_DIR, f'{b}_USDT_funding.csv'), index=False)
        print(f"  {b}: {len(px)} bars to {px['timestamp'].max()}, {len(fr)} funding rows", flush=True)
        time.sleep(0.2)


if __name__ == '__main__':
    main()
