

import yaml
import os
import numpy as np

class RiskManager:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.base_risk = 0.01
        self.elite_risk = 0.01
        self.ml_threshold = self.config.get('ml_threshold', 0.92)
        self.friction_rate = self.config.get('friction', {}).get('fee', 0.0004) + self.config.get('friction', {}).get('slippage', 0.0005)
        
        # Sniper Parameters
        self.tp1_ratio = 1.0  # Take 50% profit at 1.0 * ATR
        self.tp_partial_pct = 0.5
        self.sl_atr_mult = 0.8

    def get_slippage_buffer(self, df_1m):
        """
        Volatility-Based Slippage (Iteration 161.0 - The Aegis)
        If 1m Volatility > 2%, increase slippage from 0.0005 to 0.0015.
        """
        if df_1m is None or len(df_1m) < 20:
            return 0.0005
            
        # Calculate 1m volatility (std of log returns)
        log_ret = np.log(df_1m['close'] / df_1m['close'].shift(1))
        vol = log_ret.std()
        
        # Threshold: 2% annualized or relative? 
        # User said "1m Volatility > 2%". Let's assume 1m candle range or std.
        # If max-min range > 2% in 1m, it's extreme.
        recent_range = (df_1m['high'].iloc[-1] - df_1m['low'].iloc[-1]) / df_1m['low'].iloc[-1]
        
        if recent_range > 0.02:
            return 0.0015
        return 0.0005

    def get_position_size(self, ml_score, account_balance, entry_price, stop_loss_price):
        """
        Calculate position size based on ML score and Stop Loss distance.
        Formula: (Balance * Risk_Percent) / Stop_Loss_Distance_Pct
        """
        risk_percent = self.elite_risk if ml_score >= self.ml_threshold else self.base_risk
        
        sl_distance_pct = abs(entry_price - stop_loss_price) / entry_price
        if sl_distance_pct == 0:
            return 0
            
        risk_amount = account_balance * risk_percent
        position_size = risk_amount / sl_distance_pct
        
        return position_size

    def sovereign_filter(self, btc_price_series, eth_price_series, window=10):
        """
        Calculate the slope of (BTC_Price / ETH_Price).
        If slope > 0, favor BTC; if slope < 0, favor ETH.
        """
        if len(btc_price_series) < window or len(eth_price_series) < window:
            return 'BTC'
            
        ratios = np.array(btc_price_series[-window:]) / np.array(eth_price_series[-window:])
        x = np.arange(len(ratios))
        slope, _ = np.polyfit(x, ratios, 1)
        
        return 'BTC' if slope > 0 else 'ETH'

    def get_tp_sl(self, entry_price, atr, position_type='long', ratio=2.0):
        """
        Calculate dynamic Take-Profit and Stop-Loss based on ATR and a target ratio.
        Take Profit = Entry + (ratio * ATR)
        Stop Loss = Entry - ATR
        """
        sl_distance = atr 
        tp_distance = atr * ratio
        
        if position_type == 'long':
            tp_price = entry_price + tp_distance
            sl_price = entry_price - sl_distance
        else:
            tp_price = entry_price - tp_distance
            sl_price = entry_price + sl_distance
            
        return tp_price, sl_price

