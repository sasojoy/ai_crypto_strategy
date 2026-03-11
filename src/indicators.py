import pandas as pd
import numpy as np

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def calculate_macd(df, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_adx(df, period=14):
    df = df.copy()
    df['up_move'] = df['high'].diff()
    df['down_move'] = df['low'].diff().abs()

    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)

    atr = calculate_atr(df, period)
    df['plus_di'] = 100 * (df['plus_dm'].rolling(period).mean() / atr)
    df['minus_di'] = 100 * (df['minus_dm'].rolling(period).mean() / atr)

    df['dx'] = 100 * (df['plus_di'] - df['minus_di']).abs() / (df['plus_di'] + df['minus_di'])
    adx = df['dx'].rolling(period).mean()
    return adx

def calculate_bollinger_bands(df, period=20, std_dev=2):
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    bandwidth = (upper_band - lower_band) / sma
    percent_b = (df['close'] - lower_band) / (upper_band - lower_band)
    return upper_band, lower_band, bandwidth, percent_b


def calculate_heikin_ashi(df):
    ha_df = df.copy()
    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_df['ha_close'].iloc[i-1]) / 2
    ha_df['ha_open'] = ha_open
    
    ha_df['ha_high'] = ha_df[['ha_open', 'ha_close', 'high']].max(axis=1)
    ha_df['ha_low'] = ha_df[['ha_open', 'ha_close', 'low']].min(axis=1)
    return ha_df[['ha_open', 'ha_high', 'ha_low', 'ha_close']]

def calculate_sr_levels(df, window=12): # Iteration 24: Use last 12 candles for more reactive S/R
    support = df['low'].rolling(window=window).min()
    resistance = df['high'].rolling(window=window).max()
    return support, resistance

def calculate_rsi_slope(df, window=3):
    rsi = calculate_rsi(df)
    return rsi.diff(window)


def calculate_stoch_rsi(df, period=14, smooth_k=3, smooth_d=3):
    rsi = calculate_rsi(df, period)
    rsi_min = rsi.rolling(window=period).min()
    rsi_max = rsi.rolling(window=period).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min)
    k = stoch_rsi.rolling(window=smooth_k).mean() * 100
    d = k.rolling(window=smooth_d).mean() * 100
    return k, d


def calculate_squeeze_index(df, period=20):
    """
    Iteration 52: Squeeze Index
    Measures the ratio between Keltner Channel and Bollinger Bands.
    Squeeze Index < 0.3 indicates extreme compression.
    """
    # Bollinger Bands
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    bb_upper = sma + (std * 2)
    bb_lower = sma - (std * 2)
    
    # Keltner Channel (using ATR)
    atr = calculate_atr(df, period)
    kc_upper = sma + (atr * 1.5)
    kc_lower = sma - (atr * 1.5)
    
    # Squeeze Index: Ratio of BB width to KC width
    bb_width = bb_upper - bb_lower
    kc_width = kc_upper - kc_lower
    squeeze_index = bb_width / kc_width
    return squeeze_index

def calculate_macd_divergence(df, window=20):
    """
    Iteration 52: MACD Bullish Divergence
    Price makes lower low, but MACD makes higher low.
    """
    macd_line, _, _ = calculate_macd(df)
    
    # Find local minima in price and MACD
    price_lows = df['low'].rolling(window=window).min()
    macd_lows = macd_line.rolling(window=window).min()
    
    # Check for divergence: 
    # Current price low is lower than previous window's low, 
    # but current MACD low is higher than previous window's low.
    # This is a simplified version for real-time calculation.
    price_lower_low = df['low'] < df['low'].shift(window)
    macd_higher_low = macd_line > macd_line.shift(window)
    
    return price_lower_low & macd_higher_low

