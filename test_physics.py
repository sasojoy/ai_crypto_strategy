

import unittest
import pandas as pd
import numpy as np
import yaml
from src.core.engine import Engine
from src.core.features import calculate_features, Registry_Lock

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
        
        self.assertEqual(len(features_df.columns), 19)
        self.assertFalse(features_df.isnull().values.any())
        
        # Verify Registry_Lock
        self.assertTrue(Registry_Lock.verify(features_df))

if __name__ == '__main__':
    unittest.main()

