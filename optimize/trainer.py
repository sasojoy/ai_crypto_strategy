


import pandas as pd
import numpy as np
import joblib
import json
import os
from xgboost import XGBClassifier
from data.features import calculate_features, Registry_Lock

class H16Trainer:
    def __init__(self, train_window_days=30, test_window_days=7, friction=0.0018, n_forward=12):
        self.train_window_days = train_window_days
        self.test_window_days = test_window_days
        self.friction = friction
        self.n_forward = n_forward
        self.manifest = []

    def prepare_data(self, df, df_btc):
        X = calculate_features(df, df_btc)
        returns = df.set_index('timestamp')['close'].shift(-self.n_forward) / df.set_index('timestamp')['close'] - 1
        y = pd.Series(0, index=returns.index)
        y[returns > self.friction] = 1
        y[returns < -self.friction] = 2
        data = pd.concat([X, y.rename('target'), returns.rename('raw_return')], axis=1).dropna()
        return data

    def walk_forward_train(self, data):
        """
        走動式驗證 (Walk-forward Validation)
        實施「Embargo」物理隔離，基於整數索引 (iloc) 確保絕對物理順序。
        """
        n_samples = len(data)
        
        # 假設數據是 1h 間隔，將天數轉換為 K 線根數
        train_size = self.train_window_days * 24
        test_size = self.test_window_days * 24
        
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

            # --- XGBOOST ARCHITECTURE 2.0 ---
            # 顯式宣告不使用 shuffle
            model = XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.05,
                objective='multi:softprob',
                num_class=3,
                random_state=42,
                tree_method='hist',
                enable_categorical=False # 確保數據一致性
            )
            
            # 訓練時不進行隨機打亂
            model.fit(
                train_set[Registry_Lock.MASTER_FEATURES], 
                train_set['target']
            )
            
            preds = model.predict(test_set[Registry_Lock.MASTER_FEATURES])
            test_set = test_set.copy()
            test_set['pred'] = preds
            
            long_signals = test_set[test_set['pred'] == 1]
            short_signals = test_set[test_set['pred'] == 2]
            long_expectancy = (long_signals['raw_return'] - self.friction).mean() if not long_signals.empty else 0
            short_expectancy = (-short_signals['raw_return'] - self.friction).mean() if not short_signals.empty else 0
            
            win_rate = (preds == test_set['target']).mean()
            
            window_info = {
                "train_end_idx": int(train_end_idx),
                "test_start_idx": int(test_start_idx),
                "win_rate": float(win_rate),
                "expectancy": float(long_expectancy + short_expectancy)
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


