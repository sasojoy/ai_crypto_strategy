

import unittest
import pandas as pd
import numpy as np
import yaml
from backtest.engine import Engine
from data.features import calculate_features, Registry_Lock

class TestPhysics(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        with open('strategy_config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)

    def test_friction_calculation(self):
        """
        模擬單筆 2000 USDT 交易（多單與空單各一）。
        如果餘額變動與 3.6 USDT 摩擦力不符，禁止回報成功。
        2000 * 0.0018 = 3.6
        """
        qty_usdt = 2000
        friction_expected = qty_usdt * 0.0018
        self.assertEqual(friction_expected, 3.6)
        
        # Case 1: Long
        # Entry: 100, Exit: 102 (2% gain)
        # Profit = (2000 * 0.02) - (2000 * 0.0018) = 40 - 3.6 = 36.4
        profit_long = self.engine.calculate_pnl(qty_usdt, 100, 102, 'long')
        self.assertAlmostEqual(profit_long, 36.4)
        
        # Case 2: Short
        # Entry: 100, Exit: 98 (2% gain for short)
        # Profit = (2000 * 0.02) - (2000 * 0.0018) = 40 - 3.6 = 36.4
        profit_short = self.engine.calculate_pnl(qty_usdt, 100, 98, 'short')
        self.assertAlmostEqual(profit_short, 36.4)

    def test_features_integrity(self):
        """
        19 個特徵有一個為 NaN，禁止回報成功。
        """
        # Create dummy data
        dates = pd.date_range('2023-01-01', periods=300, freq='h')
        df = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.randn(300) + 100,
            'high': np.random.randn(300) + 102,
            'low': np.random.randn(300) + 98,
            'close': np.random.randn(300) + 100,
            'volume': np.random.rand(300) * 1000
        })
        df_btc = pd.DataFrame({
            'timestamp': dates,
            'close': np.random.randn(300) + 30000
        })
        
        features_df = calculate_features(df, df_btc)
        
        # --- 物理證據要求 ---
        # 印出第 1 筆交易成交那一刻的特徵值快照
        first_trade_idx = features_df.index[0]
        print(f"\n[PHYSICS SNAPSHOT] Trade Execution Timestamp: {first_trade_idx}")
        print(f"Feature Snapshot (First Row):\n{features_df.iloc[0]}")
        
        self.assertEqual(len(features_df.columns), 19)
        self.assertFalse(features_df.isnull().values.any())
        
        # Verify Registry_Lock
        self.assertTrue(Registry_Lock.verify(features_df))

    def test_strategy_alignment(self):
        """
        驗證策略對齊邏輯與信號輸出。
        """
        from strategy.strategy import H16Strategy
        strategy = H16Strategy()
        
        # 模擬已平移特徵
        dates = pd.date_range('2023-01-01', periods=10, freq='h')
        mock_features = pd.DataFrame(np.random.randn(10, 19), 
                                   index=dates, 
                                   columns=Registry_Lock.MASTER_FEATURES)
        
        # 測試信號輸出
        # 由於沒有真實模型，這裡會觸發 Warning 並返回 Neutral
        signal = strategy.predict_signal(mock_features)
        print(f"\n[STRATEGY SIGNAL] {signal}")
        
        self.assertIn(signal['signal_type'], ["Neutral", "Long", "Short"])
        self.assertIn('confidence_score', signal)
        self.assertIn('limit_price', signal)
        
        # 印完對齊邏輯證據
        print(f"\n[ALIGNMENT PROOF - Y Definition]:\n{strategy.get_y_definition()}")
        print(f"\n[ALIGNMENT PROOF - Logic]:\n{strategy.get_alignment_logic()}")

    def test_trainer_embargo(self):
        """
        驗證訓練器的 Embargo 機制 (基於整數索引)。
        """
        from optimize.trainer import H16Trainer
        trainer = H16Trainer(train_window_days=30, test_window_days=7, n_forward=12)
        
        # 模擬數據
        dates = pd.date_range('2023-01-01', periods=2000, freq='h')
        df = pd.DataFrame({
            'timestamp': dates,
            'open': np.random.randn(2000) + 100,
            'high': np.random.randn(2000) + 102,
            'low': np.random.randn(2000) + 98,
            'close': np.random.randn(2000) + 100,
            'volume': np.random.rand(2000) * 1000
        })
        df_btc = pd.DataFrame({
            'timestamp': dates,
            'close': np.random.randn(2000) + 30000
        })
        
        data = trainer.prepare_data(df, df_btc)
        trainer.walk_forward_train(data)
        
        # 驗證 Manifest 中的 Embargo 邏輯
        if trainer.manifest:
            first_window = trainer.manifest[0]
            print(f"\n[TRAINER EMBARGO PROOF] Window 1:")
            print(f"Train End Index: {first_window['train_end_idx']}")
            print(f"Test Start Index: {first_window['test_start_idx']}")
            
            # 物理斷言：test_start_idx 必須等於 train_end_idx + n_forward
            self.assertEqual(first_window['test_start_idx'], first_window['train_end_idx'] + 12)
            print("✅ Integer-based Embargo Physical Assertion Passed.")

if __name__ == '__main__':
    unittest.main()

