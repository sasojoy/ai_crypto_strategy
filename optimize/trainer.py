


import pandas as pd
import numpy as np
import joblib
import json
import os
import optuna
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

    def optimize_hyperparameters(self, train_set, val_set):
        """
        使用 Optuna 在 Validation Set 上尋優 Sharpe Ratio
        """
        def objective(trial):
            params = {
                'n_estimators': 100,
                'max_depth': trial.suggest_int('max_depth', 3, 10),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2, log=True),
                'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                'objective': 'reg:squarederror',
                'random_state': 42,
                'tree_method': 'hist',
                'n_jobs': -1
            }
            
            model = XGBRegressor(**params)
            model.fit(train_set[Registry_Lock.MASTER_FEATURES], train_set['target'])
            
            preds = model.predict(val_set[Registry_Lock.MASTER_FEATURES])
            
            # 計算模擬收益 (簡化版) 用於優化 Sharpe
            # 假設信號強度 > 0.002 做多， < -0.002 做空
            signals = np.where(preds > 0.002, 1, np.where(preds < -0.002, -1, 0))
            # 實際收益 = 信號 * 實際變動 - 摩擦力
            # 注意：這裡的 target 是未來 n_forward 的累積收益
            # 為了簡化，我們直接用 target 作為單步收益的代理
            step_returns = signals * val_set['target'] - np.abs(signals) * self.friction
            
            if np.std(step_returns) == 0:
                return -10.0
            
            sharpe = np.mean(step_returns) / np.std(step_returns) * np.sqrt(35040 / self.n_forward)
            return sharpe

        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=20)
        return study.best_params

    def walk_forward_train(self, data):
        """
        走動式驗證 (Walk-forward Validation)
        實施「Embargo」物理隔離，基於整數索引 (iloc) 確保絕對物理順序。
        """
        data.dropna(inplace=True)
        n_samples = len(data)
        
        # 數據是 15m 間隔，將天數轉換為 K 線根數
        train_size = self.train_window_days * 96
        val_size = self.test_window_days * 96 # 使用 test_window_days 作為 validation
        test_size = self.test_window_days * 96
        
        current_train_start_idx = 0
        best_model = None
        
        while True:
            train_end_idx = current_train_start_idx + train_size
            
            # --- Embargo for Validation ---
            val_start_idx = train_end_idx + self.n_forward
            val_end_idx = val_start_idx + val_size
            
            # --- Embargo for Test ---
            test_start_idx = val_end_idx + self.n_forward
            test_end_idx = test_start_idx + test_size
            
            if test_end_idx > n_samples:
                break
            
            train_set = data.iloc[current_train_start_idx : train_end_idx]
            val_set = data.iloc[val_start_idx : val_end_idx]
            test_set = data.iloc[test_start_idx : test_end_idx]
            
            if len(train_set) < 100 or len(val_set) < 20 or len(test_set) < 20:
                current_train_start_idx += test_size
                continue

            # --- Hyperparameter Optimization on Validation Set ---
            best_params = self.optimize_hyperparameters(train_set, val_set)
            
            # --- Train Final Model for this window ---
            model = XGBRegressor(**best_params)
            model.fit(train_set[Registry_Lock.MASTER_FEATURES], train_set['target'])
            
            preds = model.predict(test_set[Registry_Lock.MASTER_FEATURES])
            test_set = test_set.copy()
            test_set['pred'] = preds
            
            mse = np.mean((preds - test_set['target'])**2)
            direction_correct = ((preds > 0) == (test_set['target'] > 0)).mean()
            
            window_info = {
                "train_end_idx": int(train_end_idx),
                "test_start_idx": int(test_start_idx),
                "mse": float(mse),
                "direction_accuracy": float(direction_correct),
                "best_params": best_params
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


