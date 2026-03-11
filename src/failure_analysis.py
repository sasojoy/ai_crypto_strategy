
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.market import calculate_rsi, calculate_ema, calculate_atr
import ccxt

def fetch_60d_data(symbol='BTC/USDT', timeframe='15m'):
    exchange = ccxt.binance()
    days = 60
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    while since < exchange.milliseconds():
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
        if not ohlcv: break
        since = ohlcv[-1][0] + 1
        all_ohlcv.extend(ohlcv)
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_detailed_analysis(df, initial_balance=2000):
    df['rsi'] = calculate_rsi(df)
    df['ema200'] = calculate_ema(df, 200)
    df['ema10'] = calculate_ema(df, 10)
    df['atr'] = calculate_atr(df, 14)
    df['ema200_slope'] = df['ema200'].diff(5) / 5
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    balance = initial_balance
    total_friction = 0
    
    for i in range(1, len(df)):
        if not in_position:
            # Entry Logic (Iteration 54)
            current_hour = df.loc[i, 'timestamp'].hour
            if df.loc[i, 'close'] > df.loc[i, 'ema200'] and \
               df.loc[i, 'ema200_slope'] > 0 and \
               df.loc[i-1, 'rsi'] < 35 and \
               df.loc[i, 'rsi'] > 40 and \
               not (0 <= current_hour < 4):
                
                in_position = True
                entry_price = df.loc[i, 'close']
                entry_time = df.loc[i, 'timestamp']
                current_atr = df.loc[i, 'atr']
                sl_price = entry_price - (3 * current_atr)
                tp_price = entry_price + (6 * current_atr)
                be_price = entry_price + (3 * current_atr)
                be_triggered = False
        
        elif in_position:
            current_price = df.loc[i, 'close']
            
            # Break-even logic
            if not be_triggered and current_price >= be_price:
                sl_price = entry_price
                be_triggered = True
            
            # Exit logic
            if current_price >= tp_price or current_price <= sl_price:
                price_change = (current_price - entry_price) / entry_price
                friction = balance * 0.001 # 0.1% Slippage + Fee
                profit_amount = (balance * price_change) - friction
                
                total_friction += friction
                balance += profit_amount
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': df.loc[i, 'timestamp'],
                    'profit_pct': price_change * 100,
                    'profit_amount': profit_amount,
                    'friction': friction,
                    'type': 'LONG',
                    'exit_reason': 'TP' if current_price >= tp_price else ('BE' if be_triggered else 'SL')
                })
                in_position = False

    if not trades: return None

    trades_df = pd.DataFrame(trades)
    
    # Analysis
    win_rate = len(trades_df[trades_df['profit_amount'] > 0]) / len(trades_df)
    total_pnl = trades_df['profit_amount'].sum()
    avg_pnl = trades_df['profit_amount'].mean()
    
    # MDD
    trades_df['cum_balance'] = initial_balance + trades_df['profit_amount'].cumsum()
    trades_df['peak'] = trades_df['cum_balance'].cummax()
    trades_df['drawdown'] = (trades_df['cum_balance'] - trades_df['peak']) / trades_df['peak']
    mdd = trades_df['drawdown'].min()
    
    print(f"\n--- 60天深度分析報告 ---")
    print(f"總交易次數: {len(trades_df)}")
    print(f"勝率: {win_rate*100:.2f}%")
    print(f"最大回撤 (MDD): {mdd*100:.2f}%")
    print(f"平均每筆盈虧: ${avg_pnl:.2f}")
    print(f"總摩擦成本 (手續費+滑點): ${total_friction:.2f}")
    print(f"摩擦成本佔總盈虧比: {abs(total_friction/total_pnl)*100 if total_pnl != 0 else 0:.2f}%")
    
    be_exits = len(trades_df[trades_df['exit_reason'] == 'BE'])
    print(f"保本出場次數: {be_exits} ({be_exits/len(trades_df)*100:.2f}%)")
    
    # Worst 3 days
    trades_df['date'] = trades_df['exit_time'].dt.date
    daily_pnl = trades_df.groupby('date')['profit_amount'].sum()
    rolling_3d_pnl = daily_pnl.rolling(window=3).sum()
    worst_3d = rolling_3d_pnl.idxmin()
    print(f"最慘烈 3 天區間結束於: {worst_3d} (虧損: ${rolling_3d_pnl.min():.2f})")

if __name__ == "__main__":
    for sym in ['BTC/USDT', 'SOL/USDT']:
        print(f"\n分析 {sym}...")
        df = fetch_60d_data(sym)
        run_detailed_analysis(df)
