from strategy.metadata import *

class RiskManager:
    def __init__(self, config_path=None):
        pass

    def get_position_size(self, risk_per_trade, balance, entry_price, sl_price):
        if entry_price == sl_price: return 0
        risk_amt_per_unit = abs(entry_price - sl_price)
        if risk_amt_per_unit <= 0: return 0
        # 返回單位數 (Units)
        return (balance * risk_per_trade) / risk_amt_per_unit

    def calculate_alpha_size(self, balance, confidence, entry_price, sl_price):
        if confidence < GHOST_LOW_THRESHOLD: return 0
        
        # 判定 Risk Ratio
        current_risk = BASE_RISK_PER_TRADE
        if confidence >= GHOST_HIGH_THRESHOLD:
            alpha_factor = (confidence - GHOST_HIGH_THRESHOLD) / (1.0 - GHOST_HIGH_THRESHOLD)
            current_risk = BASE_RISK_PER_TRADE * (1 + (alpha_factor * (ALPHA_MULTIPLIER - 1)))
        
        risk_amt_per_unit = abs(entry_price - sl_price)
        if risk_amt_per_unit <= 0: return 0
        
        # 計算單位數
        units = (balance * current_risk) / risk_amt_per_unit
        
        # 曝險上限檢查 (Notional Value / Balance)
        max_units = (balance * MAX_TOTAL_EXPOSURE) / entry_price
        return min(units, max_units)
