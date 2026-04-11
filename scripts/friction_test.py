import pandas as pd
import numpy as np
import warnings
import sys
from strategy.main import GoldilocksDispatcher
from backtest.engine import BacktestEngine
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer

warnings.filterwarnings('ignore')

# 穩定參數
STABLE_PARAMS = {
    'z_score': 0.48,
    'entropy': 0.90,
    'rsi_slope': 3,
    'tp_mult': 3.26,
    'be_trigger': 1.2
}

# 極端摩擦環境
FRICTION_CONFIG = {
    'commission': 0.0004, # 萬分之四
    'slippage': 0.001,    # 千分之一
}
TOTAL_FRICTION = FRICTION_CONFIG['commission'] + FRICTION_CONFIG['slippage']

class FrictionEngine(BacktestEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.friction = TOTAL_FRICTION # 強制覆蓋為極端摩擦

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

symbols = ["BTCUSDT", "SOLUSDT"]
fetcher = BinanceFetcher()
trainer = ModelTrainer()

dispatcher = OptimizedDispatcher(
    z_score_threshold=STABLE_PARAMS['z_score'],
    entropy_threshold=STABLE_PARAMS['entropy'],
    rsi_slope_min=STABLE_PARAMS['rsi_slope']
)

print(f"⚖️ 啟動 v500.0 摩擦係數測試 (總摩擦: {TOTAL_FRICTION:.2%})...")

all_trades = []
for s in symbols:
    df_15m_raw = fetcher.fetch_ohlcv(s, "15m", limit=5000)
    df_1h_raw = fetcher.fetch_ohlcv(s, "1h", limit=1500)
    
    df_15m = trainer.feature_engineering(df_15m_raw)
    df_1h = trainer.feature_engineering(df_1h_raw)
    
    df_15m['symbol'] = s
    df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
    df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
    
    engine = FrictionEngine()
    wrapper = DualTFWrapper(dispatcher, df_1h)
    results = engine.run(df_15m, wrapper)
    trades = results.get('all_trades', [])
    all_trades.extend(trades)

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
    sl = exit_counts.get('STOP_LOSS', 0) + exit_counts.get('TRAILING_STOP', 0)
    tp = exit_counts.get('TAKE_PROFIT', 0)
    be = exit_counts.get('BREAKEVEN', 0)
    
    print(f"\n[FINAL_AUDIT_REPORT]")
    print(f"| 指標 | 數值 |")
    print(f"| :--- | :--- |")
    print(f"| 策略版本 | v500.0-FRICTION-TEST |")
    print(f"| 總交易數 (N) | {n} |")
    print(f"| 勝率 (WinRate) | {wr:.2f}% |")
    print(f"| 期望值 (Expectancy) | {exp:.2f}% |")
    print(f"| 最大回撤 (MaxDD) | {dd:.2f}% |")
    print(f"| 盈虧比 (PF) | {pf:.2f} |")
    print(f"| 結束類型 | sl:{sl}/tp:{tp}/be:{be} |")
    print(f"[END_OF_REPORT]")
