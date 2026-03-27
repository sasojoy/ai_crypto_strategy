
import ccxt
import pandas as pd
import numpy as np
import joblib
import os
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from src.features import extract_features, prepare_labels
from datetime import datetime, timedelta

MODEL_PATH = 'models/model_v118_xgb.joblib'

def fetch_historical_data(symbol, days=180, timeframe='1h'):
    # Try to load from local data first
    local_path = f"/workspace/ai_crypto_strategy/data/{symbol.replace('/', '_')}_{timeframe}.csv"
    if os.path.exists(local_path):
        df = pd.read_csv(local_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff]
        if not df.empty:
            return df

    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())

    all_ohlcv = []
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            break

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def train_xgb():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'FET/USDT', 'AVAX/USDT']
    all_features = []
    all_labels = []

    print("Fetching BTC data for reference...")
    btc_df_1h = fetch_historical_data('BTC/USDT', timeframe='1h', days=180)
    btc_df_15m = fetch_historical_data('BTC/USDT', timeframe='15m', days=180)

    for symbol in symbols:
        print(f"Processing {symbol}...")
        # Use 1h for BTC/ETH, 15m for others
        tf = '1h' if symbol in ['BTC/USDT', 'ETH/USDT'] else '15m'
        df = fetch_historical_data(symbol, timeframe=tf, days=180)
        
        btc_ref = btc_df_1h if tf == '1h' else btc_df_15m
        # Align btc_ref with df
        btc_ref = btc_ref.reindex(df.index).ffill()

        features = extract_features(df, btc_ref)
        labels = prepare_labels(df, horizon=4 if tf == '1h' else 12) # 4h horizon

        common_index = features.index.intersection(labels.index)
        all_features.append(features.loc[common_index])
        all_labels.append(labels.loc[common_index])

    X = pd.concat(all_features)
    y = pd.concat(all_labels)

    print(f"Total dataset size: {len(X)}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )

    print("Training XGBoost model...")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(classification_report(y_test, y_pred))

    # Save model and feature names
    data = {
        'model': model,
        'feature_names': list(X.columns)
    }
    joblib.dump(data, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    # Feature Importance
    importances = model.feature_importances_
    feature_importance = pd.Series(importances, index=X.columns).sort_values(ascending=False)
    print("\nTop 5 Feature Importance:")
    print(feature_importance.head(5))

if __name__ == "__main__":
    train_xgb()
