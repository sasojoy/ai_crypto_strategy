import pandas as pd
import numpy as np
from strategy.main import StrategyMain, GoldilocksDispatcher

# 使用優化後的最佳參數
dispatcher = GoldilocksDispatcher(
    z_score_threshold=0.74,
    entropy_threshold=0.87,
    rsi_slope_min=4,
    be_trigger=1.5
)

main = StrategyMain()
trades = main.run_backtest(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'], 90, dispatcher=dispatcher)

if not trades:
    print("No trades found.")
    exit()

df = pd.DataFrame(trades)
n = len(df)
win_rate = (df['pnl'] > 0).sum() / n * 100
avg_pnl = df['pnl'].mean()
# 期望值 (Expectancy) = (勝率 * 平均獲利) + (敗率 * 平均虧損) -> 簡化為平均每筆 PnL %
expectancy = avg_pnl

# MaxDD
df['cum_balance'] = df['pnl'].cumsum() + 10000
max_dd = ((df['cum_balance'].cummax() - df['cum_balance']) / df['cum_balance'].cummax()).max() * 100

# PF
pos_pnl = df[df['pnl'] > 0]['pnl'].sum()
neg_pnl = abs(df[df['pnl'] <= 0]['pnl'].sum())
pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999

# Exit Types
exit_counts = df['exit_type'].value_counts()
exit_dist = "/".join([f"{t}:{exit_counts.get(t, 0)}" for t in ['sl', 'tp', 'be']])

print(f"VERSION: v250.0-GOLDILOCKS")
print(f"N: {n}")
print(f"WR: {win_rate:.2f}")
print(f"EXP: {expectancy:.2f}")
print(f"DD: {max_dd:.2f}")
print(f"PF: {pf:.2f}")
print(f"EXIT: {exit_dist}")
