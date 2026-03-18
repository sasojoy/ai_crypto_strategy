
import unittest
import pandas as pd
import numpy as np
from src.indicators import calculate_rsi, calculate_ema, calculate_atr

class TestIndicators(unittest.TestCase):
    def test_calculate_ema(self):
        # Create a simple series
        data = pd.DataFrame({'close': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]})
        period = 5
        ema = calculate_ema(data, period)
        
        # EMA should have the same length
        self.assertEqual(len(ema), len(data))
        # Last value should be greater than the first for an uptrend
        self.assertTrue(ema.iloc[-1] > ema.iloc[0])
        # Check if it's a Series
        self.assertTrue(isinstance(ema, pd.Series))

    def test_calculate_rsi(self):
        # Create a series that goes up then down
        prices = [10, 12, 14, 16, 18, 20, 18, 16, 14, 12, 10]
        data = pd.DataFrame({'close': prices})
        rsi = calculate_rsi(data, period=5)
        
        self.assertEqual(len(rsi), len(data))
        # RSI should be between 0 and 100
        valid_rsi = rsi.dropna()
        self.assertTrue(valid_rsi.min() >= 0)
        self.assertTrue(valid_rsi.max() <= 100)
        # After price drop, RSI should decrease
        self.assertTrue(rsi.iloc[-1] < rsi.iloc[5])

    def test_calculate_atr(self):
        # Create data with constant range
        data = pd.DataFrame({
            'high': [110, 110, 110, 110, 110],
            'low': [100, 100, 100, 100, 100],
            'close': [105, 105, 105, 105, 105]
        })
        atr = calculate_atr(data, period=3)
        
        self.assertEqual(len(atr), len(data))
        # ATR should be around 10 since high-low is 10
        self.assertAlmostEqual(atr.iloc[-1], 10.0)

if __name__ == '__main__':
    unittest.main()
