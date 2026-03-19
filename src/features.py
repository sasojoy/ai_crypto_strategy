import pandas as pd
import numpy as np
from src.indicators import calculate_rsi, calculate_macd, calculate_adx, calculate_atr, calculate_ema

def extract_features(df, btc_df=None):
    """
    Iteration 71.10: Native Logic Overwrite
    """
    # 1. Force chronological order (Native Sort)
    if 'timestamp' in df.columns:
        df = df.sort_values('timestamp', ascending=True)
    df = df.sort_index(ascending=True)
    
    if btc_df is not None:
        if 'timestamp' in btc_df.columns:
            btc_df = btc_df.sort_values('timestamp', ascending=True)
        btc_df = btc_df.sort_index(ascending=True)

    features = pd.DataFrame(index=df.index)

    # 2. Calculate Indicators
    features['rsi'] = calculate_rsi(df)
    _, _, macd_hist = calculate_macd(df)
    features['macd_hist'] = macd_hist
    features['adx'] = calculate_adx(df)
    features['atr_pct'] = calculate_atr(df) / df['close']
    features['vol_change_24h'] = df['volume'].pct_change(24)
    features['volatility_24h'] = df['close'].pct_change().rolling(window=24).std()

    if btc_df is not None:
        btc_close = btc_df['close'].reindex(df.index, method='ffill')
        coin_returns = df['close'].pct_change(24)
        btc_returns = btc_close.pct_change(24)
        features['relative_strength_btc'] = coin_returns - btc_returns
        features['btc_volatility_24h'] = btc_close.pct_change().rolling(window=24).std()
    else:
        features['relative_strength_btc'] = 0
        features['btc_volatility_24h'] = 0

    ema200 = calculate_ema(df, 200)
    features['dist_ema200'] = (df['close'] - ema200) / ema200
    ema20 = calculate_ema(df, 20)
    features['dist_ema20'] = (df['close'] - ema20) / ema20

    # 3. Feature Alignment (Iteration 71.10: Strict Reindex)
    expected_features = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
        'dist_ema200', 'dist_ema20'
    ]
    
    features = features.reindex(columns=expected_features)

    # 4. Robust NaN Handling
    features = features.bfill().ffill().fillna(0.5)

    # Debugging (Iteration 71.14: NoneType Protection)
    if not features.empty:
        last_row = features.iloc[-1]
        print(f"🔍 [Feature Debug] RSI: {last_row['rsi']:.2f}, DistEMA200: {last_row['dist_ema200']:.4f}")
    else:
        print("⚠️ Warning: Features DataFrame is empty! Returning default 0.5 values.")
        # Create a single-row DataFrame with default 0.5 values
        features = pd.DataFrame([0.5] * len(expected_features), index=expected_features).T
        features.columns = expected_features

    return features

def prepare_labels(df, horizon=4):
    future_close = df['close'].shift(-horizon)
    pnl = (future_close - df['close']) / df['close']
    return (pnl > 0).astype(int)
