
import pandas as pd
import numpy as np
from src.market import fetch_1h_data, CryptoMLModel
from src.features import extract_features

def validate():
    print("🔍 Validating Iteration 71.3 Fixes...")
    
    # 1. Load Model
    model = CryptoMLModel()
    model.load()
    if not model.is_trained:
        print("❌ Model not loaded!")
        return

    # 2. Fetch Data (Pre-warmup style)
    symbol = 'SOL/USDT'
    print(f"Fetching data for {symbol}...")
    df = fetch_1h_data(symbol, limit=500)
    btc_df = fetch_1h_data('BTC/USDT', limit=500)
    
    if df.empty or btc_df.empty:
        print("❌ Failed to fetch data")
        return

    # 3. Extract Features
    print("Extracting features...")
    features = extract_features(df, btc_df=btc_df)
    
    print(f"Feature shape: {features.shape}")
    print("Last feature row:")
    print(features.tail(1))

    # 4. Predict
    score = float(model.predict_proba(features.tail(1))[0])
    print(f"🤖 AI Prediction Score: {score:.2%}")
    
    if score == 0.5:
        print("⚠️ Score is still 50.00%. Checking for NaNs in features...")
        print(features.tail(1).isna().sum())
    else:
        print("✅ SUCCESS: Dynamic AI score detected!")

if __name__ == "__main__":
    validate()
