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
    df_btc = df_btc[['close']].rename(columns={'close': 'btc_close'})

    combined = df.join(df_btc, how='inner')
    if combined.empty:
        print("❌ [Feature Error] 數據對齊後結果為空，請檢查時間戳格式")
        return pd.DataFrame()

    # --- RSI ---
    combined['rsi'] = ta.rsi(combined['close'], length=14)
    
    # --- MACD (模糊匹配：解決 MACDH 大小寫與後綴問題) ---
    macd = ta.macd(combined['close'])
    if macd is not None:
        hist_cols = [c for c in macd.columns if 'MACDh' in c or 'MACDH' in c]
        if hist_cols:
            combined['macd_hist'] = macd[hist_cols[0]]
        else:
            combined['macd_hist'] = 0.0
    else:
        combined['macd_hist'] = 0.0

    # --- ADX ---
    adx = ta.adx(combined['high'], combined['low'], combined['close'], length=14)
    if adx is not None:
        adx_cols = [c for c in adx.columns if 'ADX' in c]
        if adx_cols:
            combined['adx'] = adx[adx_cols[0]]
        else:
            combined['adx'] = 0.0
    else:
        combined['adx'] = 0.0
    
    # --- 補齊模型必備欄位 (初始化為 0，避免模型崩潰) ---
    REQUIRED = ['atr_pct', 'vol_change_24h', 'btc_volatility_24h', 'dist_ema200', 
                'dist_ema20', 'bb_width', 'bb_percent_b', 'stoch_k', 'stoch_d', 
                'squeeze_index', 'macd_div', 'dist_sr_low', 'dist_sr_high', 'price_momentum']
    for col in REQUIRED:
        if col not in combined.columns:
            combined[col] = 0.0

    # 數據清洗 (先填補，後補零)
    combined = combined.ffill().fillna(0)
    return combined
