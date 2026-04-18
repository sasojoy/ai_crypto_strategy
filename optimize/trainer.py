


import pandas as pd
import numpy as np
import joblib
import json
import os
from xgboost import XGBRegressor
from src.core.features import calculate_features, Registry_Lock

class H16Trainer:
    def __init__(self, train_window_days=30, test_window_days=7, friction=0.0018, n_forward=12):
        self.train_window_days = train_window_days
        self.test_window_days = test_window_days
        self.friction = friction
        self.n_forward = n_forward
        self.manifest = []

    def prepare_data(self, df, df_btc):
        X = calculate_features(df, df_btc)
        # 預測未來 12 根 K 線的累積報酬率 (Regression)
        returns = df.set_index('timestamp')['close'].shift(-self.n_forward) / df.set_index('timestamp')['close'] - 1
        data = pd.concat([X, returns.rename('target')], axis=1).dropna()
        return data

    def walk_forward_train(self, data):
        """
        走動式驗證 (Walk-forward Validation)
        實施「Embargo」物理隔離，基於整數索引 (iloc) 確保絕對物理順序。
        """
        # --- DRIFT DEFENSE ---
        # 防止 NaN 導致整數索引偏移，確保 Embargo 真空帶是物理上的 n_forward 根 K 線
        data.dropna(inplace=True)
        n_samples = len(data)
        
        # 數據是 15m 間隔，將天數轉換為 K 線根數 (24 * 4 = 96 根/天)
        train_size = self.train_window_days * 96
        test_size = self.test_window_days * 96
        
        current_train_start_idx = 0
        best_model = None
        
        while True:
            train_end_idx = current_train_start_idx + train_size
            
            # --- 真正的物理隔離 (基於 K 線根數，無涉絕對時間) ---
            test_start_idx = train_end_idx + self.n_forward
            test_end_idx = test_start_idx + test_size
            
            if test_end_idx > n_samples:
                break
            
            # --- 切割 (使用 iloc 確保絕對物理順序) ---
            train_set = data.iloc[current_train_start_idx : train_end_idx]
            test_set = data.iloc[test_start_idx : test_end_idx]
            
            if len(train_set) < 100 or len(test_set) < 20:
                current_train_start_idx += test_size
                continue

            # --- XGBOOST REGRESSOR ---
            model = XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.05,
                objective='reg:squarederror',
                random_state=42,
                tree_method='hist'
            )
            
            # 訓練時不進行隨機打亂
            model.fit(
                train_set[Registry_Lock.MASTER_FEATURES], 
                train_set['target']
            )
            
            preds = model.predict(test_set[Registry_Lock.MASTER_FEATURES])
            test_set = test_set.copy()
            test_set['pred'] = preds
            
            # Regression 評估：使用 MSE 或方向準確率
            mse = np.mean((preds - test_set['target'])**2)
            direction_correct = ((preds > 0) == (test_set['target'] > 0)).mean()
            
            
            
            window_info = {
                "train_end_idx": int(train_end_idx),
                "test_start_idx": int(test_start_idx),
                "mse": float(mse),
                "direction_accuracy": float(direction_correct)
            }
            self.manifest.append(window_info)
            best_model = model
            current_train_start_idx += test_size

        if best_model:
            os.makedirs('models', exist_ok=True)
            joblib.dump(best_model, 'models/h16_v2_wf.joblib')
            with open('models/training_manifest.json', 'w') as f:
                json.dump(self.manifest, f, indent=4)
            print("✅ Walk-forward training with Strict Embargo complete.")


