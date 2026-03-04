
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.market import calculate_rsi, calculate_ema

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

def run_backtest(df):
    df['rsi'] = calculate_rsi(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    
    # Drop rows with NaN values from indicators
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    entry_price = 0
    
    for i in range(len(df)):
        # Buy condition
        if not in_position:
            if df.loc[i, 'close'] > df.loc[i, 'ema20'] and \
               df.loc[i, 'ema20'] > df.loc[i, 'ema50'] and \
               df.loc[i, 'rsi'] < 30:
                
                in_position = True
                entry_price = df.loc[i, 'close']
                entry_time = df.loc[i, 'timestamp']
        
        # Sell condition (Simple: 1% take profit or 0.5% stop loss for backtest purposes)
        # You can adjust this logic as needed
        elif in_position:
            current_price = df.loc[i, 'close']
            price_change = (current_price - entry_price) / entry_price
            
            if price_change >= 0.01 or price_change <= -0.005:
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': df.loc[i, 'timestamp'],
                    'entry_price': entry_price,
                    'exit_price': current_price,
                    'profit': price_change
                })
                in_position = False
                
    if not trades:
        return 0, 0, 0
    
    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df['profit'] > 0).sum() / total_trades * 100
    
    # Calculate Max Drawdown
    trades_df['cumulative_profit'] = (1 + trades_df['profit']).cumprod()
    peak = trades_df['cumulative_profit'].cummax()
    drawdown = (trades_df['cumulative_profit'] - peak) / peak
    max_drawdown = drawdown.min() * 100
    
    return total_trades, win_rate, max_drawdown

if __name__ == "__main__":
    print("正在獲取過去 30 天的數據...")
    df = fetch_backtest_data()
    print(f"獲取到 {len(df)} 條數據。")
    
    total_trades, win_rate, max_drawdown = run_backtest(df)
    
    print("\n--- 回測結果 ---")
    print(f"總交易次數: {total_trades}")
    print(f"勝率: {win_rate:.2f}%")
    print(f"最大回撤: {max_drawdown:.2f}%")
