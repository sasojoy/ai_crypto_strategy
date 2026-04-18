



import unittest
from backtest.engine import Engine

class TestEngineFriction(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()

    def test_friction_precision(self):
        """
        參數化測試：驗證 1000, 2000, 5000 USDT 倉位。
        """
        test_cases = [
            {"qty": 1000, "expected_friction": 1.8},
            {"qty": 2000, "expected_friction": 3.6},
            {"qty": 5000, "expected_friction": 9.0},
        ]
        
        entry_price = 100
        exit_price = 105 # 獲利 5%
        
        for case in test_cases:
            qty = case["qty"]
            expected_f = case["expected_friction"]
            
            # 透過引擎計算
            pnl = self.engine.calculate_pnl(qty, entry_price, exit_price, 'long')
            
            # 原始利潤 = qty * 0.05
            raw_profit = qty * 0.05
            expected_pnl = raw_profit - expected_f
            
            self.assertAlmostEqual(pnl, expected_pnl, places=8)
            print(f"✅ [FRICTION TEST] Qty: {qty} USDT | Expected Friction: {expected_f} | PnL: {pnl}")

if __name__ == '__main__':
    unittest.main()



