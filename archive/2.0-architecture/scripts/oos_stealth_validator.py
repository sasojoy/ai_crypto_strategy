import json
import pandas as pd
import numpy as np
import warnings
import os
from strategy.main import GoldilocksDispatcher
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

# 妳確認過的黃金參數 (v300.3-GOLDILOCKS)
STABLE_PARAMS = {
    'z_score': 0.48,
    'entropy': 0.90,
    'rsi_slope': 3,
    'tp_mult': 3.26,
    'be_trigger': 1.2
}

class OptimizedDispatcher(GoldilocksDispatcher):
    def get_signal(self, df_15m, symbol="UNKNOWN", df_1h=None):
        sig, params = super().get_signal(df_15m, symbol, df_1h)
        if sig and 'tp_price' in params:
            latest_15m = df_15m.iloc[-1]
            current_atr = latest_15m.get('atr', latest_15m['close'] * 0.01)
            if sig == 'LONG':
                params['tp_price'] = latest_15m['close'] + (current_atr * STABLE_PARAMS['tp_mult'])
                params['be_trigger_price'] = latest_15m['close'] + (current_atr * STABLE_PARAMS['be_trigger'])
            else:
                params['tp_price'] = latest_15m['close'] - (current_atr * STABLE_PARAMS['tp_mult'])
                params['be_trigger_price'] = latest_15m['close'] - (current_atr * STABLE_PARAMS['be_trigger'])
        return sig, params

class DualTFWrapper:
    def __init__(self, dispatcher, df_1h):
        self.dispatcher = dispatcher
        self.df_1h = df_1h
    def get_signal(self, df_15m_slice, symbol="UNKNOWN"):
        ts = df_15m_slice['timestamp'].iloc[-1]
        h_slice = self.df_1h[self.df_1h['timestamp'] <= ts]
        return self.dispatcher.get_signal(df_15m_slice, symbol, df_1h=h_slice)

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
fetcher = BinanceFetcher()
trainer = ModelTrainer()
results = {}

print("🤫 進入靜默驗證模式，正在穿透樣本外數據...")

dispatcher = OptimizedDispatcher(
    z_score_threshold=STABLE_PARAMS['z_score'],
    entropy_threshold=STABLE_PARAMS['entropy'],
    rsi_slope_min=STABLE_PARAMS['rsi_slope']
)

for s in symbols:
    try:
        # 抓取 180 天數據
        limit_15m = 180 * 96 + 200
        limit_1h = 180 * 24 + 200
        df_15m_raw = fetcher.fetch_ohlcv(s, "15m", limit=limit_15m)
        df_1h_raw = fetcher.fetch_ohlcv(s, "1h", limit=limit_1h)
        
        # 提取樣本外片段 (前半段)
        df_15m_oos_raw = df_15m_raw.iloc[:len(df_15m_raw)//2].copy()
        df_1h_oos_raw = df_1h_raw.iloc[:len(df_1h_raw)//2].copy()
        
        df_15m = trainer.feature_engineering(df_15m_oos_raw)
        df_1h = trainer.feature_engineering(df_1h_oos_raw)
        
        df_15m['symbol'] = s
        df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
        df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
        
        engine = BacktestEngine()
        wrapper = DualTFWrapper(dispatcher, df_1h)
        report_raw = engine.run(df_15m, wrapper)
        trades = report_raw.get('all_trades', [])
        
        n = len(trades)
        if n > 0:
            tdf = pd.DataFrame(trades)
            pos_pnl = tdf[tdf['pnl'] > 0]['pnl'].sum()
            neg_pnl = abs(tdf[tdf['pnl'] <= 0]['pnl'].sum())
            pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
            wr = (tdf['pnl'] > 0).sum() / n
            
            tdf['cum_balance'] = tdf['pnl'].cumsum() + 10000
            max_dd = ((tdf['cum_balance'].cummax() - tdf['cum_balance']) / tdf['cum_balance'].cummax()).max()
        else:
            pf, wr, max_dd = 0, 0, 0
            
        results[s] = {
            'N': n,
            'PF': round(pf, 2),
            'MaxDD': f"{max_dd:.2%}",
            'WinRate': f"{wr:.2%}"
        }
    except Exception as e:
        results[s] = {"error": str(e)}

with open('oos_results.json', 'w') as f:
    json.dump(results, f, indent=4)

print("✅ 驗證完成，結果已寫入 oos_results.json")
