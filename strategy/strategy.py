

import pandas as pd
import numpy as np
import joblib
import os

class H16Strategy:
    def __init__(self, model_path='/workspace/ai_crypto_strategy/models/lgbm_model.joblib'):
        self.model_path = model_path
        self.model = self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            return joblib.load(self.model_path)
        else:
            # Fallback or warning if model not found
            print(f"Warning: Model not found at {self.model_path}")
            return None

    def predict_signal(self, final_df):
        """
        接收 final_df（已平移特徵，即 t 時刻看到的數據是 t-1 的收盤結果）。
        輸出信號包含：signal_type, confidence_score, limit_price。
        """
        if self.model is None or final_df.empty:
            return {"signal_type": "Neutral", "confidence_score": 0.0, "limit_price": 0.0}

        # 獲取最新的一行特徵 (t 時刻看到的 t-1 數據)
        latest_features = final_df.iloc[-1:]
        
        # 模型預測
        # 假設模型輸出機率
        probs = self.model.predict_proba(latest_features)[0]
        confidence_score = float(np.max(probs))
        prediction = int(np.argmax(probs))

        # 假設 1 為 Long, 0 為 Neutral/Short (根據具體模型訓練定義)
        # 這裡為了演示，假設模型預測的是 1: Long, 2: Short, 0: Neutral
        signal_map = {0: "Neutral", 1: "Long", 2: "Short"}
        signal_type = signal_map.get(prediction, "Neutral")

        # 獲取當前價格 (t 時刻的價格，用於建議 limit_price)
        # 注意：final_df 不包含原始價格，通常需要從原始數據獲取
        # 這裡假設我們能獲取到最新的收盤價作為參考
        # 由於 final_df 是 shift(1) 過的，我們需要原始數據的最新價格
        
        # 建議 limit_price：這裡簡單使用 t-1 的收盤價（即 latest_features 之前的原始數據）
        # 在實際系統中，這會從實時行情獲取
        limit_price = 0.0 # 佔位符，實際應由外部傳入或從行情獲取

        return {
            "signal_type": signal_type,
            "confidence_score": confidence_score,
            "limit_price": limit_price,
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

