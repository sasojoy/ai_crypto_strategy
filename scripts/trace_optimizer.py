import optuna
import pandas as pd
import numpy as np
import warnings
import sys
from strategy.main import GoldilocksDispatcher
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

def log(msg):
    print(f"🔍 [DEBUG] {msg}")
    sys.stdout.flush()

log("📡 正在預抓取並處理 30 天數據 (縮短時間以利診斷)...")
fetcher = BinanceFetcher()
trainer = ModelTrainer()
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
days = 30
limit_15m = days * 96 + 200
limit_1h = days * 24 + 200

data_cache = {}
for symbol in symbols:
    log(f"處理 {symbol}...")
    df_15m_raw = fetcher.fetch_ohlcv(symbol, "15m", limit=limit_15m)
    df_1h_raw = fetcher.fetch_ohlcv(symbol, "1h", limit=limit_1h)
    if df_15m_raw.empty or df_1h_raw.empty: continue
    df_15m = trainer.feature_engineering(df_15m_raw)
    df_1h = trainer.feature_engineering(df_1h_raw)
    df_15m['symbol'] = symbol
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
    data_cache[symbol] = {'df_15m': df_15m, 'df_1h': df_1h}

class DualTFWrapper:
    def __init__(self, dispatcher, df_1h):
        self.dispatcher = dispatcher
        self.df_1h = df_1h
    def get_signal(self, df_15m_slice, symbol="UNKNOWN"):
        ts = df_15m_slice['timestamp'].iloc[-1]
        h_slice = self.df_1h[self.df_1h['timestamp'] <= ts]
        return self.dispatcher.get_signal(df_15m_slice, symbol, df_1h=h_slice)

def objective(trial):
    # 大幅放寬門檻以尋找進場點
    z_score = trial.suggest_float('z_score', 0.5, 1.5)
    entropy = trial.suggest_float('entropy', 0.7, 0.95)
    rsi_slope = trial.suggest_int('rsi_slope', 1, 5)
    
    dispatcher = GoldilocksDispatcher(
        z_score_threshold=z_score,
        entropy_threshold=entropy,
        rsi_slope_min=rsi_slope,
        be_trigger=1.5
    )
    
    all_trades = []
    for symbol, data in data_cache.items():
        engine = BacktestEngine()
        wrapper = DualTFWrapper(dispatcher, data['df_1h'])
        results = engine.run(data['df_15m'], wrapper)
        all_trades.extend(results.get('all_trades', []))
        
    n = len(all_trades)
    if n == 0:
        return -10.0
        
    trade_df = pd.DataFrame(all_trades)
    trade_df['cum_balance'] = trade_df['pnl'].cumsum() + 10000
    max_drawdown = ((trade_df['cum_balance'].cummax() - trade_df['cum_balance']) / trade_df['cum_balance'].cummax()).max()
    
    pos_pnl = trade_df[trade_df['pnl'] > 0]['pnl'].sum()
    neg_pnl = abs(trade_df[trade_df['pnl'] <= 0]['pnl'].sum())
    pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
    
    # 只要有單，就根據 PF 和 N 給分
    score = pf * np.log10(n + 1) / (1 + max_drawdown)
    return score

log("🚀 開始優化...")
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=30)

log("✅ 優化完成！")
print(f"🏆 最佳參數: {study.best_params}")
print(f"🏆 最佳得分: {study.best_value}")
