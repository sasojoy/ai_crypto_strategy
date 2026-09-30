"""
Fetches 4H OHLCV (Binance USDT-M perpetuals, 2020-01-01 .. 2025-12-31, i.e.
dev window only) for a wider coin universe, to re-test cup-and-handle
(scripts/dev_cup_handle.py) on coins it has never seen.

Universe rule (fixed before looking at any results): the top N_COINS USDT
perpetuals by current 24h quote volume among CRYPTO contracts only
(underlyingType == COIN, contractType == PERPETUAL -- Binance also lists
tokenized stocks/commodities) listed before LISTED_BEFORE (so every coin
has data in both 2020-23 and 2024-25), excluding stablecoin/fiat bases
and the 5 coins the original test used (BTC/ETH/SOL/NEAR/AVAX), so the new
sample is independent. Survivorship bias: today's top coins are survivors;
the cup test's controls use the same coins, so comparisons stay fair.

Output: data/backtest_cache/universe_4h/<BASE>_USDT_4h.csv
"""
import os
import time

import ccxt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_4h')
N_COINS = 45
START = '2020-01-01T00:00:00Z'
END = pd.Timestamp('2026-01-01')
LISTED_BEFORE = pd.Timestamp('2023-01-01')
EXCLUDE = {'BTC', 'ETH', 'SOL', 'NEAR', 'AVAX',
           'USDC', 'FDUSD', 'TUSD', 'BUSD', 'USDP', 'DAI', 'USDE', 'EUR', 'GBP'}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    markets = ex.load_markets()
    perps = [m for m in markets.values()
             if m.get('swap') and m.get('linear') and m['quote'] == 'USDT' and m.get('active')
             and m['base'] not in EXCLUDE
             and m['info'].get('underlyingType') == 'COIN' and m['info'].get('contractType') == 'PERPETUAL'
             and pd.Timestamp(int(m['info'].get('onboardDate', 0)), unit='ms') < LISTED_BEFORE]
    tickers = ex.fetch_tickers([m['symbol'] for m in perps])
    ranked = sorted(perps, key=lambda m: tickers.get(m['symbol'], {}).get('quoteVolume') or 0, reverse=True)
    chosen = ranked[:N_COINS]
    print('Universe:', ', '.join(m['base'] for m in chosen), flush=True)

    since0 = ex.parse8601(START)
    for m in chosen:
        path = os.path.join(OUT_DIR, f"{m['base']}_USDT_4h.csv")
        if os.path.exists(path):
            print(f"  {m['base']}: cached", flush=True)
            continue
        rows, since = [], since0
        while True:
            batch = ex.fetch_ohlcv(m['symbol'], '4h', since=since, limit=1500)
            if not batch:
                break
            rows += batch
            since = batch[-1][0] + 1
            if pd.Timestamp(batch[-1][0], unit='ms') >= END:  # page size varies (1000 seen), so don't infer "done" from it
                break
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[df['timestamp'] < END].drop_duplicates('timestamp')
        df.to_csv(path, index=False)
        print(f"  {m['base']}: {len(df)} bars from {df['timestamp'].min() if len(df) else '-'}", flush=True)
        time.sleep(0.2)


if __name__ == '__main__':
    main()
