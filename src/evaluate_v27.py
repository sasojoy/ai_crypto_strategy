



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

def run_evaluation_v27(df, initial_balance=10000, params=None, pyramiding=True):
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
    pyramided = False
    sl_price = 0

    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]

        if not in_position:
            # Iteration 26/27: Pullback Buy
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
                risk_amount = balance * params.get('risk_per_trade', 0.025)
                sl_dist = 3.0 * latest['atr']
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0
                sl_price = entry_price - sl_dist
                pyramided = False
                trades.append({'entry_time': entry_time, 'entry_price': entry_price, 'side': side, 'status': 'Open', 'pos_size': pos_size})
        else:
            # Iteration 27: Pyramiding
            if pyramiding and not pyramided:
                profit_pct = (latest['close'] - entry_price) / entry_price * 100
                if profit_pct > 1.0 and latest['rsi'] < 50:
                    # Add 30%
                    add_size = pos_size * 0.3
                    new_pos_size = pos_size + add_size
                    entry_price = (entry_price * pos_size + latest['close'] * add_size) / new_pos_size
                    pos_size = new_pos_size
                    sl_price = entry_price # Move to break-even
                    pyramided = True
                    trades[-1]['pyramided'] = True

            # 1. SL
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
    print(f"Evaluating {symbol} for 90 days...")
    df = fetch_backtest_data(symbol, days=90)
    
    print("\n--- Running WITHOUT Pyramiding (Iteration 26 Base) ---")
    res_base = run_evaluation_v27(df, params=params, pyramiding=False)
    profit_base = res_base['balance'] - 10000
    
    print("\n--- Running WITH Pyramiding (Iteration 27 Accelerator) ---")
    res_acc = run_evaluation_v27(df, params=params, pyramiding=True)
    profit_acc = res_acc['balance'] - 10000
    
    improvement = ((profit_acc - profit_base) / abs(profit_base) * 100) if profit_base != 0 else 0
    
    print("\n" + "="*40)
    print(f"📊 ITERATION 27 PERFORMANCE COMPARISON: {symbol}")
    print("="*40)
    print(f"Base Profit (v26): ${profit_base:.2f}")
    print(f"Accel Profit (v27): ${profit_acc:.2f}")
    print(f"Profit Improvement: {improvement:.2f}%")
    
    trades_acc = pd.DataFrame(res_acc['trades'])
    if not trades_acc.empty:
        win_rate = (trades_acc['profit'] > 0).sum() / len(trades_acc)
        print(f"Win Rate (v27): {win_rate*100:.2f}%")
        print(f"Total Trades: {len(trades_acc)}")
        print(f"Pyramided Trades: {trades_acc.get('pyramided', pd.Series([False]*len(trades_acc))).sum()}")
    print("="*40)

    # Evaluate other symbols
    for s in ['ETH/USDT', 'AVAX/USDT', 'NEAR/USDT']:
        print(f"\nEvaluating {s}...")
        df_s = fetch_backtest_data(s, days=90)
        res_s = run_evaluation_v27(df_s, params=params, pyramiding=True)
        if res_s:
            t_s = pd.DataFrame(res_s['trades'])
            if not t_s.empty:
                wr = (t_s['profit'] > 0).sum() / len(t_s)
                prof = res_s['balance'] - 10000
                print(f"{s} Win Rate: {wr*100:.2f}% | Profit: ${prof:.2f}")
                if wr > 0.55:
                    print(f"✅ {s} passed 55% win rate threshold.")
                else:
                    print(f"❌ {s} failed 55% win rate threshold.")



