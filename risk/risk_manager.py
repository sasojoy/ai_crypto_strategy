

import yaml
import os

class RiskManager:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.base_risk = self.config.get('base_risk', 0.015)
        self.elite_risk = self.config.get('elite_risk', 0.06)
        self.ml_threshold = self.config.get('ml_threshold', 0.92)
        self.friction = self.config.get('friction', {}).get('fee', 0.0004) + self.config.get('friction', {}).get('slippage', 0.0005)

    def get_position_size(self, ml_score, account_balance):
        """
        Calculate position size based on ML score.
        """
        risk_percent = self.elite_risk if ml_score >= self.ml_threshold else self.base_risk
        
        # Adjust for friction (0.0009)
        adjusted_risk = risk_percent * (1 - self.friction)
        
        return account_balance * adjusted_risk

    def sovereign_filter(self, btc_price_series, eth_price_series):
        """
        Decide fund allocation based on BTC/ETH price ratio trend.
        Returns 'BTC' if BTC is stronger, otherwise 'ETH'.
        """
        if len(btc_price_series) < 2 or len(eth_price_series) < 2:
            return 'BTC' # Default to BTC
            
        ratio_current = btc_price_series[-1] / eth_price_series[-1]
        ratio_previous = btc_price_series[-2] / eth_price_series[-2]
        
        if ratio_current > ratio_previous:
            return 'BTC'
        else:
            return 'ETH'

    def check_break_even(self, entry_price, current_price, atr, position_type='long'):
        """
        Move Stop-Loss to entry price when profit reaches 1.5 * ATR.
        Returns True if break-even should be triggered.
        """
        threshold = 1.5 * atr
        if position_type == 'long':
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price
            
        return profit >= threshold

