import pandas as pd
import numpy as np

def calculate_features(df, btc_df):
    df = df.copy()
    # Basic Indicators
    df['rsi'] = (df['close'].diff().where(df['close'].diff() > 0, 0).rolling(14).mean() / 
                 df['close'].diff().abs().rolling(14).mean()) * 100
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_hist'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()
    
    # Volatility & ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_pct'] = tr.rolling(14).mean() / df['close']
    
    # Volume & Volatility
    df['vol_change_24h'] = df['volume'].pct_change(96)
    df['volatility_24h'] = df['close'].pct_change().rolling(96).std()
    
    # BTC Relative Strength
    df['relative_strength_btc'] = df['close'].pct_change() - btc_df['close'].pct_change().reindex(df.index).ffill()
    df['btc_volatility_24h'] = btc_df['close'].pct_change().rolling(96).std().reindex(df.index).ffill()
    
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
    df['price_momentum'] = df['close'].pct_change(10)
    
    # Support/Resistance (Simplified)
    df['dist_sr_low'] = (df['close'] - df['low'].rolling(100).min()) / df['close']
    df['dist_sr_high'] = (df['high'].rolling(100).max() - df['close']) / df['close']
    
    # ADX (Simplified)
    df['adx'] = df['atr_pct'].rolling(14).mean() * 100 # Proxy
    
    return df.dropna()
