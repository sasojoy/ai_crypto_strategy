
import pandas as pd
import numpy as np
from src.indicators import calculate_rsi, calculate_macd, calculate_adx, calculate_atr, calculate_ema

def extract_features(df, btc_df=None):
    """
    Iteration 55: Feature Extractor for ML Model
    Converts OHLCV data into a feature set.
    """
    features = pd.DataFrame(index=df.index)
    
    # 1. Standard Indicators
    features['rsi'] = calculate_rsi(df)
    macd_line, signal_line, macd_hist = calculate_macd(df)
    features['macd_hist'] = macd_hist
    features['adx'] = calculate_adx(df)
    features['atr_pct'] = calculate_atr(df) / df['close']
    
    # 2. 24H Volume Change Rate (assuming 1H data, 24 periods)
    features['vol_change_24h'] = df['volume'].pct_change(24)
    
    # 3. Price Volatility (Standard Deviation of returns)
    features['volatility_24h'] = df['close'].pct_change().rolling(window=24).std()
    
    # 4. Relative Strength vs BTC & BTC Volatility
    if btc_df is not None:
        # Align BTC data with current df
        btc_close = btc_df['close'].reindex(df.index, method='ffill')
        coin_returns = df['close'].pct_change(24)
        btc_returns = btc_close.pct_change(24)
        features['relative_strength_btc'] = coin_returns - btc_returns
        # Iteration 59: [Feature Injection] BTC Standard Deviation (24H)
        features['btc_volatility_24h'] = btc_close.pct_change().rolling(window=24).std()
    else:
        features['relative_strength_btc'] = 0
        features['btc_volatility_24h'] = 0
        
    # 5. Price distance from EMA 200
    ema200 = calculate_ema(df, 200)
    features['dist_ema200'] = (df['close'] - ema200) / ema200
    
    # Iteration 60: [Feature Injection] Price distance from EMA 20
    ema20 = calculate_ema(df, 20)
    features['dist_ema20'] = (df['close'] - ema20) / ema20
    
    # Iteration 71.3: Fix AI feature alignment and NaN handling
    expected_features = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
        'dist_ema200', 'dist_ema20'
    ]
    
    # Ensure all expected features exist
    for feat in expected_features:
        if feat not in features.columns:
            features[feat] = 0.5
            
    # Reorder columns to match model training
    features = features[expected_features]
    
    # Handle NaNs: backfill then fill remaining with neutral 0.5
    features = features.bfill().fillna(0.5)
    
    return features

def prepare_labels(df, horizon=4):
    """
    Label: Is PnL positive after 'horizon' periods?
    """
    future_close = df['close'].shift(-horizon)
    pnl = (future_close - df['close']) / df['close']
    return (pnl > 0).astype(int)
