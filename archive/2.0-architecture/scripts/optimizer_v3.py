import optuna
import sys
import pandas as pd
import numpy as np
import warnings
from strategy.main import GoldilocksDispatcher, StrategyMain
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

def log(msg):
    print(msg); sys.stdout.flush()

log("📡 預載 90 天多幣種數據...")
fetcher = BinanceFetcher()
trainer = ModelTrainer()
symbols = ["BTCUSDT", "ETHUSDT"]
days = 90
limit_15m = days * 96 + 200
limit_1h = days * 24 + 200

data_cache = {}
for s in symbols:
    log(f"正在抓取 {s}...")
    df_15m_raw = fetcher.fetch_ohlcv(s, "15m", limit=limit_15m)
    df_1h_raw = fetcher.fetch_ohlcv(s, "1h", limit=limit_1h)
    
    df_15m = trainer.feature_engineering(df_15m_raw)
    df_1h = trainer.feature_engineering(df_1h_raw)
    
    df_15m['symbol'] = s
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
    
    data_cache[s] = {"15m": df_15m, "1h": df_1h}

class DualTFWrapper:
    def __init__(self, dispatcher, df_1h):
        self.dispatcher = dispatcher
        self.df_1h = df_1h
    def get_signal(self, df_15m_slice, symbol="UNKNOWN"):
        ts = df_15m_slice['timestamp'].iloc[-1]
        h_slice = self.df_1h[self.df_1h['timestamp'] <= ts]
        return self.dispatcher.get_signal(df_15m_slice, symbol, df_1h=h_slice)

def objective(trial):
    z_score = trial.suggest_float('z_score', 0.4, 1.2)
    entropy = trial.suggest_float('entropy', 0.75, 0.9)
    rsi_slope = trial.suggest_int('rsi_slope', 1, 4)
    tp_mult = trial.suggest_float('tp_mult', 1.5, 3.5)

    # 修改 Dispatcher 以支援 tp_mult (透過閉包或繼承)
    class OptimizedDispatcher(GoldilocksDispatcher):
        def get_signal(self, df_15m, symbol="UNKNOWN", df_1h=None):
            sig, params = super().get_signal(df_15m, symbol, df_1h)
            if sig and 'tp_price' in params:
                # 重新計算基於 tp_mult 的止盈
                latest_15m = df_15m.iloc[-1]
                current_atr = latest_15m.get('atr', latest_15m['close'] * 0.01)
                if sig == 'LONG':
                    params['tp_price'] = latest_15m['close'] + (current_atr * tp_mult)
                else:
                    params['tp_price'] = latest_15m['close'] - (current_atr * tp_mult)
            return sig, params

    dispatcher = OptimizedDispatcher(
        z_score_threshold=z_score,
        entropy_threshold=entropy,
        rsi_slope_min=rsi_slope
    )
    
    total_n = 0
    total_pnl = 0
    total_pos_pnl = 0
    total_neg_pnl = 0
    
    for s in symbols:
        engine = BacktestEngine()
        wrapper = DualTFWrapper(dispatcher, data_cache[s]["1h"])
        results = engine.run(data_cache[s]["15m"], wrapper)
        trades = results.get('all_trades', [])
        
        total_n += len(trades)
        for t in trades:
            pnl = t['pnl']
            total_pnl += pnl
            if pnl > 0: total_pos_pnl += pnl
            else: total_neg_pnl += abs(pnl)

    pf = total_pos_pnl / total_neg_pnl if total_neg_pnl > 0 else (999 if total_pos_pnl > 0 else 0)
    
    if total_n < 15: return -10.0 + total_n
    if total_n > 80: return -5.0
    
    return pf * (total_n ** 0.5)

log("🚀 啟動 50 次貝氏演化...")
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=50)

log(f"🏆 最佳參數: {study.best_params}")
log(f"🏆 最佳得分: {study.best_value:.4f}")
