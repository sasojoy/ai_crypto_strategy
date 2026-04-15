import ccxt
import pandas as pd
import os
import time

exchange = ccxt.binance()
symbol = 'BTC/USDT'
timeframe = '1h'
limit = 5000
all_ohlcv = []
# 計算 5000 小時前的時間戳
since = exchange.milliseconds() - (limit * 60 * 60 * 1000)

print(f"Fetching {limit} candles of {symbol} {timeframe}...")
while len(all_ohlcv) < limit:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
    if not ohlcv:
        break
    all_ohlcv.extend(ohlcv)
    since = ohlcv[-1][0] + 1
    print(f"Fetched {len(all_ohlcv)}/{limit}...")
    time.sleep(0.1)

df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
if not os.path.exists('data'):
    os.makedirs('data')
df.to_csv('data/btc_wfo_data.csv', index=False)
print(f"Data saved to data/btc_wfo_data.csv. Total rows: {len(df)}")
