import optuna
import pandas as pd
import numpy as np
import sys
import os
import warnings
from strategy.main import GoldilocksDispatcher
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

def log(msg):
    print(f"HB: {msg}") # Heartbeat 標記
    sys.stdout.flush()

# 數據預抓取
log("📡 抓取數據中...")
fetcher = BinanceFetcher()
trainer = ModelTrainer()

symbol = "BTCUSDT"
days = 90
limit_15m = days * 96 + 200
limit_1h = days * 24 + 200

df_15m_raw = fetcher.fetch_ohlcv(symbol, "15m", limit=limit_15m)
df_1h_raw = fetcher.fetch_ohlcv(symbol, "1h", limit=limit_1h)

df_15m = trainer.feature_engineering(df_15m_raw)
df_1h = trainer.feature_engineering(df_1h_raw)

df_15m['symbol'] = symbol
df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])

class DualTFWrapper:
    def __init__(self, dispatcher, df_1h):
        self.dispatcher = dispatcher
        self.df_1h = df_1h
    def get_signal(self, df_15m_slice, symbol="UNKNOWN"):
        ts = df_15m_slice['timestamp'].iloc[-1]
        h_slice = self.df_1h[self.df_1h['timestamp'] <= ts]
        return self.dispatcher.get_signal(df_15m_slice, symbol, df_1h=h_slice)

def objective(trial):
    z_score = trial.suggest_float('z_score', 0.5, 1.2)
    entropy = trial.suggest_float('entropy', 0.7, 0.9)
    rsi_slope = trial.suggest_int('rsi_slope', 1, 4)
    
    dispatcher = GoldilocksDispatcher(
        z_score_threshold=z_score,
        entropy_threshold=entropy,
        rsi_slope_min=rsi_slope,
        be_trigger=1.5
    )
    
    engine = BacktestEngine()
    wrapper = DualTFWrapper(dispatcher, df_1h)
    results = engine.run(df_15m, wrapper)
    trades = results.get('all_trades', [])
    
    n = len(trades)
    if n > 0:
        trade_df = pd.DataFrame(trades)
        pos_pnl = trade_df[trade_df['pnl'] > 0]['pnl'].sum()
        neg_pnl = abs(trade_df[trade_df['pnl'] <= 0]['pnl'].sum())
        pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
        
        trade_df['cum_balance'] = trade_df['pnl'].cumsum() + 10000
        max_dd = ((trade_df['cum_balance'].cummax() - trade_df['cum_balance']) / trade_df['cum_balance'].cummax()).max()
    else:
        pf = 0
        max_dd = 0

    report = {'N': n, 'PF': pf, 'MaxDD': max_dd}
    
    # 將結果寫入 CSV，防止 Agent 崩潰丟失數據
    params = {'z_score': z_score, 'entropy': entropy, 'rsi_slope': rsi_slope}
    res = {**params, **report}
    pd.DataFrame([res]).to_csv('optuna_progress.csv', mode='a', header=not os.path.exists('optuna_progress.csv'), index=False)
    
    log(f"Trial {trial.number} Done | N: {n} | PF: {pf:.2f}")
    
    if n < 10: return -10.0
    return pf * (1 - max_dd)

log("🚀 啟動 30 次極速演化...")
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=30)

log("🏆 最佳參數已產生！")
print(study.best_params)
