import pandas as pd
import numpy as np
import joblib
import os
from src.core.features import Registry_Lock

class H16Strategy:
    def __init__(self, model_path='/workspace/ai_crypto_strategy/models/h16_v2_wf.joblib'):
        self.model_path = model_path
        self.model = self._load_model()
        # 方案一：滾動分位數動態閾值 (Rolling Quantile)
        self.window = 2000
        self.quantile_val = 0.95

    def _load_model(self):
        if os.path.exists(self.model_path):
            return joblib.load(self.model_path)
        else:
            # Fallback or warning if model not found
            print(f"Warning: Model not found at {self.model_path}")
            return None

    def predict_signal(self, final_df, current_price, atr=None):
        """
        接收 final_df，全面改用滾動分位數動態閾值。
        """
        if self.model is None or final_df.empty:
            return {"signal_type": "Neutral", "confidence_score": 0.0, "limit_price": 0.0, "stop_loss": 0.0}

        # 為了計算滾動分位數，我們需要最近 window 期的預測值
        lookback_df = final_df.tail(self.window + 1)
        all_preds = self.model.predict(lookback_df[Registry_Lock.MASTER_FEATURES])
        
        current_pred = float(all_preds[-1])
        past_preds = all_preds[:-1] if len(all_preds) > 1 else all_preds

        # 計算動態閾值
        if len(past_preds) >= 100: # 至少要有一定數據才計算分位數
            upper_threshold = np.quantile(past_preds, self.quantile_val)
            lower_threshold = np.quantile(past_preds, 1 - self.quantile_val)
        else:
            # 數據不足時回退到極其保守的靜態門檻
            upper_threshold = 0.005
            lower_threshold = -0.005

        # 獲取 4h EMA 趨勢濾網
        ema_trend_4h = float(lookback_df['ema_trend_4h'].iloc[-1])

        # 決策邏輯：預測值必須擊穿 95% 分位數且趨勢共振
        if current_pred > upper_threshold and ema_trend_4h > 0:
            signal_type = "Long"
        elif current_pred < lower_threshold and ema_trend_4h < 0:
            signal_type = "Short"
        else:
            signal_type = "Neutral"

        # 動態停損
        stop_loss = 0.0
        if atr is not None:
            if signal_type == "Long":
                stop_loss = current_price - 2 * atr
            elif signal_type == "Short":
                stop_loss = current_price + 2 * atr

        return {
            "signal_type": signal_type,
            "confidence_score": current_pred,
            "limit_price": current_price,
            "stop_loss": stop_loss,
            "timestamp": lookback_df.index[-1]
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
