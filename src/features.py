import pandas as pd
import numpy as np

def calculate_features(df, btc_df):
    df = df.copy()
    # Basic Indicators
    df['rsi'] = (df['close'].diff().where(df['close'].diff() > 0, 0).rolling(14).mean() / 
                 df['close'].diff().abs().rolling(14).mean()) * 100
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    # Iteration 121.0: Scale MACD by price for global model consistency
    df['macd_hist'] = ((ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()) / df['close']
    
    # Volatility & ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_pct'] = tr.rolling(14).mean() / df['close']
    
    # Volume & Volatility (Corrected for 1H: 24 periods = 24h)
    df['vol_change_24h'] = df['volume'].pct_change(24)
    df['volatility_24h'] = df['close'].pct_change().rolling(24).std()
    
    # BTC Relative Strength (Corrected for 1H: 24 periods = 24h ratio)
    btc_pct_24h = btc_df['close'].pct_change(24).reindex(df.index).ffill()
    df['relative_strength_btc'] = (df['close'].pct_change(24) + 1) / (btc_pct_24h + 1)
    df['btc_volatility_24h'] = btc_df['close'].pct_change().rolling(24).std().reindex(df.index).ffill()
    
    # Distance to EMAs
    df['dist_ema200'] = (df['close'] - df['close'].ewm(span=200, adjust=False).mean()) / df['close'].ewm(span=200, adjust=False).mean()
    df['dist_ema20'] = (df['close'] - df['close'].ewm(span=20, adjust=False).mean()) / df['close'].ewm(span=20, adjust=False).mean()
    
    # Bollinger Bands
    std20 = df['close'].rolling(20).std()
    ma20 = df['close'].rolling(20).mean()
    df['bb_width'] = (4 * std20) / ma20
    df['bb_percent_b'] = (df['close'] - (ma20 - 2 * std20)) / (4 * std20)
    
    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = (df['close'] - low14) / (high14 - low14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    
    # Squeeze & Momentum
    df['squeeze_index'] = df['bb_width'] / df['atr_pct']
    df['macd_div'] = df['macd_hist'].diff()
    df['price_momentum'] = df['close'].pct_change(24) # Aligned to 24h
    
    # Support/Resistance (Simplified)
    df['dist_sr_low'] = (df['close'] - df['low'].rolling(100).min()) / df['close']
    df['dist_sr_high'] = (df['high'].rolling(100).max() - df['close']) / df['close']
    
    # ADX (Standard via pandas_ta)
    import pandas_ta as ta
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx_df is not None:
        df['adx'] = adx_df['ADX_14']
    else:
        df['adx'] = 0
    
    # Iteration 120.0: Lag Audit - Shift all features by 1 to use ONLY closed bars
    feature_cols = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 'volatility_24h',
        'relative_strength_btc', 'btc_volatility_24h', 'dist_ema200', 'dist_ema20',
        'bb_width', 'bb_percent_b', 'stoch_k', 'stoch_d', 'squeeze_index',
        'macd_div', 'dist_sr_low', 'dist_sr_high', 'price_momentum'
    ]
    df[feature_cols] = df[feature_cols].shift(1)
    
    return df.dropna()
