import pandas as pd
import numpy as np
from src.indicators import calculate_rsi, calculate_macd, calculate_adx, calculate_atr, calculate_ema

def extract_features(df, btc_df=None):
    """
    Iteration 89.0: Rigid Data Alignment
    """
    expected_features = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
        'dist_ema200', 'dist_ema20'
    ]

    # 0. Guardrail: Handle None or Empty DataFrame
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        print("⚠️ Warning: extract_features received None or empty DataFrame! Returning neutral 0.5 features.")
        neutral_features = pd.DataFrame([[0.5] * len(expected_features)], columns=expected_features)
        return neutral_features

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
    # Iteration 89.0: Rigid Data Alignment
    features['rsi'] = calculate_rsi(df)
    _, _, macd_hist = calculate_macd(df)
    features['macd_hist'] = macd_hist
    features['adx'] = calculate_adx(df)
    features['atr_pct'] = calculate_atr(df) / df['close']
    features['vol_change_24h'] = df['volume'].pct_change(24)
    features['volatility_24h'] = df['close'].pct_change().rolling(window=24).std()

    print(f"🔍 [Iteration 89.0 | Rigid Data] Input indicators keys: {features.columns.tolist()}")

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

    # 4. Robust NaN Handling (Iteration 89.0: Rigid Data Alignment)
    # Use bfill first to propagate future values back to early NaN rows (warmup period)
    # Then ffill for any remaining gaps.
    features = features.bfill().ffill()
    
    # Iteration 89.0: Print final features before returning
    print(f"🔍 [Iteration 89.0 | Rigid Data] Final features to model (Tail 1):\n{features.tail(1)}")

    # Debugging (Iteration 89.0: Rigid Data Alignment)
    if not features.empty:
        last_row = features.iloc[-1:] # Use iloc[-1:] to keep it as a DataFrame/Series
        print(f"🔍 [Iteration 89.0 | Rigid Data] Feature Debug - RSI: {last_row['rsi'].values[0]:.2f}, DistEMA200: {last_row['dist_ema200'].values[0]:.4f}")
        
        # Check for NaN in the last row which causes 50% lock if filled with 0.5
        if last_row.isnull().any().any():
            print(f"⚠️ [Iteration 89.0 | Rigid Data] CRITICAL: NaN detected in final features for {df.index[-1] if hasattr(df, 'index') else 'unknown'}")
            print(f"{last_row[last_row.isnull()]}")
    else:
        print("⚠️ Warning: Features DataFrame is empty!")

    return features

def prepare_labels(df, horizon=4):
    future_close = df['close'].shift(-horizon)
    pnl = (future_close - df['close']) / df['close']
    return (pnl > 0).astype(int)
