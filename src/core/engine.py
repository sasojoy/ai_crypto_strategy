
import numpy as np

class Consistency_Guard:
    @staticmethod
    def verify_friction(qty, delta_price, profit):
        """
        Profit = (Qty * delta_price) - (Qty * 0.0018)
        """
        expected_friction = qty * 0.0018
        expected_profit = (qty * delta_price) - expected_friction
        
        # Use assert to lock the friction calculation
        assert np.isclose(profit, expected_profit), f"Friction mismatch! Expected profit: {expected_profit}, got: {profit}"
        return True

class Engine:
    def __init__(self):
        self.guard = Consistency_Guard()

    def calculate_pnl(self, qty, entry_price, exit_price, side):
        # delta_price is the relative price change
        if side == 'long':
            delta_price = (exit_price - entry_price) / entry_price
        elif side == 'short':
            delta_price = (entry_price - exit_price) / entry_price
        else:
            raise ValueError("Invalid side. Must be 'long' or 'short'.")
        
        # Profit = (Qty * delta_price) - (Qty * 0.0018)
        profit = (qty * delta_price) - (qty * 0.0018)
        
        # Consistency Guard Lock
        self.guard.verify_friction(qty, delta_price, profit)
        
        return profit
