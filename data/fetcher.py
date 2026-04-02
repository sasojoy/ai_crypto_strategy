


import ccxt
import pandas as pd
import os
import yaml

class BinanceFetcher:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        self.exchange = ccxt.binance()
        self.symbols = self.config.get('symbol', ["BTCUSDT", "ETHUSDT"])
        self.timeframes = self.config.get('timeframes', ["1h", "15m"])
        self.data_dir = '/workspace/ai_crypto_strategy/data'

    def fetch_ohlcv(self, symbol, timeframe, limit=1000):
        """
        Fetch OHLCV data from Binance with correct historical pagination.
        """
        print(f"Fetching {symbol} {timeframe} data (Limit: {limit})...")
        
        # Calculate 'since' to get historical data
        duration_ms = limit * self.exchange.parse_timeframe(timeframe) * 1000
        since = self.exchange.milliseconds() - duration_ms
        
        all_ohlcv = []
        while len(all_ohlcv) < limit:
            fetch_limit = min(limit - len(all_ohlcv), 1000)
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=fetch_limit)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def save_to_parquet(self, df, symbol, timeframe):
        """
        Save DataFrame to Parquet file.
        """
        filename = f"{symbol.replace('/', '_')}_{timeframe}.parquet"
        path = os.path.join(self.data_dir, filename)
        df.to_parquet(path, index=False)
        print(f"Saved to {path}")

    def run(self):
        """
        Fetch and save data for all symbols and timeframes concurrently.
        """
        from concurrent.futures import ThreadPoolExecutor
        
        tasks = []
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                tasks.append((symbol, timeframe))
        
        def process_task(task):
            symbol, timeframe = task
            df = self.fetch_ohlcv(symbol, timeframe)
            self.save_to_parquet(df, symbol, timeframe)
            
        print(f"Starting concurrent download for {len(tasks)} tasks...")
        with ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as executor:
            executor.map(process_task, tasks)

if __name__ == "__main__":
    fetcher = BinanceFetcher()
    fetcher.run()


