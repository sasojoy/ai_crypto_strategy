
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# Import logic from market.py
from src.market import calculate_rsi, calculate_ema, calculate_atr

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=30):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv:
                break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_evaluation(df, initial_balance=10000):
    # Indicators
    df['rsi'] = calculate_rsi(df)
    df['ema200'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    
    df = df.dropna().reset_index(drop=True)
    
    balance = initial_balance
    trades = []
    in_position = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    
    # Strategy Parameters (Iteration 8 Proposal)
    # RSI Hook: Prev < 30, Current > 30
    # Filter: Price > EMA 50 AND EMA 50 > EMA 200
    # SL: 2 * ATR, TP: 4 * ATR (2:1 RR)
    
    df['ema50'] = calculate_ema(df, 50)
    
    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]
        
        if not in_position:
            # Entry Logic
            if latest['close'] > latest['ema50'] and \
               latest['ema50'] > latest['ema200'] and \
               prev['rsi'] < 30 and latest['rsi'] > 30:
                in_position = True
                entry_price = latest['close']
                sl_price = entry_price - (2 * latest['atr'])
                tp_price = entry_price + (4 * latest['atr'])
                
                # Risk Check: 2% Max Risk per trade
                risk_per_share = entry_price - sl_price
                position_size = (balance * 0.02) / risk_per_share
                trades.append({'entry_time': latest['timestamp'], 'entry_price': entry_price, 'size': position_size})
        
        else:
            # Exit Logic
            if latest['low'] <= sl_price:
                exit_price = sl_price
                profit = (exit_price - entry_price) * trades[-1]['size']
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'SL'})
                in_position = False
            elif latest['high'] >= tp_price:
                exit_price = tp_price
                profit = (exit_price - entry_price) * trades[-1]['size']
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'TP'})
                in_position = False

    if not trades or 'exit_price' not in trades[-1]:
        if trades and 'exit_price' not in trades[-1]:
            trades.pop()
        if not trades:
            return 0, 0, 0, 0, 0

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df['profit'] > 0).sum() / total_trades
    net_profit = balance - initial_balance
    
    # Max Drawdown
    trades_df['cum_profit'] = trades_df['profit'].cumsum() + initial_balance
    peak = trades_df['cum_profit'].cummax()
    drawdown = (trades_df['cum_profit'] - peak) / peak
    max_dd = abs(drawdown.min())
    
    # Score Calculation: (Net Profit * Win Rate) / Max Drawdown
    # Avoid division by zero
    score = (net_profit * win_rate) / max_dd if max_dd != 0 else 0
    
    return score, net_profit, win_rate, max_dd, total_trades

if __name__ == "__main__":
    symbol = 'BTC/USDT'
    print(f"Evaluating {symbol} for the last 30 days...")
    df = fetch_backtest_data(symbol)
    if not df.empty:
        score, profit, wr, mdd, count = run_evaluation(df)
        print(f"\n--- Evaluation Result ---")
        print(f"Score: {score:.2f}")
        print(f"Net Profit: ${profit:.2f}")
        print(f"Win Rate: {wr*100:.2f}%")
        print(f"Max Drawdown: {mdd*100:.2f}%")
        print(f"Total Trades: {count}")
    else:
        print("No data found.")
