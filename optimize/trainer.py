


import pandas as pd
import numpy as np
import joblib
import json
import os
from xgboost import XGBClassifier
from src.core.features import calculate_features, Registry_Lock

class H16Trainer:
    def __init__(self, train_window_days=30, test_window_days=7, friction=0.0018, n_forward=12):
        self.train_window_days = train_window_days
        self.test_window_days = test_window_days
        self.friction = friction
        self.n_forward = n_forward
        self.manifest = []

        if train_window_days < 14:
            print("⚠️ WARNING: Training window is too short (< 14 days). This will likely lead to OVERFITTING.")

    def prepare_data(self, df, df_btc):
        """
        對齊邏輯：
        X_t: 來自 t-1 的特徵 (已在 calculate_features 中 shift(1))
        y_t: t 之後的報酬 (t 到 t+n)
        """
        # 1. 計算特徵 (已包含 shift(1))
        X = calculate_features(df, df_btc)
        
        # 2. 計算目標變數 y (未來 n 根 K 線的報酬)
        # y_t = (Price_{t+n} - Price_t) / Price_t
        returns = df.set_index('timestamp')['close'].shift(-self.n_forward) / df.set_index('timestamp')['close'] - 1
        
        # 3. 考慮摩擦成本的標籤化
        y = pd.Series(0, index=returns.index)
        y[returns > self.friction] = 1
        y[returns < -self.friction] = 2
        
        # 4. 精準對齊
        data = pd.concat([X, y.rename('target'), returns.rename('raw_return')], axis=1).dropna()
        return data

    def walk_forward_train(self, data):
        """
        走動式驗證 (Walk-forward Validation) 核心邏輯
        實作 Embargo 機制，杜絕時間軸洩漏。
        """
        timestamps = data.index.unique().sort_values()
        start_time = timestamps[0]
        end_time = timestamps[-1]
        
        current_train_start = start_time
        best_model = None
        
        while True:
            current_train_end = current_train_start + pd.Timedelta(days=self.train_window_days)
            
            # --- IMPLEMENT THE PURGE ZONE (EMBARGO) ---
            # 物理隔離：test_start 必須跳過 n_forward 根 K 線，防止 train_set 標籤偷看 test_set 價格
            # 假設數據是 1h 間隔，跳過 n_forward 小時
            embargo_period = pd.Timedelta(hours=self.n_forward)
            current_test_start = current_train_end + embargo_period
            current_test_end = current_test_start + pd.Timedelta(days=self.test_window_days)
            
            if current_test_end > end_time:
                break
            
            # --- TIME SLICING WITH EMBARGO ---
            train_set = data[(data.index >= current_train_start) & (data.index < current_train_end)]
            test_set = data[(data.index >= current_test_start) & (data.index < current_test_end)]
            
            if len(train_set) < 100 or len(test_set) < 20:
                current_train_start += pd.Timedelta(days=self.test_window_days)
                continue

            # --- ARCHITECTURE CORRECTION: XGBOOST ---
            # 使用梯度提升模型 (XGBoost) 處理高雜訊金融數據
            model = XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.05,
                objective='multi:softprob',
                num_class=3,
                random_state=42,
                tree_method='hist' # 提高訓練效率
            )
            
            model.fit(
                train_set[Registry_Lock.MASTER_FEATURES], 
                train_set['target']
            )
            
            # 樣本外預測
            preds = model.predict(test_set[Registry_Lock.MASTER_FEATURES])
            test_set = test_set.copy()
            test_set['pred'] = preds
            
            # 效能評估：摩擦後期望值
            long_signals = test_set[test_set['pred'] == 1]
            short_signals = test_set[test_set['pred'] == 2]
            
            long_expectancy = (long_signals['raw_return'] - self.friction).mean() if not long_signals.empty else 0
            short_expectancy = (-short_signals['raw_return'] - self.friction).mean() if not short_signals.empty else 0
            
            win_rate = (preds == test_set['target']).mean()
            
            window_info = {
                "train_start": str(current_train_start),
                "train_end": str(current_train_end),
                "embargo_gap": str(embargo_period),
                "test_start": str(current_test_start),
                "win_rate": float(win_rate),
                "expectancy": float(long_expectancy + short_expectancy)
            }
            self.manifest.append(window_info)
            
            best_model = model
            current_train_start += pd.Timedelta(days=self.test_window_days)

        if best_model:
            os.makedirs('models', exist_ok=True)
            joblib.dump(best_model, 'models/h16_v2_wf.joblib')
            with open('models/training_manifest.json', 'w') as f:
                json.dump(self.manifest, f, indent=4)
            print("✅ Walk-forward training with Embargo and XGBoost complete.")
        else:
            print("❌ Training failed: Not enough data.")

if __name__ == "__main__":
    # 測試對齊與隔離邏輯
    trainer = H16Trainer(train_window_days=30, test_window_days=7, n_forward=12)
    print("H16Trainer initialized with Embargo Mechanism.")


