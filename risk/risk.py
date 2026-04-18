



class RiskManager:
    def __init__(self, max_risk_per_trade=0.02):
        self.max_risk_per_trade = max_risk_per_trade

    def validate_position_size(self, balance, position_value):
        """
        實施單筆 2% 風控限制。
        """
        risk_amount = balance * self.max_risk_per_trade
        if position_value > balance:
            # 這裡假設不允許槓桿超過 1 倍，或根據具體需求調整
            return False
        
        # 實際風控邏輯應根據 Stop Loss 計算 Risk
        # 這裡簡單斷言單筆倉位價值不應導致超過 2% 的潛在損失（假設 100% 損失情況）
        # 在實際交易中，這會結合 Stop Loss 距離來計算
        return position_value <= balance * self.max_risk_per_trade * 50 # 範例：允許 50 倍槓桿下的 2% 風險



