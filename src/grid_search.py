
import pandas as pd
import numpy as np
from src.evaluate import fetch_backtest_data, calculate_rsi, calculate_ema, calculate_atr, run_evaluation
from datetime import datetime

def grid_search(symbol='BTC/USDT'):
    print(f"🚀 Starting Grid Search for {symbol}...")
    df_all = fetch_backtest_data(symbol, days=90) # Increased to 90 days
    if df_all.empty:
        print("No data found.")
        return
    
    mid_point = len(df_all) // 2
    df_train = df_all.iloc[:mid_point].copy()
    
    # Parameter Ranges
    rsi_range = [25, 30, 35]
    ema_fast_range = [20, 40, 60]
    ema_slow_range = [100, 150, 200]
    atr_sl_range = [1.5, 2.0, 2.5, 3.0]
    macd_confirm_range = [True, False]
    
    results = []
    
    total_combinations = len(rsi_range) * len(ema_fast_range) * len(ema_slow_range) * len(atr_sl_range) * len(macd_confirm_range)
    count = 0
    
    for rsi_th in rsi_range:
        for ema_f in ema_fast_range:
            for ema_s in ema_slow_range:
                for sl_mult in atr_sl_range:
                    for macd_c in macd_confirm_range:
                        count += 1
                        if count % 20 == 0:
                            print(f"Progress: {count}/{total_combinations}...")
                        
                        score, profit, wr, mdd, trades = run_evaluation(df_train.copy(), rsi_th=rsi_th, ema_f=ema_f, ema_s=ema_s, sl_mult=sl_mult, macd_confirm=macd_c)
                        results.append({
                            'rsi_th': rsi_th,
                            'ema_f': ema_f,
                            'ema_s': ema_s,
                            'sl_mult': sl_mult,
                            'macd_confirm': macd_c,
                            'score': score,
                            'profit': profit,
                            'wr': wr,
                            'mdd': mdd
                        })
    
    # Sort by score descending
    results_df = pd.DataFrame(results)
    top_3 = results_df.sort_values(by='score', ascending=False).head(3)
    
    print("\n--- Grid Search Top 3 Results ---")
    print(top_3)
    top_3.to_csv('data/grid_search_results.csv', index=False)
    return top_3

if __name__ == "__main__":
    grid_search()
