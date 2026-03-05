
import pandas as pd
import numpy as np
from src.evaluate import fetch_backtest_data, calculate_rsi, calculate_ema, calculate_atr, run_evaluation
from datetime import datetime

def grid_search(symbol='BTC/USDT'):
    print(f"🚀 Starting Grid Search for {symbol}...")
    df_all = fetch_backtest_data(symbol, days=60)
    if df_all.empty:
        print("No data found.")
        return
    
    # Split data for OOS verification within grid search if needed, 
    # but here we'll just use the first 30 days for "Training" the grid search.
    mid_point = len(df_all) // 2
    df_train = df_all.iloc[:mid_point].copy()
    
    # Parameter Ranges
    rsi_range = [25, 30, 35, 40]
    ema_fast_range = [20, 40, 60]
    ema_slow_range = [100, 150, 200]
    atr_sl_range = [1.5, 2.0, 2.5, 3.0]
    
    results = []
    
    total_combinations = len(rsi_range) * len(ema_fast_range) * len(ema_slow_range) * len(atr_sl_range)
    count = 0
    
    for rsi_th in rsi_range:
        for ema_f in ema_fast_range:
            for ema_s in ema_slow_range:
                for sl_mult in atr_sl_range:
                    count += 1
                    if count % 10 == 0:
                        print(f"Progress: {count}/{total_combinations}...")
                    
                    # Custom evaluation logic for grid search
                    res = evaluate_params(df_train.copy(), rsi_th, ema_f, ema_s, sl_mult)
                    if res:
                        results.append({
                            'rsi_th': rsi_th,
                            'ema_f': ema_f,
                            'ema_s': ema_s,
                            'sl_mult': sl_mult,
                            'score': res['score'],
                            'profit': res['profit'],
                            'wr': res['wr'],
                            'mdd': res['mdd']
                        })
    
    # Sort by score descending
    results_df = pd.DataFrame(results)
    top_3 = results_df.sort_values(by='score', ascending=False).head(3)
    
    print("\n--- Grid Search Top 3 Results ---")
    print(top_3)
    top_3.to_csv('data/grid_search_results.csv', index=False)
    return top_3

def evaluate_params(df, rsi_th, ema_f, ema_s, sl_mult, initial_balance=10000):
    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, ema_f)
    df['ema_s'] = calculate_ema(df, ema_s)
    df['atr'] = calculate_atr(df, 14)
    df['atr_ma24h'] = df['atr'].rolling(96).mean()
    df = df.dropna().reset_index(drop=True)
    
    balance = initial_balance
    trades = []
    in_position = False
    
    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]
        
        if not in_position:
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            if volatility_ok and \
               latest['close'] > latest['ema_f'] and \
               latest['ema_f'] > latest['ema_s'] and \
               prev['rsi'] < rsi_th and latest['rsi'] > rsi_th:
                in_position = True
                entry_price = latest['close']
                sl_price = entry_price - (sl_mult * latest['atr'])
                tp_price = entry_price + (sl_mult * 2 * latest['atr']) # 2:1 RR
                
                risk_per_share = entry_price - sl_price
                position_size = (balance * 0.02) / risk_per_share
                trades.append({'size': position_size, 'entry_price': entry_price, 'sl': sl_price, 'tp': tp_price})
        else:
            trade = trades[-1]
            if latest['low'] <= trade['sl']:
                balance += (trade['sl'] - trade['entry_price']) * trade['size']
                in_position = False
            elif latest['high'] >= trade['tp']:
                balance += (trade['tp'] - trade['entry_price']) * trade['size']
                in_position = False
                
    if not trades or in_position: # Simplified for grid search
        if in_position: trades.pop()
        if not trades: return None

    net_profit = balance - initial_balance
    win_rate = sum(1 for t in trades if (t.get('profit', 0) if 'profit' in t else 0) > 0) # This is simplified
    # Re-calculating properly
    profits = []
    temp_balance = initial_balance
    for t in trades:
        # We need to track profit in the loop above
        pass
    # Let's just use a more robust way
    return run_evaluation_with_params(df, rsi_th, ema_f, ema_s, sl_mult)

def run_evaluation_with_params(df, rsi_th, ema_f, ema_s, sl_mult, initial_balance=10000):
    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, ema_f)
    df['ema_s'] = calculate_ema(df, ema_s)
    df['atr'] = calculate_atr(df, 14)
    df['atr_ma24h'] = df['atr'].rolling(96).mean()
    df = df.dropna().reset_index(drop=True)
    
    balance = initial_balance
    trades = []
    in_position = False
    entry_price, sl_price, tp_price = 0, 0, 0
    
    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]
        if not in_position:
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            if volatility_ok and latest['close'] > latest['ema_f'] and latest['ema_f'] > latest['ema_s'] and \
               prev['rsi'] < rsi_th and latest['rsi'] > rsi_th:
                in_position = True
                entry_price = latest['close']
                sl_price = entry_price - (sl_mult * latest['atr'])
                tp_price = entry_price + (sl_mult * 2 * latest['atr'])
                risk_per_share = entry_price - sl_price
                position_size = (balance * 0.02) / risk_per_share
                trades.append({'profit': 0}) # placeholder
                trades[-1]['size'] = position_size
                trades[-1]['entry_price'] = entry_price
        else:
            if latest['low'] <= sl_price:
                profit = (sl_price - entry_price) * trades[-1]['size']
                balance += profit
                trades[-1]['profit'] = profit
                in_position = False
            elif latest['high'] >= tp_price:
                profit = (tp_price - entry_price) * trades[-1]['size']
                balance += profit
                trades[-1]['profit'] = profit
                in_position = False
    
    if not trades or in_position:
        if in_position: trades.pop()
        if not trades: return {'score': -9999, 'profit': 0, 'wr': 0, 'mdd': 1}

    total_trades = len(trades)
    win_rate = sum(1 for t in trades if t['profit'] > 0) / total_trades
    net_profit = balance - initial_balance
    
    # Max Drawdown
    cum_profits = pd.Series([t['profit'] for t in trades]).cumsum() + initial_balance
    peak = cum_profits.cummax()
    drawdown = (cum_profits - peak) / peak
    max_dd = abs(drawdown.min()) if not drawdown.empty else 0
    
    score = (net_profit * win_rate) / max_dd if max_dd > 0 else 0
    return {'score': score, 'profit': net_profit, 'wr': win_rate, 'mdd': max_dd}

if __name__ == "__main__":
    grid_search()
