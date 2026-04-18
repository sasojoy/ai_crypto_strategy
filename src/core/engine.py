


import numpy as np

class Consistency_Guard:
    def __init__(self, friction_ratio=0.0018):
        self.friction_ratio = friction_ratio

    def verify_friction(self, qty, delta_price, profit):
        """
        物理斷言：Profit = (Qty * delta_price) - (Qty * 0.0018)
        """
        expected_friction = qty * self.friction_ratio
        expected_profit = (qty * delta_price) - expected_friction

        # 嚴格鎖死摩擦力計算，不允許任何偏差
        assert np.isclose(profit, expected_profit, atol=1e-8), \
            f"🚨 [PHYSICS VIOLATION] Expected profit: {expected_profit}, got: {profit}"
        return True

class Engine:
    def __init__(self, friction_ratio=0.0018):
        self.friction_ratio = friction_ratio
        self.guard = Consistency_Guard(friction_ratio=self.friction_ratio)

    def calculate_pnl(self, qty, entry_price, exit_price, side):
        """
        動態計算 PnL，嚴格執行 0.18% 摩擦力。
        """
        if side == 'long':
            delta_price = (exit_price - entry_price) / entry_price
        elif side == 'short':
            delta_price = (entry_price - exit_price) / entry_price
        else:
            raise ValueError("Invalid side. Must be 'long' or 'short'.")

        # Profit = (Qty * delta_price) - (Qty * 0.0018)
        profit = (qty * delta_price) - (qty * self.friction_ratio)

        # 物理常數鎖死
        self.guard.verify_friction(qty, delta_price, profit)

        return profit


