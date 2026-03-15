

import os
import pandas as pd
from src.market import fetch_1h_data, fetch_15m_data, extract_features
from src.ml_model import CryptoMLModel
from src.indicators import calculate_ema, calculate_macd

def diagnostic():
    print("🔍 [Diagnostic] Volume Logic & AI Confidence Audit")
    
    # 1. Check BTC Volume
    df_48h = fetch_1h_data('BTC/USDT', limit=48)
    vol_change_24h = 0
    if len(df_48h) >= 48:
        last_24h_vol = df_48h.iloc[-24:]['volume'].sum()
        prev_24h_vol = df_48h.iloc[-48:-24]['volume'].sum()
        if prev_24h_vol > 0:
            vol_change_24h = (last_24h_vol - prev_24h_vol) / prev_24h_vol * 100
    
    print(f"📊 BTC 24H Volume Change: {vol_change_24h:.2f}%")
    
    # 2. Determine Regime
    regime = "震盪防禦"
    if vol_change_24h > 15:
        regime = "多頭追擊"
    elif vol_change_24h < -30:
        regime = "極度縮量"
    
    print(f"🌐 Current Regime: {regime}")
    
    # 3. Scan Symbols
    symbols = ['SOL/USDT', 'ETH/USDT', 'AVAX/USDT', 'FET/USDT', 'NEAR/USDT']
    model = CryptoMLModel()
    
    print("\n--- AI Confidence Scan (Ignoring Volume Filter) ---")
    for s in symbols:
        try:
            df = fetch_15m_data(s)
            if df.empty: continue
            
            features = extract_features(df, btc_df=df_48h)
            if features.empty: continue
            
            # Drop new features for prediction as model was trained on old feature set
            X = features.iloc[-1:].drop(columns=['btc_volatility_24h', 'dist_ema20'], errors='ignore')
            ml_score = model.predict_proba(X)[0]
            
            # Check RSI and MACD for Aggressive Mode
            rsi = features.iloc[-1]['rsi']
            macd_line, macd_signal, _ = calculate_macd(df)
            last_macd = macd_line.iloc[-1]
            last_sig = macd_signal.iloc[-1]
            
            print(f"🪙 {s} | AI Score: {ml_score:.4f} | RSI: {rsi:.1f} | MACD: {last_macd:.6f}/{last_sig:.6f}")
            
        except Exception as e:
            print(f"Error scanning {s}: {e}")

if __name__ == "__main__":
    diagnostic()

