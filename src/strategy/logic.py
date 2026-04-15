

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class DualTrackStrategy:
    """
    Iteration 94.1: Dual-Track Diversion System
    - BTC/ETH: 1H Cycle, Threshold 0.85
    - Others: 15m Cycle, Threshold 0.75
    """
    def __init__(self):
        self.last_trade_time = {}
        self.cooldown_period = timedelta(hours=4)
        self.symbol_map = {
            'BTC/USDT': '1h',
            'ETH/USDT': '1h',
            'SOL/USDT': '15m',
            'FET/USDT': '15m',
            'NEAR/USDT': '15m',
            'AVAX/USDT': '15m',
            'ARB/USDT': '15m'
        }

    def get_timeframe(self, symbol):
        return self.symbol_map.get(symbol, '15m')

    def get_threshold(self, symbol):
        return 0.85 if self.get_timeframe(symbol) == '1h' else 0.75

    def get_weight(self, symbol):
        if symbol == 'BTC/USDT': return 0.5
        if symbol in ['SOL/USDT', 'FET/USDT']: return 0.25
        return 0.15

    def check_cooldown(self, symbol, current_time):
        if symbol not in self.last_trade_time:
            return True
        return (current_time - self.last_trade_time[symbol]) >= self.cooldown_period

    def get_signal(self, symbol, ml_score, df_1h=None):
        """
        H16 Optimized Signal Logic
        - BARD/USDT: Allows oversold rebound entry even if trend is bearish
        """
        # 1. 1H Trend Filter with H16 Exception
        if df_1h is not None and not df_1h.empty:
            from src.indicators import calculate_ema
            ema50 = calculate_ema(df_1h, 50).iloc[-1]
            current_price = df_1h['close'].iloc[-1]
            
            # H16 Exception for BARD: Physical Oversold + AI Confirmation
            from src.indicators import calculate_atr
            atr = calculate_atr(df_1h, 14).iloc[-1]
            is_oversold = current_price < (ema50 - 1.5 * atr)
            
            if symbol == 'BARD/USDT' and is_oversold and ml_score >= 0.65:
                pass # Allow entry in bearish trend if severely oversold
            elif current_price <= ema50:
                return False, "1H Trend Bearish"

        # 2. Cooldown Check
        now = datetime.utcnow()
        if not self.check_cooldown(symbol, now):
            return False, "Cooldown Active"

        # 3. AI Threshold Check
        threshold = self.get_threshold(symbol)
        if ml_score >= threshold:
            return True, f"AI Signal ({ml_score:.2f} >= {threshold})"
        
        return False, f"AI Score Low ({ml_score:.2f} < {threshold})"

    def get_trade_params(self, symbol):
        """
        Iteration 116.0 Soul: Tiered Slippage (5-30bps)
        """
        slippage_map = {
            'BTC/USDT': 0.0005,  # 5bps
            'ETH/USDT': 0.0008,  # 8bps
            'SOL/USDT': 0.0015,  # 15bps
            'FET/USDT': 0.0025,  # 25bps
            'NEAR/USDT': 0.0020, # 20bps
            'AVAX/USDT': 0.0020, # 20bps
            'ARB/USDT': 0.0030   # 30bps
        }
        slippage = slippage_map.get(symbol, 0.0020)
        
        tf = self.get_timeframe(symbol)
        if tf == '1h':
            return {'tp_pct': 0.05, 'sl_pct': 0.02, 'slippage_comp': slippage}
        else:
            return {'tp_pct': 0.03, 'sl_pct': 0.015, 'slippage_comp': slippage}

    def record_trade(self, symbol):
        self.last_trade_time[symbol] = datetime.utcnow()

