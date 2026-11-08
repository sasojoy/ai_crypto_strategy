


from risk.risk_manager import RiskManager

class StrategyLogic:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        self.risk_manager = RiskManager(config_path)

    def generate_signal(self, trend_data_1h, signal_data_15m, ml_score, account_balance):
        """
        Generate trading signal and calculate order size.
        """
        # Basic trend filter (EMA200 logic can be added here)
        # For now, we assume trend_data_1h and signal_data_15m are pre-processed
        
        # Calculate position size using RiskManager
        order_size = self.risk_manager.get_position_size(ml_score, account_balance)
        
        # Sovereign Filter decision
        # Assuming trend_data_1h contains 'BTC' and 'ETH' price series
        # btc_prices = trend_data_1h.get('BTC', [])
        # eth_prices = trend_data_1h.get('ETH', [])
        # preferred_asset = self.risk_manager.sovereign_filter(btc_prices, eth_prices)
        
        return {
            'order_size': order_size,
            'ml_score': ml_score,
            'status': 'ready' if ml_score >= 0.82 else 'hold'
        }


