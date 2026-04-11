import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

class RegimeClassifier:
    def __init__(self, n_regimes=3):
        self.model = GaussianMixture(n_components=n_regimes, covariance_type='full', random_state=42)
        
    def predict_regime(self, df):
        if len(df) < 500: return 0
        
        # 提取波動率與趨勢特徵
        returns = np.log(df['close'] / df['close'].shift(1)).fillna(0)
        vol = (df['high'] - df['low']) / df['close']
        features = np.column_stack([returns, vol])
        
        # 性能優化：每 100 根 K 線才重新訓練一次
        if not hasattr(self, '_last_fit_len') or len(df) - self._last_fit_len >= 100:
            self.model.fit(features[-500:])
            self._last_fit_len = len(df)
            
            # 確保標籤含義一致 (依據波動率排序)
            # Regime 0: 中等波動 (趨勢), Regime 1: 低波動 (震盪), Regime 2: 高波動 (混亂)
            means = self.model.means_[:, 1] # 使用 vol 特徵的均值
            self._sorted_indices = np.argsort(means) # 0: lowest vol, 1: medium, 2: highest
            # 重新映射以符合 Dispatcher: 0: Trend (Medium), 1: Range (Low), 2: Chaos (High)
            # 我們將 medium 設為 0, low 設為 1, high 設為 2
            self._label_map = {self._sorted_indices[1]: 0, self._sorted_indices[0]: 1, self._sorted_indices[2]: 2}

        raw_regime = self.model.predict(features[-1:])[0]
        return self._label_map.get(raw_regime, 2)
