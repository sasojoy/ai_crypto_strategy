class DynamoMatrix:
    @staticmethod
    def get_params(regime_label):
        # 這是 v600 的靈魂：根據標籤切換參數集
        matrix = {
            0: {'z_score': 0.45, 'tp_mult': 4.5, 'be_trigger': 2.2, 'desc': 'TREND_HUNTER'},
            1: {'z_score': 1.10, 'tp_mult': 1.6, 'be_trigger': 0.7, 'desc': 'MEAN_REVERSION'},
            2: {'z_score': 9.99, 'tp_mult': 0.0, 'be_trigger': 0.0, 'desc': 'STAY_OUT'}
        }
        return matrix.get(regime_label, matrix[2])
