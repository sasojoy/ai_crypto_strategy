
import pandas as pd
import numpy as np
from src.indicators import (
    calculate_rsi, calculate_macd, calculate_adx, calculate_atr, 
    calculate_ema, calculate_bollinger_bands, calculate_stoch_rsi,
    calculate_squeeze_index, calculate_macd_divergence, calculate_sr_levels
)

def extract_features_v111(df, btc_df=None):
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

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return pd.DataFrame([[0.5] * len(expected_features)], columns=expected_features)

    # Force chronological order
    df = df.sort_index(ascending=True)
    if btc_df is not None:
        btc_df = btc_df.sort_index(ascending=True)

    features = pd.DataFrame(index=df.index)

    # 1-7: Core Indicators
    features['rsi'] = calculate_rsi(df)
    _, _, macd_hist = calculate_macd(df)
    features['macd_hist'] = macd_hist
    features['adx'] = calculate_adx(df)
    features['atr_pct'] = calculate_atr(df) / df['close']
    features['vol_change_24h'] = df['volume'].pct_change(24)
    features['volatility_24h'] = df['close'].pct_change().rolling(window=24).std()
    
    # 8-9: BTC Correlation
    if btc_df is not None:
        btc_close = btc_df['close'].reindex(df.index, method='ffill')
        features['relative_strength_btc'] = df['close'].pct_change(24) - btc_close.pct_change(24)
        features['btc_volatility_24h'] = btc_close.pct_change().rolling(window=24).std()
    else:
        features['relative_strength_btc'] = 0
        features['btc_volatility_24h'] = 0

    # 10-11: EMA Distances
    ema200 = calculate_ema(df, 200)
    features['dist_ema200'] = (df['close'] - ema200) / ema200
    ema20 = calculate_ema(df, 20)
    features['dist_ema20'] = (df['close'] - ema20) / ema20

    # 12-13: Bollinger Bands
    _, _, bb_width, bb_percent_b = calculate_bollinger_bands(df)
    features['bb_width'] = bb_width
    features['bb_percent_b'] = bb_percent_b

    # 14-15: Stochastic RSI
    stoch_k, stoch_d = calculate_stoch_rsi(df)
    features['stoch_k'] = stoch_k / 100.0
    features['stoch_d'] = stoch_d / 100.0

    # 16: Squeeze Index
    features['squeeze_index'] = calculate_squeeze_index(df)

    # 17: MACD Divergence
    features['macd_div'] = calculate_macd_divergence(df)

    # 18-19: S/R Levels & Momentum
    sr_low, sr_high = calculate_sr_levels(df)
    features['dist_sr_low'] = (df['close'] - sr_low) / df['close']
    features['dist_sr_high'] = (sr_high - df['close']) / df['close']
    features['price_momentum'] = df['close'].pct_change(4)

    # Final Alignment & NaN Handling
    features = features.reindex(columns=expected_features)
    features = features.fillna(method='bfill').fillna(method='ffill').fillna(0.5)

    return features
