import numpy as np

class TrendFollower:
    def __init__(self):
        self.name = "Trend_Follower_v1"

    def get_signal(self, df):
        if len(df) < 1: return 0
        latest = df.iloc[-1]
        # 邏輯：1H EMA200 以上 + ADX 走強
        # 注意：trainer.py 中計算的是 ema_trend (800 bars)
        ema_trend = latest.get('ema_trend', latest['close'])
        is_uptrend = latest['close'] > ema_trend
        is_strong = latest.get('adx', 0) > 25
        
        if is_uptrend and is_strong:
            return 1.0  # 多頭訊號
        elif not is_uptrend and is_strong:
            return -1.0 # 空頭訊號
        return 0
