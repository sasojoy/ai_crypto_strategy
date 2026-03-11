


import pandas as pd
import numpy as np
from src.features import extract_features, prepare_labels
from src.ml_model import CryptoMLModel
from src.train_model import fetch_historical_data
from datetime import datetime, timedelta

def run_validation(days=30):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT']
    ml_model = CryptoMLModel()
    ml_model.load()
    
    if not ml_model.is_trained:
        print("❌ Model not trained. Cannot run validation.")
        return

    print(f"🔍 Running AI Validation for the last {days} days...")
    
    btc_df = fetch_historical_data('BTC/USDT', days=days+5) # Extra days for indicators
    
    all_results = []
    
    for symbol in symbols:
        print(f"Processing {symbol}...")
        df = fetch_historical_data(symbol, days=days+5)
        
        features = extract_features(df, btc_df)
        labels = prepare_labels(df, horizon=4)
        
        common_index = features.index.intersection(labels.index)
        X = features.loc[common_index]
        y = labels.loc[common_index]
        
        probs = ml_model.predict_proba(X)
        
        df_res = pd.DataFrame({
            'prob': probs,
            'actual': y
        }, index=common_index)
        
        all_results.append(df_res)
        
    full_res = pd.concat(all_results)
    
    # Analysis
    high_conf = full_res[full_res['prob'] > 0.65]
    low_conf = full_res[full_res['prob'] <= 0.65]
    
    print("\n" + "="*30)
    print("📊 AI VALIDATION REPORT (Last 30 Days)")
    print("="*30)
    print(f"Total Samples: {len(full_res)}")
    print(f"Overall Win Rate: {full_res['actual'].mean()*100:.2f}%")
    print("-" * 30)
    print(f"High Confidence (Score > 0.65) Count: {len(high_conf)}")
    if len(high_conf) > 0:
        print(f"High Confidence Win Rate: {high_conf['actual'].mean()*100:.2f}%")
    else:
        print("High Confidence Win Rate: N/A")
    print("-" * 30)
    print(f"Low Confidence (Score <= 0.65) Count: {len(low_conf)}")
    print(f"Low Confidence Win Rate: {low_conf['actual'].mean()*100:.2f}%")
    print("="*30)

if __name__ == "__main__":
    run_validation(30)


