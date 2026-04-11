import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import pandas_ta as ta
import os
import joblib
import argparse

class ModelTrainer:
    def __init__(self, data_dir='/workspace/ai_crypto_strategy/data', model_dir='/workspace/ai_crypto_strategy/models'):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.features = ['adx', 'rsi', 'bb_width', 'volatility_ratio', 'hist']

    def feature_engineering(self, df):
        df = df.copy()
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['volatility_ratio'] = df['atr'] / df['atr'].rolling(50).mean()
        
        # RSI & ADX
        df['rsi'] = ta.rsi(df['close'], length=14)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['adx'] = adx_df['ADX_14']
        
        # Bollinger Bands
        bb = ta.bbands(df['close'], length=20, std=2)
        df['bb_lower'] = bb.iloc[:, 0]
        df['bb_mid'] = bb.iloc[:, 1]
        df['bb_upper'] = bb.iloc[:, 2]
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
        
        # Trend Filters
        df['ema_20'] = df['close'].ewm(span=20).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        df['ema_200_4h'] = df['close'].ewm(span=800).mean()
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        macd = ema12 - ema26
        signal_macd = macd.ewm(span=9).mean()
        df['hist'] = macd - signal_macd
        
        # Target Labeling: 12 bars later price > current price * 1.01 (1% profit)
        df['target'] = (df['close'].shift(-12) > df['close'] * 1.01).astype(int)
        return df.dropna()

    def train(self, df, model_name='ensemble_model.joblib'):
        X = df[self.features]
        y = df['target']
        model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X, y)
        os.makedirs(self.model_dir, exist_ok=True)
        joblib.dump(model, os.path.join(self.model_dir, model_name))
        print(f'Model saved to {os.path.join(self.model_dir, model_name)}')

if __name__ == '__main__':
    from data.fetcher import BinanceFetcher
    fetcher = BinanceFetcher()
    df_raw = fetcher.fetch_ohlcv('BTCUSDT', '1h', limit=4000)
    trainer = ModelTrainer()
    df = trainer.feature_engineering(df_raw)
    trainer.train(df)
