
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# Import logic from market.py
from src.market import calculate_rsi, calculate_ema, calculate_atr, calculate_macd

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=60):
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

def run_evaluation(df, initial_balance=10000, rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True):
    # Indicators
    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, ema_f)
    df['ema_s'] = calculate_ema(df, ema_s)
    df['atr'] = calculate_atr(df, 14)
    _, _, df['macd_hist'] = calculate_macd(df)
    
    # Volatility Warning: 24h (96 candles of 15m) Avg ATR
    df['atr_ma24h'] = df['atr'].rolling(96).mean()
    
    df = df.dropna().reset_index(drop=True)
    
    balance = initial_balance
    trades = []
    in_position = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    
    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]
        
        if not in_position:
            # Volatility Filter: ATR must not exceed 2x of 24h average
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            
            # MACD Confirmation: Histogram > 0 and increasing
            macd_ok = True
            if macd_confirm:
                macd_ok = latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']
            
            # Entry Logic
            if volatility_ok and macd_ok and \
               latest['close'] > latest['ema_f'] and \
               latest['ema_f'] > latest['ema_s'] and \
               prev['rsi'] < rsi_th and latest['rsi'] > rsi_th:
                in_position = True
                entry_price = latest['close']
                sl_price = entry_price - (sl_mult * latest['atr'])
                tp_price = entry_price + (sl_mult * 2 * latest['atr'])
                
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

def get_full_report(symbol='BTC/USDT', rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True):
    df_all = fetch_backtest_data(symbol, days=90) # Increased to 90 days as requested
    if df_all.empty:
        return "No data found."
    
    mid_point = len(df_all) // 2
    df_train = df_all.iloc[:mid_point].copy()
    df_test = df_all.iloc[mid_point:].copy()
    
    score_tr, profit_tr, wr_tr, mdd_tr, count_tr = run_evaluation(df_train, rsi_th=rsi_th, ema_f=ema_f, ema_s=ema_s, sl_mult=sl_mult, macd_confirm=macd_confirm)
    score_ts, profit_ts, wr_ts, mdd_ts, count_ts = run_evaluation(df_test, rsi_th=rsi_th, ema_f=ema_f, ema_s=ema_s, sl_mult=sl_mult, macd_confirm=macd_confirm)
    
    report = f"### [Strategy Iteration] Report - {datetime.now().strftime('%Y-%m-%d')}\n\n"
    report += f"#### Symbol: {symbol} | RSI: {rsi_th} | EMA_F: {ema_f} | EMA_S: {ema_s} | SL: {sl_mult} | MACD: {macd_confirm}\n\n"
    report += "| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |\n"
    report += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    report += f"| **Train (30d)** | {score_tr:.2f} | ${profit_tr:.2f} | {wr_tr*100:.2f}% | {mdd_tr*100:.2f}% | {count_tr} |\n"
    report += f"| **Test (30d)** | {score_ts:.2f} | ${profit_ts:.2f} | {wr_ts*100:.2f}% | {mdd_ts*100:.2f}% | {count_ts} |\n\n"
    
    if profit_tr > 0 and profit_ts > 0:
        report += "✅ **Strategy passed OOS test.**\n"
    else:
        report += "❌ **Strategy failed OOS test.**\n"
        
    return report

if __name__ == "__main__":
    print(get_full_report())
