

import pandas as pd
import numpy as np
import joblib
import os
from src.core.features import Registry_Lock

class H16Strategy:
    def __init__(self, model_path='/workspace/ai_crypto_strategy/models/h16_v2_wf.joblib'):
        self.model_path = model_path
        self.model = self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            return joblib.load(self.model_path)
        else:
            # Fallback or warning if model not found
            print(f"Warning: Model not found at {self.model_path}")
            return None

    def predict_signal(self, final_df, current_price, atr=None):
        """
        接收 final_df（已平移特徵，即 t 時刻看到的數據是 t-1 的收盤結果）。
        輸出信號包含：signal_type, confidence_score, limit_price, stop_loss。
        """
        if self.model is None or final_df.empty:
            return {"signal_type": "Neutral", "confidence_score": 0.0, "limit_price": 0.0, "stop_loss": 0.0}

        # 獲取最新的一行特徵 (t 時刻看到的 t-1 數據)
        latest_features = final_df.iloc[-1:]
        
        # 模型預測 (XGBRegressor)
        pred_return = float(self.model.predict(latest_features)[0])
        
        # --- REGIME FILTER (Priority 3) ---
        # 獲取 4h EMA 趨勢濾網特徵
        ema_trend_4h = float(latest_features['ema_trend_4h'].iloc[0])

        # 決策邏輯：
        # 當預測未來 12 根 K 線報酬 > 0.05% 且 4h 趨勢向上時，發出做多信號
        # 當預測未來 12 根 K 線報酬 < -0.05% 且 4h 趨勢向下時，發出做空信號
        if pred_return > 0.0005 and ema_trend_4h > 0:
            signal_type = "Long"
        elif pred_return < -0.0005 and ema_trend_4h < 0:
            signal_type = "Short"
        else:
            signal_type = "Neutral"

        # 動態停損：強制掛上 2 倍 ATR 的動態停損邏輯
        stop_loss = 0.0
        if atr is not None:
            if signal_type == "Long":
                stop_loss = current_price - 2 * atr
            elif signal_type == "Short":
                stop_loss = current_price + 2 * atr
        
        

        return {
            "signal_type": signal_type,
            "confidence_score": abs(pred_return),
            "limit_price": current_price,
            "stop_loss": stop_loss,
            "timestamp": latest_features.index[0]
        }

    def get_y_definition(self):
        """
        定義 y 的數學公式：
        y_t = (Price_{t+12} > Price_t * 1.01) -> 1 (Long)
        y_t = (Price_{t+12} < Price_t * 0.99) -> 2 (Short)
        Else -> 0 (Neutral)
        """
        code_snippet = """
        # Target Labeling Logic in trainer.py
        # y_t is the price movement from t to t+12
        df['future_close'] = df['close'].shift(-12)
        df['target'] = 0  # Neutral
        df.loc[df['future_close'] > df['close'] * 1.01, 'target'] = 1  # Long
        df.loc[df['future_close'] < df['close'] * 0.99, 'target'] = 2  # Short
        """
        return code_snippet

    def get_alignment_logic(self):
        """
        展示對齊邏輯 (Alignment Logic)：
        確保 X_t (基於 t-1) 預測的是 y_t (t 之後的變動)。
        """
        alignment_code = """
        # X_t: Features at time t (already shifted by 1 in features.py)
        # y_t: Target at time t (predicting t+12)
        
        # In training:
        X = calculate_features(df) # This returns shifted features
        y = calculate_target(df)   # This calculates target for each t
        
        # Merge on index (timestamp)
        train_df = pd.concat([X, y], axis=1).dropna()
        
        # Result:
        # At index '2026-04-15 10:00:00':
        # X contains data from '... 09:00:00' (t-1)
        # y contains label for '... 10:00:00' -> '... 22:00:00' (t -> t+12)
        """
        return alignment_code

