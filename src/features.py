import pandas as pd
import numpy as np

def calculate_features(df_1h, df_15m):
    cols = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h',
        'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h',
        'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
        'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
        'dist_sr_low', 'dist_sr_high', 'price_momentum'
    ]
    return pd.DataFrame(np.zeros((1, 19)), columns=cols)

extract_features = calculate_features
