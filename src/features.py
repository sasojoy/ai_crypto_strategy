
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
    
    # 4. Relative Strength vs BTC
    if btc_df is not None:
        # Align BTC data with current df
        btc_close = btc_df['close'].reindex(df.index, method='ffill')
        coin_returns = df['close'].pct_change(24)
        btc_returns = btc_close.pct_change(24)
        features['relative_strength_btc'] = coin_returns - btc_returns
    else:
        features['relative_strength_btc'] = 0
        
    # 5. Price distance from EMA 200
    ema200 = calculate_ema(df, 200)
    features['dist_ema200'] = (df['close'] - ema200) / ema200
    
    return features.dropna()

def prepare_labels(df, horizon=4):
    """
    Label: Is PnL positive after 'horizon' periods?
    """
    future_close = df['close'].shift(-horizon)
    pnl = (future_close - df['close']) / df['close']
    return (pnl > 0).astype(int)
