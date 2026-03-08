


import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.evaluate import fetch_backtest_data, run_evaluation

def optimize_params(symbol='BTC/USDT'):
    print(f"🔄 Starting Walk-Forward Optimization for {symbol}...")
    
    # Fetch last 30 days of data
    df_15m = fetch_backtest_data(symbol, timeframe='15m', days=30)
    df_4h = fetch_backtest_data(symbol, timeframe='4h', days=30)
    
    if df_15m.empty or df_4h.empty:
        print("Error: Optimization failed due to missing data.")
        return

    best_score = -1
    best_params = {}

    # Search Space
    ema_f_options = [20, 50, 100]
    bb_std_options = [1.5, 2.0, 2.5]
    
    for ema_f in ema_f_options:
        for bb_std in bb_std_options:
            res = run_evaluation(
                df_15m, 
                ema_f=ema_f, 
                bb_std=bb_std,
                df_4h=df_4h
            )
            
            if res['score'] > best_score:
                best_score = res['score']
                best_params = {'ema_f': ema_f, 'bb_std': bb_std}

    if best_params:
        print(f"✅ Optimization Complete. Best Params: {best_params} (Score: {best_score:.2f})")
        
        # Update config/params.json
        params_path = 'config/params.json'
        with open(params_path, 'r') as f:
            current_params = json.load(f)
        
        current_params.update(best_params)
        current_params['last_optimized'] = datetime.now().isoformat()
        
        with open(params_path, 'w') as f:
            json.dump(current_params, f, indent=4)
        print(f"💾 Updated {params_path} with optimized parameters.")
    else:
        print("⚠️ No improvement found during optimization.")

if __name__ == "__main__":
    optimize_params()


