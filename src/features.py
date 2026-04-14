import pandas as pd
import pandas_ta as ta
import numpy as np

def calculate_features(df_input, df_btc_input):
    if df_input.empty or df_btc_input.empty:
        return pd.DataFrame()

    df = df_input.copy()
    df_btc = df_btc_input.copy()

    df.set_index('timestamp', inplace=True)
    df_btc.set_index('timestamp', inplace=True)
    df_btc_close = df_btc[['close']].rename(columns={'close': 'btc_close'})

    combined = df.join(df_btc_close, how='inner')
    if combined.empty: return pd.DataFrame()

    # 1. 基礎指標
    combined['rsi'] = ta.rsi(combined['close'], length=14)
    macd = ta.macd(combined['close'])
    if macd is not None:
        h_col = [c for c in macd.columns if 'MACDh' in c or 'MACDH' in c]
        combined['macd_hist'] = macd[h_col[0]] if h_col else 0
        combined['macd_div'] = combined['macd_hist'].diff() # MACD 柱狀圖斜率
    
    adx_df = ta.adx(combined['high'], combined['low'], combined['close'], length=14)
    if adx_df is not None:
        combined['adx'] = adx_df[[c for c in adx_df.columns if 'ADX' in c][0]]

    # 2. 波動與通道 (Bollinger Bands)
    bbands = ta.bbands(combined['close'], length=20, std=2)
    if bbands is not None:
        combined['bb_width'] = (bbands.iloc[:, 2] - bbands.iloc[:, 0]) / bbands.iloc[:, 1]
        combined['bb_percent_b'] = (combined['close'] - bbands.iloc[:, 0]) / (bbands.iloc[:, 2] - bbands.iloc[:, 0])
    
    # 3. 波動率與 ATR
    atr_df = ta.atr(combined['high'], combined['low'], combined['close'], length=14)
    combined['atr_pct'] = (atr_df / combined['close']) if atr_df is not None else 0
    combined['volatility_24h'] = combined['close'].pct_change().rolling(24).std()
    combined['btc_volatility_24h'] = combined['btc_close'].pct_change().rolling(24).std()

    # 4. 相對強度與動能
    combined['relative_strength_btc'] = combined['close'] / combined['btc_close']
    combined['price_momentum'] = combined['close'].pct_change(10)

    # 5. 移動平均偏離 (Distance from EMA)
    combined['dist_ema20'] = (combined['close'] - ta.ema(combined['close'], length=20)) / ta.ema(combined['close'], length=20)
    combined['dist_ema200'] = (combined['close'] - ta.ema(combined['close'], length=200)) / ta.ema(combined['close'], length=200)

    # 6. 隨機指標 (Stochastic)
    stoch = ta.stoch(combined['high'], combined['low'], combined['close'])
    if stoch is not None:
        combined['stoch_k'] = stoch.iloc[:, 0]
        combined['stoch_d'] = stoch.iloc[:, 1]

    # 7. 擠壓指標 (Squeeze Index - 簡化版)
    combined['squeeze_index'] = combined['bb_width'] / combined['volatility_24h'].rolling(100).mean()

    # 8. 支撐壓力距離 (SR Distance)
    combined['dist_sr_high'] = (combined['high'].rolling(50).max() - combined['close']) / combined['close']
    combined['dist_sr_low'] = (combined['close'] - combined['low'].rolling(50).min()) / combined['close']

    # 9. 交易量變動
    combined['vol_change_24h'] = combined['volume'].pct_change(24)

    # --- 嚴格對齊 19 項協議 ---
    MASTER_FEATURES = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
        'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
        'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
        'dist_sr_low', 'dist_sr_high', 'price_momentum'
    ]
    
    # 補齊缺失並清洗
    for col in MASTER_FEATURES:
        if col not in combined.columns: combined[col] = 0.0
    
    combined = combined.ffill().fillna(0)
    return combined[MASTER_FEATURES]
