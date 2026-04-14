import pandas as pd
import pandas_ta as ta
import numpy as np


def calculate_features(df_input, df_btc_input):
    if df_input.empty or df_btc_input.empty:
        return pd.DataFrame()


    df = df_input.copy()
    df_btc = df_btc_input.copy()


    # 對齊時間戳
    df.set_index('timestamp', inplace=True)
    df_btc.set_index('timestamp', inplace=True)
    df_btc = df_btc[['close']].rename(columns={'close': 'btc_close'})


    combined = df.join(df_btc, how='inner')
    if combined.empty:
        return pd.DataFrame()


    # --- 核心指標計算 ---
    combined['rsi'] = ta.rsi(combined['close'], length=14)
    
    macd = ta.macd(combined['close'])
    if macd is not None:
        hist_cols = [c for c in macd.columns if 'MACDh' in c or 'MACDH' in c]
        combined['macd_hist'] = macd[hist_cols[0]] if hist_cols else 0.0
    
    adx = ta.adx(combined['high'], combined['low'], combined['close'], length=14)
    if adx is not None:
        adx_cols = [c for c in adx.columns if 'ADX' in c]
        combined['adx'] = adx[adx_cols[0]] if adx_cols else 0.0
    
    combined['volatility_24h'] = combined['close'].pct_change().rolling(24).std()
    combined['relative_strength_btc'] = combined['close'] / combined['btc_close']


    # --- 19 項標準協議特徵清單 (必須與 market.py 嚴格一致) ---
    MASTER_FEATURES = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
        'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
        'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
        'dist_sr_low', 'dist_sr_high', 'price_momentum'
    ]


    # 強制補齊所有缺失的特徵列
    for col in MASTER_FEATURES:
        if col not in combined.columns:
            combined[col] = 0.0


    # 最終清洗：先向前填充，剩下的補 0
    combined = combined.ffill().fillna(0)
    
    return combined[MASTER_FEATURES] # 只回傳協議內的特徵
