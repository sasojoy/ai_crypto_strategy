


import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=90):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv: break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            break
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_evaluation_v26(df, initial_balance=10000, params=None):
    if df.empty: return None

    df['rsi'] = calculate_rsi(df)
    df['atr'] = calculate_atr(df, 14)
    df['bb_upper'], df['bb_lower'], df['bb_mid'], _ = calculate_bollinger_bands(df, 20, 2)
    
    # 4H EMA 200 for trend
    df_4h = df.resample('4h', on='timestamp').last().ffill()
    df_4h['ema200_4h'] = calculate_ema(df_4h, 200)
    df = df.merge(df_4h[['ema200_4h']], left_on=df['timestamp'].dt.floor('4h'), right_index=True, how='left')

    balance = initial_balance
    trades = []
    in_position = False
    entry_price = 0
    pos_size = 0
    side = None
    entry_time = None

    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]

        if not in_position:
            # Iteration 26: Pullback Buy
            trend_4h_strong = latest['close'] > latest['ema200_4h']
            rsi_oversold = latest['rsi'] < 35
            price_at_bb_lower = latest['low'] <= latest['bb_lower']
            rsi_hook_up = latest['rsi'] > prev['rsi']
            first_green = latest['close'] > latest['open']

            if trend_4h_strong and rsi_oversold and price_at_bb_lower and rsi_hook_up and first_green:
                in_position = True
                side = 'LONG'
                entry_price = latest['close']
                entry_time = latest['timestamp']
                risk_amount = balance * 0.015
                sl_dist = 3.0 * latest['atr']
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0
                trades.append({'entry_time': entry_time, 'entry_price': entry_price, 'side': side, 'status': 'Open', 'pos_size': pos_size})
        else:
            # 1. SL (3.0x ATR)
            sl_price = entry_price - (3.0 * df.iloc[i-1]['atr'])
            if latest['low'] <= sl_price:
                exit_price = sl_price
                profit = (exit_price - entry_price) * pos_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'SL'})
                in_position = False
                continue

            # 2. TP (BB Upper)
            if latest['high'] >= latest['bb_upper']:
                exit_price = latest['bb_upper']
                profit = (exit_price - entry_price) * pos_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'TP_BB_Upper'})
                in_position = False

    return {"balance": balance, "trades": trades, "df": df}

if __name__ == "__main__":
    with open('config/params.json', 'r') as f:
        params = json.load(f)
    
    symbol = 'SOL/USDT'
    print(f"Evaluating {symbol} for 90 days (Iteration 26 - Pullback Buy)...")
    df = fetch_backtest_data(symbol, days=90)
    res = run_evaluation_v26(df, params=params)
    
    if res:
        trades_df = pd.DataFrame(res['trades'])
        if not trades_df.empty:
            win_rate = (trades_df['profit'] > 0).sum() / len(trades_df)
            net_profit = res['balance'] - 10000
            
            print("\n" + "="*40)
            print(f"📊 ITERATION 26 BACKTEST: {symbol}")
            print("="*40)
            print(f"Net Profit: ${net_profit:.2f}")
            print(f"Win Rate: {win_rate*100:.2f}%")
            print(f"Total Trades: {len(trades_df)}")
            print("="*40)
            
            if win_rate >= 0.50:
                print("✅ Win rate >= 50%. Ready for deployment.")
            else:
                print("❌ Win rate < 50%. Analyzing losses...")
                # Analysis of last 5 losing trades
                losses = trades_df[trades_df['profit'] < 0].tail(5)
                print("\nLast 5 Losing Trades:")
                print(losses[['entry_time', 'exit_time', 'entry_price', 'exit_price', 'profit', 'result']])
        else:
            print("No trades executed.")


