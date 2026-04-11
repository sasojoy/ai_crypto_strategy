import pandas as pd
import numpy as np
import warnings
import sys
from strategy.main import GoldilocksDispatcher
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

# 妳辛苦得出的上帝參數
GOD_PARAMS = {
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
                params['tp_price'] = latest_15m['close'] + (current_atr * GOD_PARAMS['tp_mult'])
                params['be_trigger_price'] = latest_15m['close'] + (current_atr * GOD_PARAMS['be_trigger'])
            else:
                params['tp_price'] = latest_15m['close'] - (current_atr * GOD_PARAMS['tp_mult'])
                params['be_trigger_price'] = latest_15m['close'] - (current_atr * GOD_PARAMS['be_trigger'])
        return sig, params

class DualTFWrapper:
    def __init__(self, dispatcher, df_1h):
        self.dispatcher = dispatcher
        self.df_1h = df_1h
    def get_signal(self, df_15m_slice, symbol="UNKNOWN"):
        ts = df_15m_slice['timestamp'].iloc[-1]
        h_slice = self.df_1h[self.df_1h['timestamp'] <= ts]
        return self.dispatcher.get_signal(df_15m_slice, symbol, df_1h=h_slice)

symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT"]
fetcher = BinanceFetcher()
trainer = ModelTrainer()

dispatcher = OptimizedDispatcher(
    z_score_threshold=GOD_PARAMS['z_score'],
    entropy_threshold=GOD_PARAMS['entropy'],
    rsi_slope_min=GOD_PARAMS['rsi_slope']
)

all_trades = []

for s in symbols:
    # 測試過去 90~180 天的數據 (樣本外)
    # 抓取 180 天數據，取前半段
    limit_15m = 180 * 96 + 200
    limit_1h = 180 * 24 + 200
    
    df_15m_raw = fetcher.fetch_ohlcv(s, "15m", limit=limit_15m)
    df_1h_raw = fetcher.fetch_ohlcv(s, "1h", limit=limit_1h)
    
    if df_15m_raw.empty or df_1h_raw.empty: continue
    
    # 取前半段 (樣本外)
    df_15m_oos = df_15m_raw.iloc[:8640].copy()
    df_1h_oos = df_1h_raw.iloc[:2160].copy()
    
    df_15m = trainer.feature_engineering(df_15m_oos)
    df_1h = trainer.feature_engineering(df_1h_oos)
    
    df_15m['symbol'] = s
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
    
    engine = BacktestEngine()
    wrapper = DualTFWrapper(dispatcher, df_1h)
    results = engine.run(df_15m, wrapper)
    trades = results.get('all_trades', [])
    all_trades.extend(trades)
    
    if trades:
        tdf = pd.DataFrame(trades)
        pos_pnl = tdf[tdf['pnl'] > 0]['pnl'].sum()
        neg_pnl = abs(tdf[tdf['pnl'] <= 0]['pnl'].sum())
        pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
        
        tdf['cum_balance'] = tdf['pnl'].cumsum() + 10000
        max_dd = ((tdf['cum_balance'].cummax() - tdf['cum_balance']) / tdf['cum_balance'].cummax()).max()
        print(f"📊 Symbol: {s} | N: {len(trades)} | PF: {pf:.2f} | MaxDD: {max_dd:.2%}")
    else:
        print(f"📊 Symbol: {s} | N: 0 | PF: 0.00 | MaxDD: 0.00%")

# 輸出最終審計數據
if all_trades:
    df = pd.DataFrame(all_trades)
    n = len(df)
    wr = (df['pnl'] > 0).sum() / n * 100
    exp = df['pnl'].mean()
    df['cum_balance'] = df['pnl'].cumsum() + 10000
    dd = ((df['cum_balance'].cummax() - df['cum_balance']) / df['cum_balance'].cummax()).max() * 100
    pos_pnl = df[df['pnl'] > 0]['pnl'].sum()
    neg_pnl = abs(df[df['pnl'] <= 0]['pnl'].sum())
    pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
    exit_counts = df['exit_type'].value_counts()
    # 映射 engine.py 的 exit_type
    sl = exit_counts.get('STOP_LOSS', 0) + exit_counts.get('TRAILING_STOP', 0)
    tp = exit_counts.get('TAKE_PROFIT', 0)
    be = exit_counts.get('BREAKEVEN', 0)
    
    print(f"\n[FINAL_AUDIT_REPORT]")
    print(f"| 指標 | 數值 |")
    print(f"| :--- | :--- |")
    print(f"| 策略版本 | v400.0-GOLDILOCKS-OOS |")
    print(f"| 總交易數 (N) | {n} |")
    print(f"| 勝率 (WinRate) | {wr:.2f}% |")
    print(f"| 期望值 (Expectancy) | {exp:.2f}% |")
    print(f"| 最大回撤 (MaxDD) | {dd:.2f}% |")
    print(f"| 盈虧比 (PF) | {pf:.2f} |")
    print(f"| 結束類型 | sl:{sl}/tp:{tp}/be:{be} |")
    print(f"[END_OF_REPORT]")
