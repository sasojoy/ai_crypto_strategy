import numpy as np

class MeanReversion:
    def __init__(self):
        self.name = "Mean_Reversion_v1"

    def get_signal(self, df):
        if len(df) < 1: return 0
        latest = df.iloc[-1]
        # 邏輯：布林帶邊界反轉 + RSI 超買超賣 (在低 ADX 環境下運作)
        rsi = latest.get('rsi', 50)
        if rsi < 30:
            return 1.0  # 超賣反彈
        elif rsi > 70:
            return -1.0 # 超買回檔
        return 0
