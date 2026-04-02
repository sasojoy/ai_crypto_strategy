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

        # 1. Z-Score Distance from EMA200 (15m)
        df['ema200'] = ta.ema(df['close'], length=200)
        df['std200'] = df['close'].rolling(200).std()
        df['z_score_dist'] = (df['close'] - df['ema200']) / (df['std200'] + 1e-9)

        # 2. RSI (15m) for Momentum Flip
        df['rsi'] = ta.rsi(df['close'], length=14)

        # 3. 4H Trend Filter (EMA200)
        if df_4h is not None:
            df_4h = df_4h.copy()
            df_4h['ema200_4h'] = ta.ema(df_4h['close'], length=200)
            df_4h = df_4h[['timestamp', 'ema200_4h']]
            df = pd.merge_asof(df.sort_values('timestamp'), df_4h.sort_values('timestamp'), on='timestamp', direction='backward')
            df['trend_up_4h'] = df['close'] > df['ema200_4h']
        else:
            df['trend_up_4h'] = True # Fallback

        # 4. Volume Climax & Stabilization (15m)
        df['vol_ma24'] = df['volume'].rolling(96).mean() # 24h = 96 * 15m
        df['vol_ratio'] = df['volume'] / (df['vol_ma24'] + 1e-9)
        
        # vol_climax: Volume > 2.0x 24h Average in the last 4 bars (1 hour)
        df['vol_climax'] = df['vol_ratio'].rolling(4).max() > 2.0
        # vol_stabilize: Current volume is between 0.8x and 1.2x 24h Average
        df['vol_stabilize'] = (df['vol_ratio'] > 0.8) & (df['vol_ratio'] < 1.2)

        # 3. ATR (14)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr_pct'] = df['atr'] / df['close']

        # 4. Confirmation Pattern (Hammer/Engulfing)
        df['is_hammer'] = np.where((df['high'] - df['low']) > 2 * (df['open'] - df['close']).abs(), 1, 0)
        df['is_engulfing'] = np.where((df['close'] > df['open'].shift(1)) & (df['open'] < df['close'].shift(1)), 1, 0)

        # Labeling: 15m Mean Reversion (Future 4h return to EMA200)
        # 4h = 16 * 15m
        # 168.0 Logic: Z < -1.5 AND RSI Crosses 30 AND 4H Trend Up
        df['rsi_prev'] = df['rsi'].shift(1)
        df['rsi_cross_30'] = (df['rsi_prev'] < 30) & (df['rsi'] >= 30)
        
        df['target'] = np.where((df['z_score_dist'] < -1.5) & (df['rsi_cross_30']) & (df['trend_up_4h']) & (df['close'].shift(-16) > df['close']), 1, 0)
        
        df.dropna(inplace=True)
        return df

    def train(self, df, model_name='ensemble_model.joblib', split_date=None):
        features = ['z_score_dist', 'vol_ratio', 'vol_climax', 'vol_stabilize', 'atr_pct', 'is_hammer', 'is_engulfing', 'rsi', 'trend_up_4h']
        
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
            raise ValueError("Train or Test set is empty. Check split_date or data size.")

        X_train, y_train = train_df[features], train_df['target']
        X_test, y_test = test_df[features], test_df['target']

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        joblib.dump(scaler, os.path.join(self.model_dir, 'scaler.joblib'))

        print(f'Training Random Forest 167.0 Model on {len(X_train)} samples...')
        model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42)
        model.fit(X_train_scaled, y_train)

        importances = model.feature_importances_
        print('\nFeature Importance (Random Forest):')
        max_imp = max(importances) if len(importances) > 0 and max(importances) > 0 else 1
        for f, imp in zip(features, importances):
            print(f'{f:<20}: {"#" * int(imp/max_imp*50)} ({imp})')

        joblib.dump(model, os.path.join(self.model_dir, model_name))
        print(f'Model saved to {os.path.join(self.model_dir, model_name)}')

if __name__ == '__main__':
    trainer = ModelTrainer()
