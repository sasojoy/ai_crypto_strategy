




import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from src.market import calculate_rsi, calculate_ema, calculate_atr, calculate_bollinger_bands, calculate_macd

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=60):
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

def run_backtest_v41(df, symbol, initial_balance=1000, mode='v41'):
    # Indicators
    df['rsi'] = calculate_rsi(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['ema200_15m'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    df['bb_upper'], df['bb_lower'], df['bb_mid'], _ = calculate_bollinger_bands(df, 20, 2)
    df['ema200_4h'] = calculate_ema(df, 200 * 16)
    df['ema200_1h'] = calculate_ema(df, 200 * 4)
    _, _, df['macd_hist'] = calculate_macd(df)
    
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    entry_price = 0
    balance = initial_balance
    sl_price = 0
    tp_price = 0
    highest_price = 0
    partial_tp_hit = False
    
    last_exit_time = None
    last_exit_reason = None
    last_entry_rsi = 0

    for i in range(10, len(df)):
        current_row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        if not in_position:
            # Entry Logic
            trend_4h_strong = current_row['close'] > current_row['ema200_4h']
            trend_1h_strong = current_row['close'] > current_row['ema200_1h']
            
            # MACD Divergence
            price_down = current_row['close'] < df['close'].iloc[i-5]
            macd_up = current_row['macd_hist'] > df['macd_hist'].iloc[i-5]
            macd_bullish_div = price_down and macd_up

            if mode == 'v41':
                extreme_mode = current_row['rsi'] < 30
                structural_mode = current_row['rsi'] < 38 and macd_bullish_div
                hybrid_trigger = extreme_mode or structural_mode
                
                if symbol in ['SOL/USDT', 'BTC/USDT', 'ETH/USDT']:
                    vol_buffer = 1.2
                    avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                    vol_exhaustion = current_row['volume'] < (avg_vol_5 * vol_buffer)
                else:
                    if current_row['rsi'] < 30:
                        vol_exhaustion = True
                    else:
                        avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                        vol_exhaustion = current_row['volume'] < (avg_vol_5 * 1.1)
                
                entry_allowed = trend_4h_strong and trend_1h_strong and hybrid_trigger
            else: # v40
                rsi_oversold = current_row['rsi'] < 35
                avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                vol_exhaustion = current_row['volume'] < (avg_vol_5 * 1.1)
                entry_allowed = trend_4h_strong and trend_1h_strong and macd_bullish_div and rsi_oversold
                
            price_at_bb_lower = current_row['low'] <= current_row['bb_lower']
            ema_golden_cross = current_row['ema20'] > current_row['ema50'] and prev_row['ema20'] <= prev_row['ema50']
            rsi_hook_up = current_row['rsi'] > prev_row['rsi']
            first_green = current_row['close'] > current_row['open']
            
            long_signal = entry_allowed and vol_exhaustion and (price_at_bb_lower or ema_golden_cross) and rsi_hook_up and first_green
            
            # Two-Stage SL Protection
            if long_signal and symbol not in ['SOL/USDT', 'BTC/USDT', 'ETH/USDT']:
                if last_exit_time and last_exit_reason in ['SL', 'SL_Trailing']:
                    if (current_row['timestamp'] - last_exit_time).total_seconds() < 1800:
                        if current_row['rsi'] >= last_entry_rsi:
                            long_signal = False

            if long_signal:
                in_position = True
                entry_price = current_row['close']
                entry_time = current_row['timestamp']
                highest_price = entry_price
                partial_tp_hit = False
                last_entry_rsi = current_row['rsi']
                
                # Sizing
                dist_ema200_pct = abs(entry_price - current_row['ema200_4h']) / current_row['ema200_4h'] * 100
                risk_pct = 0.03 if dist_ema200_pct < 1.5 else (0.015 if dist_ema200_pct > 5.0 else 0.025)
                
                sl_distance = 1.5 * current_row['atr']
                risk_amount = balance * risk_pct
                pos_size = risk_amount / sl_distance
                if pos_size * entry_price > balance * 0.95:
                    pos_size = (balance * 0.95) / entry_price
                
                sl_price = entry_price - sl_distance
                tp_price_atr = entry_price + (3.0 * current_row['atr'])
                tp_price = min(tp_price_atr, current_row['bb_upper'])
        
        else:
            current_price = current_row['close']
            highest_price = max(highest_price, current_price)
            profit_pct = (current_price - entry_price) / entry_price * 100
            
            exit_triggered = False
            exit_reason = ""
            
            highest_pnl = (highest_price - entry_price) / entry_price * 100
            
            if highest_pnl >= 2.0:
                chandelier_sl = highest_price * 0.995
                if current_price <= chandelier_sl:
                    exit_triggered = True
                    exit_reason = "Chandelier_Exit"
            
            if not exit_triggered and highest_pnl >= 3.0:
                retracement = (highest_pnl - profit_pct) / highest_pnl
                if retracement >= 0.20:
                    exit_triggered = True
                    exit_reason = "Profit Protection"
            
            if not exit_triggered and current_price <= sl_price:
                exit_triggered = True
                exit_reason = "SL"
            
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
                last_exit_time = current_row['timestamp']
                last_exit_reason = exit_reason

    if not trades:
        return {"net_profit_pct": 0, "win_rate": 0, "total_trades": 0}

    trades_df = pd.DataFrame(trades)
    net_profit_pct = (balance - initial_balance) / initial_balance * 100
    win_rate = (trades_df['pnl'] > 0).sum() / len(trades_df) * 100
    
    return {
        "net_profit_pct": net_profit_pct,
        "win_rate": win_rate,
        "total_trades": len(trades_df)
    }

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT', 'LINK/USDT', 'MATIC/USDT', 'FET/USDT', 'RNDR/USDT', 'ARB/USDT']
    results = {}
    
    for symbol in symbols:
        print(f"Fetching data for {symbol} (60 days)...")
        try:
            df = fetch_backtest_data(symbol, days=60)
            
            res_v40 = run_backtest_v41(df.copy(), symbol, mode='v40')
            res_v41 = run_backtest_v41(df.copy(), symbol, mode='v41')
            
            results[symbol] = {
                "v40": res_v40,
                "v41": res_v41
            }
        except Exception as e:
            print(f"Error backtesting {symbol}: {e}")
    
    print("\n" + "="*60)
    print("FINAL COMPARISON: Iteration 41 vs Iteration 40 (60 Days)")
    print("="*60)
    
    total_trades_v40 = 0
    total_trades_v41 = 0
    total_profit_v40 = 0
    total_profit_v41 = 0
    
    for symbol, data in results.items():
        v40 = data['v40']
        v41 = data['v41']
        print(f"\n[{symbol}]")
        print(f"  V40: Profit {v40['net_profit_pct']:.2f}%, WinRate {v40['win_rate']:.2f}%, Trades {v40['total_trades']}")
        print(f"  V41: Profit {v41['net_profit_pct']:.2f}%, WinRate {v41['win_rate']:.2f}%, Trades {v41['total_trades']}")
        
        total_trades_v40 += v40['total_trades']
        total_trades_v41 += v41['total_trades']
        total_profit_v40 += v40['net_profit_pct']
        total_profit_v41 += v41['net_profit_pct']

    print("\n" + "="*60)
    print(f"OVERALL SUMMARY (60 Days):")
    print(f"  V40: Total Profit {total_profit_v40:.2f}%, Total Trades {total_trades_v40}")
    print(f"  V41: Total Profit {total_profit_v41:.2f}%, Total Trades {total_trades_v41}")
    print("="*60)

    with open('data/backtest_results_v41.json', 'w') as f:
        json.dump(results, f, indent=4)




