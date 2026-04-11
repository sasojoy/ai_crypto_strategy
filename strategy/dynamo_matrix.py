class DynamoMatrix:
    @staticmethod
    def get_adaptive_params(regime_label):
        # 根據 GMM 標籤動態調整策略性格
        if regime_label == 0: # 趨勢市
            return {'tp_mult': 4.5, 'be_trigger': 1.8, 'risk_weight': 1.2}
        elif regime_label == 1: # 震盪市
            return {'tp_mult': 1.8, 'be_trigger': 0.8, 'risk_weight': 0.8}
        else: # 混亂市
            return {'tp_mult': 0, 'be_trigger': 0, 'risk_weight': 0}
