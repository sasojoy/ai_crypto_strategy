

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from src.market import calculate_rsi, calculate_ema, calculate_atr, calculate_bollinger_bands

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=30):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    while since < exchange.milliseconds():
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
        if not ohlcv:
            break
        since = ohlcv[-1][0] + 1
        all_ohlcv.extend(ohlcv)
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_backtest_v38(df, initial_balance=1000, mode='v38'):
    # Indicators
    df['rsi'] = calculate_rsi(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['ema200_15m'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    df['bb_upper'], df['bb_lower'], df['bb_mid'], _ = calculate_bollinger_bands(df, 20, 2)
    
    # Simulate 4H EMA200 (simplified for backtest)
    df['ema200_4h'] = calculate_ema(df, 200 * 16) # 16 * 15m = 4h
    
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    entry_price = 0
    balance = initial_balance
    sl_price = 0
    tp_price = 0
    highest_price = 0
    partial_tp_hit = False
    atr_spike_count = 0
    
    atr_avg_100 = df['atr'].rolling(window=100).mean()

    for i in range(5, len(df)):
        current_row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        if not in_position:
            # Entry Logic
            trend_4h_strong = current_row['close'] > current_row['ema200_4h']
            
            if mode == 'v38':
                rsi_oversold = current_row['rsi'] < 35 # Tightened
                avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                vol_exhaustion = current_row['volume'] < avg_vol_5
            else: # v37
                rsi_oversold = current_row['rsi'] < 42
                vol_exhaustion = True
                
            price_at_bb_lower = current_row['low'] <= current_row['bb_lower']
            ema_golden_cross = current_row['ema20'] > current_row['ema50'] and prev_row['ema20'] <= prev_row['ema50']
            rsi_hook_up = current_row['rsi'] > prev_row['rsi']
            first_green = current_row['close'] > current_row['open']
            
            if trend_4h_strong and rsi_oversold and vol_exhaustion and (price_at_bb_lower or ema_golden_cross) and rsi_hook_up and first_green:
                in_position = True
                entry_price = current_row['close']
                entry_time = current_row['timestamp']
                highest_price = entry_price
                partial_tp_hit = False
                
                # Sizing Logic
                dist_ema200_pct = abs(entry_price - current_row['ema200_4h']) / current_row['ema200_4h'] * 100
                if dist_ema200_pct < 1.5:
                    risk_pct = 0.03
                elif dist_ema200_pct > 5.0:
                    risk_pct = 0.015
                else:
                    risk_pct = 0.025
                
                # ATR Spike Guard
                spike_factor = 1.2 if mode == 'v38' else 1.5
                if current_row['atr'] > (atr_avg_100.iloc[i] * spike_factor):
                    risk_pct /= 2
                    atr_spike_count += 1
                
                sl_mult = 1.5 if mode == 'v38' else 2.0
                sl_distance = sl_mult * current_row['atr']
                risk_amount = balance * risk_pct
                pos_size = risk_amount / sl_distance
                
                # No-leverage cap
                if pos_size * entry_price > balance * 0.95:
                    pos_size = (balance * 0.95) / entry_price
                
                sl_price = entry_price - sl_distance
                
                if mode == 'v38':
                    tp_price_atr = entry_price + (3.0 * current_row['atr'])
                    tp_price = min(tp_price_atr, current_row['bb_upper'])
                else:
                    tp_price = current_row['bb_upper']
        
        else:
            current_price = current_row['close']
            highest_price = max(highest_price, current_price)
            profit_pct = (current_price - entry_price) / entry_price * 100
            
            # Exit Logic
            exit_triggered = False
            exit_reason = ""
            
            # 1. Profit Protection
            highest_pnl = (highest_price - entry_price) / entry_price * 100
            if highest_pnl >= 3.0:
                retracement = (highest_pnl - profit_pct) / highest_pnl
                if retracement >= 0.20:
                    exit_triggered = True
                    exit_reason = "Profit Protection"
            
            # 2. SL
            if not exit_triggered and current_price <= sl_price:
                exit_triggered = True
                exit_reason = "SL"
            
            # 3. Partial TP & Trailing Stop
            if not exit_triggered and current_price >= tp_price and not partial_tp_hit:
                sl_price = max(sl_price, entry_price)
                partial_tp_hit = True
            
            if partial_tp_hit:
                trailing_sl = highest_price * 0.985
                sl_price = max(sl_price, trailing_sl)
            
            if exit_triggered:
                pnl_amount = (current_price - entry_price) * pos_size
                balance += pnl_amount
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_row['timestamp'],
                    'profit_pct': profit_pct,
                    'pnl': pnl_amount,
                    'balance': balance,
                    'reason': exit_reason
                })
                in_position = False

    if not trades:
        return {"net_profit_pct": 0, "win_rate": 0, "max_drawdown": 0, "total_trades": 0, "atr_spikes": atr_spike_count}

    trades_df = pd.DataFrame(trades)
    net_profit_pct = (balance - initial_balance) / initial_balance * 100
    win_rate = (trades_df['pnl'] > 0).sum() / len(trades_df) * 100
    
    peak = trades_df['balance'].cummax()
    drawdown = (trades_df['balance'] - peak) / peak
    max_drawdown = drawdown.min() * 100
    
    return {
        "net_profit_pct": net_profit_pct,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
        "total_trades": len(trades_df),
        "atr_spikes": atr_spike_count
    }

if __name__ == "__main__":
    symbols = ['SOL/USDT', 'NEAR/USDT', 'BTC/USDT']
    results = {}
    
    for symbol in symbols:
        print(f"Fetching data for {symbol}...")
        df = fetch_backtest_data(symbol, days=30)
        
        res_v37 = run_backtest_v38(df.copy(), mode='v37')
        res_v38 = run_backtest_v38(df.copy(), mode='v38')
        
        results[symbol] = {
            "v37": res_v37,
            "v38": res_v38
        }
    
    print("\n" + "="*50)
    print("BACKTEST RESULTS: Iteration 38 vs Iteration 37")
    print("="*50)
    
    for symbol, data in results.items():
        v37 = data['v37']
        v38 = data['v38']
        print(f"\n[{symbol}]")
        print(f"  V37: Profit {v37['net_profit_pct']:.2f}%, WinRate {v37['win_rate']:.2f}%, MDD {v37['max_drawdown']:.2f}%, Trades {v37['total_trades']}")
        print(f"  V38: Profit {v38['net_profit_pct']:.2f}%, WinRate {v38['win_rate']:.2f}%, MDD {v38['max_drawdown']:.2f}%, Trades {v38['total_trades']}, ATR Spikes {v38['atr_spikes']}")

    with open('data/backtest_results_v38.json', 'w') as f:
        json.dump(results, f, indent=4)

