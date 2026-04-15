import pandas as pd
import numpy as np
import sys
import os

# 物理清理舊證
if os.path.exists('backtest_equity_curve.csv'):
    os.remove('backtest_equity_curve.csv')

sys.path.append('/workspace/ai_crypto_strategy')
from src.features import calculate_features
from src.ml_model import CryptoMLModel
from src.indicators import calculate_ema, calculate_atr

# 嚴格參數：150天訓練，15天測試，15天步長 (絕無重疊)
TRAIN_DAYS = 150
TEST_DAYS = 15
STEP_DAYS = 15
FEE = 0.0004
SLIPPAGE = 0.0005

def run_wfo():
    if not os.path.exists('data/btc_wfo_data.csv'):
        print("❌ 錯誤：找不到數據檔案")
        return

    df = pd.read_csv('data/btc_wfo_data.csv', parse_dates=['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    print(f"🔍 數據載入完成：{df['timestamp'].min()} 至 {df['timestamp'].max()} (共 {len(df)} 筆)")
    
    df['ema200_1h'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    X_all = calculate_features(df, df.copy())
    df = df.set_index('timestamp').loc[X_all.index]
    
    current_train_start = df.index[0]
    end_date = df.index[-1]
    
    ml_model = CryptoMLModel()
    ml_model.load()

    all_trades_log = []
    cumulative_ret = 1.0
    fold_count = 1
    
    print("\n" + "="*60)
    print("🚀 [V1.3.5_WFO_DYNAMIC_SIM] 物理清場審計開始")
    print("="*60)
    
    while True:
        train_end = current_train_start + pd.Timedelta(days=TRAIN_DAYS)
        test_end = train_end + pd.Timedelta(days=TEST_DAYS)
        
        if test_end > end_date:
            break
            
        test_idx = df[(df.index >= train_end) & (df.index < test_end)].index
        
        fold_pnl = 0.0
        fold_trades = 0
        
        if len(test_idx) > 0:
            X_test = X_all.loc[test_idx]
            probs = ml_model.predict_proba(X_test)[:, 1]
            df_oos = df.loc[test_idx].copy()
            df_oos['ml_score'] = probs
            
            current_fold_ret = 1.0
            for i in range(1, len(df_oos)):
                prev = df_oos.iloc[i-1]
                if prev['ml_score'] >= 0.82 and prev['close'] > prev['ema200_1h']:
                    entry_price = prev['close'] * (1 + SLIPPAGE) 
                    exit_idx = min(i + 5, len(df_oos) - 1)
                    exit_price = df_oos.iloc[exit_idx]['close'] * (1 - SLIPPAGE)
                    pnl = (exit_price / entry_price) - 1 - FEE
                    
                    cumulative_ret *= (1 + pnl)
                    current_fold_ret *= (1 + pnl)
                    fold_trades += 1
                    all_trades_log.append({
                        'timestamp': df_oos.index[i],
                        'pnl': pnl,
                        'cumulative_return': cumulative_ret - 1
                    })
            fold_pnl = current_fold_ret - 1

        print(f"Fold {fold_count:02d} | 測試區間: {train_end.date()} ~ {test_end.date()} | 交易數: {fold_trades} | 區間損益: {fold_pnl:+.2%}")
        
        current_train_start += pd.Timedelta(days=STEP_DAYS)
        fold_count += 1

    if all_trades_log:
        equity_df = pd.DataFrame(all_trades_log)
        equity_df.to_csv('backtest_equity_curve.csv', index=False)
        print("\n" + "="*60)
        print(f"✅ 審計完成。最終累積投報率: {cumulative_ret-1:.2%}")
        print(f"✅ 總交易次數: {len(equity_df)}")
    else:
        print("\n❌ 審計結束：未產生任何交易。")

if __name__ == "__main__":
    run_wfo()
