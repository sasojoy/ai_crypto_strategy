import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import pandas_ta as ta
import os
import joblib
from sklearn.preprocessing import StandardScaler

class ModelTrainer:
    def __init__(self, data_dir='/workspace/ai_crypto_strategy/data', model_dir='/workspace/ai_crypto_strategy/models'):
        self.data_dir = data_dir
        self.model_dir = model_dir

    def load_data(self, symbol, timeframe):
        path = os.path.join(self.data_dir, f"{symbol.replace('/', '_')}_{timeframe}.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Data file not found: {path}")
        return pd.read_parquet(path)

    def feature_engineering(self, df, df_4h=None):
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 1. Donchian Channel (24h = 24 * 1h)
        df['upper_band'] = df['high'].rolling(window=24).max().shift(1)
        df['lower_band'] = df['low'].rolling(window=24).min().shift(1)

        # 2. ATR (14) for Trailing Stop
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr_pct'] = df['atr'] / df['close']

        # 3. Trend Filter (EMA200)
        df['ema200'] = ta.ema(df['close'], length=200)
        df['trend_up'] = df['close'] > df['ema200']
        df['trend_down'] = df['close'] < df['ema200']

        # 4. Breakout Signals
        df['is_long_breakout'] = (df['close'] > df['upper_band']) & df['trend_up']
        df['is_short_breakout'] = (df['close'] < df['lower_band']) & df['trend_down']

        # Labeling: 180.0 Trend Breakout (Future 24h return)
        df['target_long'] = np.where(df['is_long_breakout'] & (df['close'].shift(-24) > df['close']), 1, 0)
        df['target_short'] = np.where(df['is_short_breakout'] & (df['close'].shift(-24) < df['close']), 1, 0)
        df['target'] = df['target_long'] | df['target_short']

        return df

    def train(self, df, model_name='ensemble_model.joblib', split_date=None):
        features = ['atr_pct', 'trend_up']
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        if split_date:
            split_dt = pd.to_datetime(split_date)
            train_df = df[df['timestamp'] < split_dt]
            test_df = df[df['timestamp'] >= (split_dt + pd.Timedelta(hours=12))]
        else:
            split_idx = int(len(df) * 0.8)
            train_df = df.iloc[:split_idx]
            test_df = df.iloc[split_idx + 12:]

        if train_df.empty or test_df.empty:
            # Fallback for small data
            train_df = df
            test_df = df

        X_train, y_train = train_df[features], train_df['target']
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        joblib.dump(scaler, os.path.join(self.model_dir, 'scaler.joblib'))

        print(f'Training Random Forest 180.0 Model on {len(X_train)} samples...')
        model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X_train_scaled, y_train)

        joblib.dump(model, os.path.join(self.model_dir, model_name))
        print(f'Model saved to {os.path.join(self.model_dir, model_name)}')

if __name__ == '__main__':
    trainer = ModelTrainer()
