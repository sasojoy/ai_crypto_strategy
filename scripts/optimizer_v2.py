import optuna
import pandas as pd
import numpy as np
import warnings
from strategy.main import GoldilocksDispatcher
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

# --- 第一步：數據預抓取與預處理 (僅執行一次) ---
print("📡 正在預抓取並處理 90 天數據，請稍候...")
fetcher = BinanceFetcher()
trainer = ModelTrainer()
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
days = 90
limit_15m = days * 96 + 200
limit_1h = days * 24 + 200

data_cache = {}

for symbol in symbols:
    print(f"處理 {symbol}...")
    df_15m_raw = fetcher.fetch_ohlcv(symbol, "15m", limit=limit_15m)
    df_1h_raw = fetcher.fetch_ohlcv(symbol, "1h", limit=limit_1h)
    
    if df_15m_raw.empty or df_1h_raw.empty:
        continue
        
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
    z_score = trial.suggest_float('z_score', 0.8, 1.8)
    entropy = trial.suggest_float('entropy', 0.6, 0.9)
    rsi_slope = trial.suggest_int('rsi_slope', 2, 8)
    be_trigger = trial.suggest_float('be_trigger', 1.0, 3.0)
    
    dispatcher = GoldilocksDispatcher(
        z_score_threshold=z_score,
        entropy_threshold=entropy,
        rsi_slope_min=rsi_slope,
        be_trigger=be_trigger
    )
    
    all_trades = []
    for symbol, data in data_cache.items():
        engine = BacktestEngine()
        wrapper = DualTFWrapper(dispatcher, data['df_1h'])
        results = engine.run(data['df_15m'], wrapper)
        all_trades.extend(results.get('all_trades', []))
        
    if not all_trades:
        return -1.0
        
    trade_df = pd.DataFrame(all_trades)
    n = len(trade_df)
    
    trade_df['cum_balance'] = trade_df['pnl'].cumsum() + 10000
    max_drawdown = ((trade_df['cum_balance'].cummax() - trade_df['cum_balance']) / trade_df['cum_balance'].cummax()).max()
    
    pos_pnl = trade_df[trade_df['pnl'] > 0]['pnl'].sum()
    neg_pnl = abs(trade_df[trade_df['pnl'] <= 0]['pnl'].sum())
    pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
    
    if n < 15 or max_drawdown > 0.25:
        return -1.0
        
    return pf * (1 - max_drawdown) * np.log10(n)

# 啟動優化
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=50)

print("\n🏆 最佳參數組合:", study.best_params)
print("最佳得分:", study.best_value)
