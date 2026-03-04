
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.market import calculate_rsi, calculate_ema, calculate_atr

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

def run_backtest(df, initial_balance=2000):
    df['rsi'] = calculate_rsi(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['ema200'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    
    # 計算 EMA 200 斜率 (過去 5 根 K 線)
    df['ema200_slope'] = df['ema200'].diff(5) / 5
    
    # Drop rows with NaN values from indicators
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    entry_price = 0
    balance = initial_balance
    tp_price = 0
    sl_price = 0
    be_triggered = False # Break-even trigger
    
    for i in range(1, len(df)):
        # Buy condition
        if not in_position:
            # 勾頭確認進場條件：
            # 1. 價格 > EMA 200 (大趨勢向上)
            # 2. EMA 200 斜率 > 0 (趨勢昂首)
            # 3. 前一根 RSI < 35 (曾進入超賣)
            # 4. 當前 RSI > 40 (動能回升)
            # 5. 排除凌晨 00:00 - 04:00 (UTC)
            current_hour = df.loc[i, 'timestamp'].hour
            if df.loc[i, 'close'] > df.loc[i, 'ema200'] and \
               df.loc[i, 'ema200_slope'] > 0 and \
               df.loc[i-1, 'rsi'] < 35 and \
               df.loc[i, 'rsi'] > 40 and \
               not (0 <= current_hour < 4):
                
                in_position = True
                entry_price = df.loc[i, 'close']
                entry_time = df.loc[i, 'timestamp']
                be_triggered = False
                
                # 優化 ATR 空間 (3*ATR 止損, 6*ATR 止盈)
                current_atr = df.loc[i, 'atr']
                sl_price = entry_price - (3 * current_atr)
                tp_price = entry_price + (6 * current_atr)
                be_price = entry_price + (3 * current_atr) # 達到 3*ATR 時觸發保本
        
        # Sell condition
        elif in_position:
            current_price = df.loc[i, 'close']
            
            # 移動止盈 (Trailing Stop to Break-even)
            if not be_triggered and current_price >= be_price:
                sl_price = entry_price
                be_triggered = True
            
            # Check TP or SL
            if current_price >= tp_price or current_price <= sl_price:
                price_change = (current_price - entry_price) / entry_price
                profit_amount = balance * price_change
                balance += profit_amount
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': df.loc[i, 'timestamp'],
                    'entry_price': entry_price,
                    'exit_price': current_price,
                    'profit_pct': price_change * 100,
                    'profit_amount': profit_amount,
                    'balance': balance
                })
                in_position = False
                
    if not trades:
        return 0, 0, 0, 0, pd.DataFrame()
    
    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df['profit_pct'] > 0).sum() / total_trades * 100
    net_profit = balance - initial_balance
    
    # Calculate Max Drawdown
    trades_df['cumulative_balance'] = trades_df['balance']
    peak = trades_df['cumulative_balance'].cummax()
    drawdown = (trades_df['cumulative_balance'] - peak) / peak
    max_drawdown = drawdown.min() * 100
    
    return total_trades, win_rate, net_profit, max_drawdown, trades_df

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'SOL/USDT']
    initial_balance = 2000
    
    for symbol in symbols:
        print(f"\n正在獲取 {symbol} 過去 30 天的數據...")
        df = fetch_backtest_data(symbol=symbol)
        print(f"獲取到 {len(df)} 條數據。")
        
        total_trades, win_rate, net_profit, max_drawdown, trades_df = run_backtest(df, initial_balance=initial_balance)
        
        print(f"\n--- {symbol} 回測報告 ---")
        print(f"起始資金: ${initial_balance}")
        print(f"總交易次數: {total_trades}")
        print(f"勝率: {win_rate:.2f}%")
        print(f"淨獲利: ${net_profit:.2f}")
        print(f"最大回撤: {max_drawdown:.2f}%")
        if not trades_df.empty:
            print(f"最終餘額: ${trades_df['balance'].iloc[-1]:.2f}")
            print("\n--- 交易明細 (前 5 筆) ---")
            print(trades_df[['entry_time', 'exit_time', 'profit_pct', 'balance']].head())
