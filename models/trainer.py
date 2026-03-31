



import pandas as pd
import numpy as np
import lightgbm as lgb
import pandas_ta as ta
import os
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

class ModelTrainer:
    def __init__(self, data_dir='/workspace/ai_crypto_strategy/data', model_dir='/workspace/ai_crypto_strategy/models'):
        self.data_dir = data_dir
        self.model_dir = model_dir

    def load_data(self, symbol, timeframe):
        """
        Load Parquet data.
        """
        path = os.path.join(self.data_dir, f"{symbol.replace('/', '_')}_{timeframe}.parquet")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Data file not found: {path}")
        return pd.read_parquet(path)

    def feature_engineering(self, df_btc, df_eth):
        """
        Add technical indicators and BTC/ETH ratio.
        """
        # Ensure timestamps align
        df = pd.merge(df_btc, df_eth, on='timestamp', suffixes=('_btc', '_eth'))
        
        # BTC Indicators
        df['rsi_btc'] = ta.rsi(df['close_btc'], length=14)
        df['atr_btc'] = ta.atr(df['high_btc'], df['low_btc'], df['close_btc'], length=14)
        macd = ta.macd(df['close_btc'])
        df['macd_btc'] = macd['MACD_12_26_9']
        
        # BTC/ETH Ratio
        df['btc_eth_ratio'] = df['close_btc'] / df['close_eth']
        df['ratio_sma'] = ta.sma(df['btc_eth_ratio'], length=20)
        
        # Target: Next 4 bars (1 hour if 15m data) return > 0.5%
        # For 1h data, next 4 bars would be 4 hours. Let's assume 15m data for training.
        df['target_return'] = df['close_btc'].shift(-4) / df['close_btc'] - 1
        df['target'] = (df['target_return'] > 0.005).astype(int)
        
        # Drop NaNs from indicators and target
        df.dropna(inplace=True)
        
        return df

    def train(self, df, model_name='lgbm_model.joblib'):
        """
        Train LightGBM model with Walk-forward split.
        """
        features = ['rsi_btc', 'atr_btc', 'macd_btc', 'btc_eth_ratio', 'ratio_sma']
        X = df[features]
        y = df['target']
        
        # Walk-forward split: Train on first 80%, test on last 20%
        split_idx = int(len(df) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        print(f"Training on {len(X_train)} samples, testing on {len(X_test)} samples...")
        
        model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, num_leaves=31)
        model.fit(X_train, y_train)
        
        # Evaluation
        y_pred = model.predict(X_test)
        print(f"Accuracy: {accuracy_score(y_test, y_pred)}")
        print(classification_report(y_test, y_pred))
        
        # Save model
        joblib.dump(model, os.path.join(self.model_dir, model_name))
        print(f"Model saved to {os.path.join(self.model_dir, model_name)}")

if __name__ == "__main__":
    trainer = ModelTrainer()
    try:
        df_btc = trainer.load_data('BTCUSDT', '15m')
        df_eth = trainer.load_data('ETHUSDT', '15m')
        df = trainer.feature_engineering(df_btc, df_eth)
        trainer.train(df)
    except Exception as e:
        print(f"Error during training: {e}")



