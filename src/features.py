import pandas as pd
import numpy as np
from src.indicators import calculate_rsi, calculate_macd, calculate_adx, calculate_atr, calculate_ema

def extract_features(df, btc_df=None):
    """
    Iteration 94.0: Standardized Feature Extraction (19 Features)
    """
    expected_features = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
        'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b',
        'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div',
        'dist_sr_low', 'dist_sr_high', 'price_momentum'
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
    from src.indicators import (
        calculate_bollinger_bands, calculate_stoch_rsi,
        calculate_squeeze_index, calculate_macd_divergence, calculate_sr_levels
    )
    
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

    # New Features for Iteration 94.0
    _, _, bb_width, bb_percent_b = calculate_bollinger_bands(df)
    features['bb_width'] = bb_width
    features['bb_percent_b'] = bb_percent_b

    stoch_k, stoch_d = calculate_stoch_rsi(df)
    features['stoch_k'] = stoch_k / 100.0
    features['stoch_d'] = stoch_d / 100.0

    features['squeeze_index'] = calculate_squeeze_index(df)
    features['macd_div'] = calculate_macd_divergence(df)

    sr_low, sr_high = calculate_sr_levels(df)
    features['dist_sr_low'] = (df['close'] - sr_low) / df['close']
    features['dist_sr_high'] = (sr_high - df['close']) / df['close']
    features['price_momentum'] = df['close'].pct_change(4)

    # 3. Feature Alignment
    features = features.reindex(columns=expected_features)

    # 4. Robust NaN Handling (Iteration 71.3: AI Feature Alignment)
    # Use bfill first to propagate future values back to early NaN rows (warmup period)
    # Then ffill for any remaining gaps.
    # Iteration 116.0 Soul: Use modern bfill/ffill methods
    features = features.bfill().ffill()
    
    # If still NaN (e.g. all values are NaN), fill with reasonable defaults
    if features.isnull().any().any():
        features = features.fillna(0.5) # Neutral fallback for indicators
    
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
