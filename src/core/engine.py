

import pandas as pd
import numpy as np

class TradingAccount:
    def __init__(self, initial_balance=10000):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.fee_rate = 0.0004
        self.slippage_rate = 0.0005
        self.fixed_pos_size = 2000  # [V1.8.0] Mandatory 20% Position Size
        self.trades = []

    def execute_trade(self, symbol, entry_time, exit_time, entry_price, exit_price, pos_size, reason=""):
        # Force fixed position size for audit integrity
        actual_pos_size = self.fixed_pos_size
        
        price_change = (exit_price - entry_price) / entry_price
        # Total friction = (0.04% fee + 0.05% slippage) * 2 (entry & exit) = 0.18%
        friction_ratio = (self.fee_rate + self.slippage_rate) * 2
        
        profit_amount = (actual_pos_size * price_change) - (actual_pos_size * friction_ratio)
        self.balance += profit_amount
        
        trade_record = {
            'symbol': symbol,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'profit_pct': (profit_amount / actual_pos_size) * 100,
            'balance': self.balance,
            'reason': reason
        }
        self.trades.append(trade_record)
        return trade_record

    def get_equity_curve(self):
        return pd.DataFrame(self.trades)

class MarketEnvironment:
    @staticmethod
    def get_volatility_level(df, window=24):
        """
        Calculate market volatility level (Low/Med/High)
        """
        if len(df) < window:
            return "Med", 0.0025
        
        vol = df['close'].pct_change().rolling(window).std().iloc[-1]
        if pd.isna(vol): vol = 0.0025
        
        if vol < 0.0015:
            return "Low", vol
        elif vol < 0.0035:
            return "Med", vol
        else:
            return "High", vol

