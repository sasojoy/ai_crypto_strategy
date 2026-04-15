

import pandas as pd
import numpy as np
from datetime import datetime
from src.indicators import calculate_ema, calculate_atr

class H16Strategy:
    def __init__(self):
        self.cooldown_period = 14400  # 4 hours
        self.last_trade_time = {}

    def calculate_size(self, balance, ml_score, volatility):
        """
        Position Sizing: balance * AI_score * (1/volatility)
        Normalized to a base risk factor.
        """
        base_risk = 0.002 # Base volatility target
        vol_factor = base_risk / max(volatility, 0.0001)
        # Cap vol_factor to avoid extreme sizing
        vol_factor = min(max(vol_factor, 0.5), 2.0)
        
        # Kelly-like scaling based on AI score
        kelly = 1.5 if ml_score >= 0.90 else (1.0 if ml_score >= 0.80 else 0.5)
        
        size = balance * 0.1 * kelly * vol_factor # 10% base allocation
        return min(size, balance * 0.5) # Max 50% of balance per trade

    def get_signal(self, symbol, ml_score, df_1h, df_15m):
        """
        H16 Predator Signal Logic - V1.6.5 MOMENTUM STRIKE
        """
        if df_1h is None or df_1h.empty or len(df_15m) < 24:
            return False, "Insufficient Data"

        current_price = df_15m['close'].iloc[-1]
        ema50_1h = calculate_ema(df_1h, 50).iloc[-1]
        ema200_1h = calculate_ema(df_1h, 200).iloc[-1]
        
        # 1. Momentum Filter: True Volume Z-Score + Price Direction
        vol_series = df_15m['volume'].iloc[-25:-1]
        avg_vol = vol_series.mean()
        std_vol = vol_series.std()
        current_vol = df_15m['volume'].iloc[-1]
        
        # Z-Score = (x - mean) / std
        vol_zscore = (current_vol - avg_vol) / std_vol if std_vol > 0 else 0
        
        # Price Direction Check: Current close must be > previous close
        price_up = df_15m['close'].iloc[-1] > df_15m['close'].iloc[-2]
        
        # Require Z-Score > 2.0 AND Price Up
        if vol_zscore < 2.0 or not price_up:
            reason = f"Low Momentum: Z={vol_zscore:.2f}" if vol_zscore < 2.0 else "Price Direction Down"
            return False, reason

        # 2. SHAP Correction: dist_ema200 clipping
        ema200_slope = (ema200_1h - calculate_ema(df_1h, 200).iloc[-2]) / ema200_1h
        threshold = 0.75
        if current_price < ema200_1h and ema200_slope < 0:
            threshold *= 1.2
            
        # 3. Squeeze Index Check
        bb_std = df_15m['close'].rolling(20).std().iloc[-1]
        bb_mean = df_15m['close'].rolling(20).mean().iloc[-1]
        bb_width = (bb_std * 4) / bb_mean
        
        if bb_width > 0.05:
            threshold += 0.05

        if ml_score < threshold:
            return False, f"AI Score {ml_score:.2f} < {threshold:.2f}"

        # 4. Trend Filter
        if current_price <= ema50_1h:
            atr = calculate_atr(df_1h, 14).iloc[-1]
            is_oversold = current_price < (ema50_1h - 1.5 * atr)
            if not (symbol == 'BARD/USDT' and is_oversold and ml_score >= 0.85):
                return False, "1H Trend Bearish"

        return True, "Predator Signal Confirmed"

    def get_exit_logic(self, entry_price, current_price, i, entry_index, df_15m, breakeven_active):
        """
        V1.9.0 REGAIN SOUL - ATR Dynamic SL & Multi-Level TP
        """
        bars_held = (i - entry_index)
        atr = calculate_atr(df_15m, 14).iloc[-1]
        
        # 1. ATR Dynamic Stop Loss (1.5 * ATR)
        sl_price = entry_price - (1.5 * atr)
        
        # 2. Multi-Level Trailing Take Profit
        # Level 1: 2.0 * ATR -> Move SL to Entry + Friction
        # Level 2: 3.5 * ATR -> Move SL to Entry + 1.5 * ATR
        new_breakeven_active = breakeven_active
        new_sl_price = sl_price
        
        if current_price >= (entry_price + 2.0 * atr):
            new_sl_price = max(new_sl_price, entry_price * (1 + 0.0018))
            new_breakeven_active = True
            
        if current_price >= (entry_price + 3.5 * atr):
            new_sl_price = max(new_sl_price, entry_price + 1.5 * atr)

        # 3. Time-based Exit (3-Bar Rule)
        time_exit = False
        if bars_held >= 3 and current_price < (entry_price + 0.2 * atr):
            time_exit = True
            
        # 4. Hard SL Check
        if current_price <= new_sl_price:
            return True, new_breakeven_active, new_sl_price

        return time_exit, new_breakeven_active, new_sl_price

