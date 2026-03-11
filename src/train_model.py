

import ccxt
import pandas as pd
import numpy as np
from src.features import extract_features, prepare_labels
from src.ml_model import CryptoMLModel
from datetime import datetime, timedelta

def fetch_historical_data(symbol, days=180, timeframe='1h'):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    while since < exchange.milliseconds():
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        since = ohlcv[-1][0] + 1
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def train():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    all_features = []
    all_labels = []
    
    print("Fetching BTC data for relative strength...")
    btc_df = fetch_historical_data('BTC/USDT')
    
    for symbol in symbols:
        print(f"Processing {symbol}...")
        df = fetch_historical_data(symbol)
        
        features = extract_features(df, btc_df)
        labels = prepare_labels(df, horizon=4) # 4 hour horizon
        
        # Align features and labels
        common_index = features.index.intersection(labels.index)
        all_features.append(features.loc[common_index])
        all_labels.append(labels.loc[common_index])
        
    X = pd.concat(all_features)
    y = pd.concat(all_labels)
    
    print(f"Total dataset size: {len(X)}")
    
    model = CryptoMLModel()
    model.train(X, y)

if __name__ == "__main__":
    train()

