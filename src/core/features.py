



import pandas as pd
import pandas_ta as ta
import numpy as np

class Registry_Lock:
    MASTER_FEATURES = [
        'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h',
        'volatility_24h', 'dist_ema200', 'dist_ema20', 'bb_width', 
        'bb_percent_b', 'price_momentum', 'bb_width_roc', 'rsi_long', 
        'macd_slope', 'vol_buy_ratio', 'ema_trend_1h', 'ema_trend_4h',
        # --- 汰弱留強：引入新特徵 ---
        'volume_delta', 'atr_expansion'
    ]

    @classmethod
    def verify(cls, df):
        # --- 物理常數第一條：特徵數量必須精準為 19 ---
        expected_count = 19
        assert len(cls.MASTER_FEATURES) == expected_count, f"Registry_Lock Error: Expected {expected_count} features, got {len(cls.MASTER_FEATURES)}"
        
        # Ensure all master features are present in the dataframe
        for feat in cls.MASTER_FEATURES:
            assert feat in df.columns, f"Registry_Lock Error: Missing feature {feat}"
        
        # Ensure no NaN values
        assert not df[cls.MASTER_FEATURES].isnull().values.any(), "Registry_Lock Error: NaN values detected in features"
        
        # Ensure no extra features in the output
        # We only check the columns that are supposed to be features
        feature_df = df[cls.MASTER_FEATURES]
        assert feature_df.shape[1] == expected_count, f"Registry_Lock Error: Feature count mismatch. Expected {expected_count}, got {feature_df.shape[1]}"
        
        return True

def calculate_features(df_input, df_btc_input):
    if df_input.empty or df_btc_input.empty:
        return pd.DataFrame()

    df = df_input.copy()
    df_btc = df_btc_input.copy()

    # Ensure timestamp is index for joining
    if 'timestamp' in df.columns:
        df.set_index('timestamp', inplace=True)
    if 'timestamp' in df_btc.columns:
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
        combined['macd_div'] = combined['macd_hist'].diff()

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

    # 7. 擠壓指標 (Squeeze Index)
    combined['squeeze_index'] = combined['bb_width'] / combined['volatility_24h'].rolling(100).mean()

    # 8. 支撐壓力距離 (SR Distance)
    combined['dist_sr_high'] = (combined['high'].rolling(50).max() - combined['close']) / combined['close']
    combined['dist_sr_low'] = (combined['close'] - combined['low'].rolling(50).min()) / combined['close']

    # 9. 交易量變動
    combined['vol_change_24h'] = combined['volume'].pct_change(24)

    # --- NEW FEATURES (Priority 1) ---
    # 10. 波動率變化率
    combined['bb_width_roc'] = combined['bb_width'].pct_change(5)
    
    # 11. 多時間週期 RSI
    combined['rsi_long'] = ta.rsi(combined['close'], length=28)
    
    # 12. MACD 柱狀圖斜率
    combined['macd_slope'] = combined['macd_hist'].diff(3)
    
    # 13. 成交量分佈特徵 (簡化版：買盤比率)
    # 假設收盤價高於開盤價為買盤主導
    combined['vol_buy_ratio'] = np.where(combined['close'] > combined['open'], combined['volume'], 0)
    combined['vol_buy_ratio'] = combined['vol_buy_ratio'].rolling(20).sum() / combined['volume'].rolling(20).sum()

    # 14. Volume Delta (成交量變化量)
    combined['volume_delta'] = combined['volume'].diff()

    # 15. ATR 擴張率 (ATR Expansion Rate)
    combined['atr_expansion'] = atr_df.pct_change(5) if atr_df is not None else 0

    # 16. 跨時間框架共振 (1h, 4h) - 修正時空洩漏 (Time Machine Leak)
    # 必須先在該級別完成 .shift(1)，才能填充回 15m 級別
    
    # 1h 級別
    df_1h = combined['close'].resample('h').last()
    ema20_1h = ta.ema(df_1h, length=20).shift(1)
    ema50_1h = ta.ema(df_1h, length=50).shift(1)
    ema_trend_1h_series = (ema20_1h - ema50_1h) / ema50_1h
    combined['ema_trend_1h'] = pd.Series(combined.index.map(ema_trend_1h_series), index=combined.index).ffill()
    
    # 4h 級別
    df_4h = combined['close'].resample('4h').last()
    ema20_4h = ta.ema(df_4h, length=20).shift(1)
    ema50_4h = ta.ema(df_4h, length=50).shift(1)
    ema_trend_4h_series = (ema20_4h - ema50_4h) / ema50_4h
    combined['ema_trend_4h'] = pd.Series(combined.index.map(ema_trend_4h_series), index=combined.index).ffill()

    # Apply Registry_Lock MASTER_FEATURES
    for col in Registry_Lock.MASTER_FEATURES:
        if col not in combined.columns: combined[col] = 0.0

    combined = combined.ffill().fillna(0)
    final_df = combined[Registry_Lock.MASTER_FEATURES]
    
    # --- KILL LOOK-AHEAD BIAS ---
    # Ensure current decision (t) only uses closed data (t-1)
    # 這裡的 shift(1) 確保了所有特徵（包括跨時間框架特徵）都只使用已收盤的數據
    final_df = final_df.shift(1).dropna()
    
    # Lock verification
    Registry_Lock.verify(final_df)
    
    return final_df



