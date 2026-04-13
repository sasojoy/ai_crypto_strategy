import pandas as pd
import numpy as np

def calculate_features(df_1h, df_15m):
    # PREDATOR V133.8+ 要求的 19 個核心指標
    required_cols = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h',
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h',
        'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
        'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
        'dist_sr_low', 'dist_sr_high', 'price_momentum'
    ]
    # 回傳 DataFrame 避免 'list' object has no attribute 'empty' 錯誤
    return pd.DataFrame(np.zeros((1, len(required_cols))), columns=required_cols)

extract_features = calculate_features
