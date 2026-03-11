
import pandas as pd
import numpy as np
from src.backtest_v48 import fetch_backtest_data
from src.indicators import calculate_rsi, calculate_macd, calculate_ema, calculate_atr, calculate_bollinger_bands, calculate_squeeze_index, calculate_macd_divergence, calculate_adx
from datetime import datetime

def run_backtest_v53(df, btc_df, rsi_trend, rsi_bottom):
    df = df.copy()
    df['rsi'] = calculate_rsi(df)
    df['ema200'] = calculate_ema(df, 200)
    df['ema10'] = calculate_ema(df, 10)
    df['atr'] = calculate_atr(df)
    df['adx'] = calculate_adx(df)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['bb_upper'], df['bb_lower'], _, _ = calculate_bollinger_bands(df)
    df['squeeze_index'] = calculate_squeeze_index(df)
    df['macd_div'] = calculate_macd_divergence(df)
    
    # 24h Change for Relative Strength
    df['change_24h'] = df['close'].pct_change(periods=24)
    btc_df['btc_change_24h'] = btc_df['close'].pct_change(periods=24)
    df = df.join(btc_df[['btc_change_24h']], how='left')
    
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    partial_tp_done = False
    
    for i in range(24, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        if not in_position:
            # Relative Strength Filter
            relative_strength_ok = current['change_24h'] > current['btc_change_24h']
            
            # Dual-Mode Entry
            trend_entry = (current['close'] > current['ema200']) and (current['rsi'] < rsi_trend) and (current['macd_hist'] > prev['macd_hist']) and (current['volume'] > df['volume'].iloc[i-5:i].mean()) and (current['adx'] > 20) and relative_strength_ok
            bottom_entry = (current['close'] <= current['ema200']) and (current['rsi'] < rsi_bottom) and current['macd_div'] and (current['rsi'] > prev['rsi'])
            squeeze_breakout = (current['squeeze_index'] < 0.3) and (current['close'] > current['bb_upper']) and (current['adx'] > 20)
            
            if trend_entry or bottom_entry or squeeze_breakout:
                in_position = True
                partial_tp_done = False
                entry_price = current['close']
                sl_price = entry_price - (1.5 * current['atr'])
                tp_1_2_price = entry_price + (1.5 * current['atr'] * 1.2)
                trades.append({'entry_price': entry_price, 'sl_price': sl_price, 'tp_1_2_price': tp_1_2_price, 'type': 'LONG', 'pnl': 0})
        else:
            trade = trades[-1]
            # 1. Partial TP at 1.2 RR
            if not partial_tp_done:
                if current['high'] >= trade['tp_1_2_price']:
                    # 50% TP
                    trade['pnl'] += 0.5 * (trade['tp_1_2_price'] - trade['entry_price']) / trade['entry_price'] - 0.001 # Half fees
                    partial_tp_done = True
                elif current['low'] <= trade['sl_price']:
                    trade['exit_price'] = trade['sl_price']
                    trade['pnl'] = (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] - 0.002
                    in_position = False
            else:
                # 2. EMA 10 Trailing Stop for remaining 50%
                if current['low'] < current['ema10']:
                    trade['exit_price'] = current['ema10']
                    trade['pnl'] += 0.5 * (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] - 0.001
                    in_position = False
                
    return trades

def run_iteration_53_backtest():
    symbols = ['ETH/USDT', 'SOL/USDT', 'BTC/USDT']
    rsi_t, rsi_b = 45, 30
    
    print(f"🚀 Running Iteration 53 Backtest (RSI_T: {rsi_t}, RSI_B: {rsi_b})...")
    
    btc_data = fetch_backtest_data('BTC/USDT', days=60)
    total_trades = 0
    total_wins = 0
    total_pnl = 0
    
    for symbol in symbols:
        data = fetch_backtest_data(symbol, days=60)
        trades = run_backtest_v53(data, btc_data.copy(), rsi_t, rsi_b)
        
        s_trades = len(trades)
        s_wins = len([t for t in trades if t.get('pnl', 0) > 0])
        s_pnl = sum([t.get('pnl', 0) for t in trades])
        
        total_trades += s_trades
        total_wins += s_wins
        total_pnl += s_pnl
        
        print(f"{symbol:<10} Trades: {s_trades:<4} WinRate: {s_wins/s_trades*100:>6.2f}% PnL: {s_pnl*100:>7.2f}%")
    
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    avg_pnl = (total_pnl / len(symbols) * 100)
    
    print(f"\n📊 --- Iteration 53 Summary ---")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate:     {win_rate:.2f}%")
    print(f"Average PnL:  {avg_pnl:.2f}%")

if __name__ == "__main__":
    run_iteration_53_backtest()
