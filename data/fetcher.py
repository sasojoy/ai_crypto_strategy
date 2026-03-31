


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
        Fetch OHLCV data from Binance.
        """
        print(f"Fetching {symbol} {timeframe} data...")
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
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
        Fetch and save data for all symbols and timeframes.
        """
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                df = self.fetch_ohlcv(symbol, timeframe)
                self.save_to_parquet(df, symbol, timeframe)

if __name__ == "__main__":
    fetcher = BinanceFetcher()
    fetcher.run()


