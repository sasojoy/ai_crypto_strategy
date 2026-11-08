import optuna
import pandas as pd
import numpy as np
import warnings
from strategy.main import StrategyMain, GoldilocksDispatcher

warnings.filterwarnings('ignore')

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
    
    main = StrategyMain()
    trades = main.run_backtest(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'], 90, dispatcher=dispatcher)
    
    if not trades:
        return -1.0
        
    trade_df = pd.DataFrame(trades)
    n = len(trade_df)
    
    trade_df['cum_balance'] = trade_df['pnl'].cumsum() + 10000
    max_drawdown = ((trade_df['cum_balance'].cummax() - trade_df['cum_balance']) / trade_df['cum_balance'].cummax()).max()
    
    pos_pnl = trade_df[trade_df['pnl'] > 0]['pnl'].sum()
    neg_pnl = abs(trade_df[trade_df['pnl'] <= 0]['pnl'].sum())
    pf = pos_pnl / neg_pnl if neg_pnl > 0 else 999
    
    if n < 10 or max_drawdown > 0.30:
        return -1.0
        
    return pf * (1 - max_drawdown) * np.log10(n)

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=50)

print("\n🏆 最佳參數組合:", study.best_params)
print("最佳得分:", study.best_value)
