import pandas as pd
import pandas_ta as ta
import numpy as np

def calculate_features(df_input, df_btc_input):
    """
    專業級特徵提取：確保 BTC 與標的幣種時間戳 100% 對齊
    """
    if df_input.empty or df_btc_input.empty:
        return pd.DataFrame()

    # 1. 統一複製數據，避免干擾原始 DataFrame
    df = df_input.copy()
    df_btc = df_btc_input.copy()

    # 2. 強制設定時間戳為索引，確保合併時不會錯位
    df.set_index('timestamp', inplace=True)
    df_btc.set_index('timestamp', inplace=True)
    
    # 只取收盤價進行基準對比
    df_btc = df_btc[['close']].rename(columns={'close': 'btc_close'})

    # 3. 合併數據 (Inner Join)
    combined = df.join(df_btc, how='inner')
    
    if combined.empty:
        print("❌ [Feature Error] Merge result is empty! Check timestamp formats.")
        return pd.DataFrame()

    # 4. 計算指標 (使用 pandas_ta)
    # RSI
    combined['rsi'] = ta.rsi(combined['close'], length=14)
    
    # MACD
    macd = ta.macd(combined['close'])
    if macd is not None:
        combined['macd_hist'] = macd['MACDH_12_26_9']
    
    # ADX
    adx = ta.adx(combined['high'], combined['low'], combined['close'], length=14)
    if adx is not None:
        combined['adx'] = adx['ADX_14']
    
    # 波動率 (Volatility)
    combined['volatility_24h'] = combined['close'].pct_change().rolling(24).std()
    
    # 相對強度 (Relative Strength to BTC)
    combined['relative_strength_btc'] = combined['close'] / combined['btc_close']
    
    # 其他模型需要的佔位特徵 (確保列名對齊 market.py 的 REQUIRED_FEATURES)
    for col in ['atr_pct', 'vol_change_24h', 'btc_volatility_24h', 'dist_ema200', 
                'dist_ema20', 'bb_width', 'bb_percent_b', 'stoch_k', 'stoch_d', 
                'squeeze_index', 'macd_div', 'dist_sr_low', 'dist_sr_high', 'price_momentum']:
        if col not in combined.columns:
            combined[col] = 0.0

    # 5. 移除預熱期的 NaN，並填補剩餘空值
    # 這裡很關鍵：我們不能一開始就 fillna(0)，否則指標算不出來
    combined = combined.fillna(method='ffill').fillna(0)
    
    return combined
