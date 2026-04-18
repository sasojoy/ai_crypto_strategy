



import unittest
from backtest.engine import Engine

class TestEngineFriction(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()

    def test_friction_precision(self):
        """
        物理常數單元測試：模擬 2000 USDT 倉位。
        如果總摩擦力不是精準的 3.6 USDT，則測試失敗。
        """
        qty_usdt = 2000
        entry_price = 100
        exit_price = 105 # 獲利 5%
        
        # 計算多單 PnL
        # Profit = (Qty * Delta Price) - (Qty * 0.0018)
        # Friction = 2000 * 0.0018 = 3.6
        
        expected_friction = qty_usdt * 0.0018
        self.assertEqual(expected_friction, 3.6)
        
        # 透過引擎計算
        pnl = self.engine.calculate_pnl(qty_usdt, entry_price, exit_price, 'long')
        
        # 原始利潤 = 2000 * (105-100)/100 = 100
        # 扣除摩擦力後 = 100 - 3.6 = 96.4
        self.assertAlmostEqual(pnl, 96.4)
        
        print(f"\n[FRICTION TEST] Qty: {qty_usdt} USDT")
        print(f"Expected Friction: {expected_friction} USDT")
        print(f"Calculated PnL: {pnl} USDT")
        print("✅ 3.6 USDT Friction Assertion Passed.")

if __name__ == '__main__':
    unittest.main()



