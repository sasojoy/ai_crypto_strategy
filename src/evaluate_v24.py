
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=30):
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

def run_evaluation_v24(df, initial_balance=10000, params=None):
    if df.empty: return None

    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, params['ema_f'])
    df['ema_s'] = calculate_ema(df, params['ema_s'])
    df['atr'] = calculate_atr(df, 14)
    df['adx'] = calculate_adx(df, 14)
    ha = calculate_heikin_ashi(df)
    df = pd.concat([df, ha], axis=1)
    df['support_12h'], df['resistance_12h'] = calculate_sr_levels(df, window=12) # Iteration 24
    df['rsi_slope'] = calculate_rsi_slope(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)

    balance = initial_balance
    trades = []
    in_position = False
    entry_price = 0
    pos_size = 0
    side = None
    last_scale_level = 0
    entry_time = None

    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]

        if not in_position:
            # Simplified Entry Logic for Backtest
            vol_ok = latest['volume'] > (df['volume'].rolling(5).mean().shift(1).iloc[i] * 1.5)
            ha_long = latest['ha_close'] > latest['ha_open'] and prev['ha_close'] > prev['ha_open']
            rsi_ok_long = latest['rsi'] < 80 and latest['rsi_slope'] > 0
            
            long_signal = ha_long and rsi_ok_long and (vol_ok and latest['close'] > prev['resistance_12h'])

            if long_signal:
                in_position = True
                side = 'LONG'
                entry_price = latest['close']
                entry_time = latest['timestamp']
                last_scale_level = 0
                risk_amount = balance * 0.015
                sl_dist = params['sl_mult'] * latest['atr']
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0
                trades.append({'entry_time': entry_time, 'entry_price': entry_price, 'side': side, 'status': 'Open', 'pos_size': pos_size})
        else:
            # 1. Zombie Cleanup
            hours_held = (latest['timestamp'] - entry_time).total_seconds() / 3600
            if latest['adx'] < 20 and hours_held > 4:
                price_diff_pct = abs(latest['close'] - entry_price) / entry_price
                if price_diff_pct < 0.005:
                    exit_price = latest['close']
                    profit = (exit_price - entry_price) * pos_size
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'Zombie Cleanup'})
                    in_position = False
                    continue

            # 2. Stepped Scale-out
            profit_pct = (latest['close'] - entry_price) / entry_price * 100
            scale_out_level = int(profit_pct / 3)
            if scale_out_level > last_scale_level and scale_out_level <= 4:
                # Realize 25% of current position size
                realized_profit = (latest['close'] - entry_price) * (pos_size * 0.25)
                balance += realized_profit
                pos_size *= 0.75
                last_scale_level = scale_out_level
                trades[-1]['profit'] = trades[-1].get('profit', 0) + realized_profit

            # 3. SL/TP (Simplified)
            sl_price = entry_price - (params['sl_mult'] * df.iloc[i-1]['atr'])
            if latest['low'] <= sl_price:
                exit_price = sl_price
                profit = (exit_price - entry_price) * pos_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': trades[-1].get('profit', 0) + profit, 'result': 'SL'})
                in_position = False

    return {"balance": balance, "trades": trades, "df": df}

if __name__ == "__main__":
    with open('config/params.json', 'r') as f:
        params = json.load(f)
    
    symbols = ['SOL/USDT', 'DOGE/USDT', 'XRP/USDT', 'DOT/USDT', 'AVAX/USDT']
    results = {}
    
    for symbol in symbols:
        print(f"Evaluating {symbol}...")
        df = fetch_backtest_data(symbol, days=30)
        
        # Run with Zombie Cleanup
        res = run_evaluation_v24(df, params=params)
        
        # Run WITHOUT Zombie Cleanup for comparison
        # (Temporarily modify the function or just run a modified version)
        def run_no_cleanup(df, initial_balance=10000, params=None):
            if df.empty: return None
            df = df.copy()
            df['rsi'] = calculate_rsi(df)
            df['rsi_slope'] = calculate_rsi_slope(df)
            df['ema_f'] = calculate_ema(df, params['ema_f'])
            df['ema_s'] = calculate_ema(df, params['ema_s'])
            df['atr'] = calculate_atr(df, 14)
            df['adx'] = calculate_adx(df, 14)
            ha = calculate_heikin_ashi(df)
            df = pd.concat([df, ha], axis=1)
            df['support_12h'], df['resistance_12h'] = calculate_sr_levels(df, window=12)
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
                    vol_ok = latest['volume'] > (df['volume'].rolling(5).mean().shift(1).iloc[i] * 1.5)
                    ha_long = latest['ha_close'] > latest['ha_open'] and prev['ha_close'] > prev['ha_open']
                    rsi_ok_long = latest['rsi'] < 80 and latest['rsi_slope'] > 0
                    long_signal = ha_long and rsi_ok_long and (vol_ok and latest['close'] > prev['resistance_12h'])
                    if long_signal:
                        in_position = True
                        side = 'LONG'
                        entry_price = latest['close']
                        entry_time = latest['timestamp']
                        risk_amount = balance * 0.015
                        sl_dist = params['sl_mult'] * latest['atr']
                        pos_size = risk_amount / sl_dist if sl_dist > 0 else 0
                        trades.append({'entry_time': entry_time, 'entry_price': entry_price, 'side': side, 'status': 'Open', 'pos_size': pos_size})
                else:
                    sl_price = entry_price - (params['sl_mult'] * df.iloc[i-1]['atr'])
                    if latest['low'] <= sl_price:
                        exit_price = sl_price
                        profit = (exit_price - entry_price) * pos_size
                        balance += profit
                        trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'SL'})
                        in_position = False
            return {"balance": balance, "trades": trades}

        res_no = run_no_cleanup(df, params=params)

        if res:
            trades_df = pd.DataFrame(res['trades'])
            win_rate = (trades_df['profit'] > 0).sum() / len(trades_df) if len(trades_df) > 0 else 0
            avg_duration = (pd.to_datetime(trades_df['exit_time']) - pd.to_datetime(trades_df['entry_time'])).mean() if 'exit_time' in trades_df.columns else timedelta(0)
            
            trades_no_df = pd.DataFrame(res_no['trades'])
            avg_duration_no = (pd.to_datetime(trades_no_df['exit_time']) - pd.to_datetime(trades_no_df['entry_time'])).mean() if 'exit_time' in trades_no_df.columns else timedelta(0)

            results[symbol] = {
                'net_profit': res['balance'] - 10000,
                'win_rate': win_rate,
                'trades': len(trades_df),
                'avg_duration': avg_duration,
                'avg_duration_no': avg_duration_no
            }

    print("\n" + "="*40)
    print("📊 ITERATION 24 PERFORMANCE REPORT")
    print("="*40)
    for symbol, data in results.items():
        print(f"--- {symbol} ---")
        print(f"Net Profit: ${data['net_profit']:.2f}")
        print(f"Win Rate: {data['win_rate']*100:.2f}%")
        print(f"Avg Duration (With Cleanup): {data['avg_duration']}")
        print(f"Avg Duration (No Cleanup): {data['avg_duration_no']}")
    
    overall_profit = sum(d['net_profit'] for d in results.values())
    print(f"\nOVERALL NET PROFIT: ${overall_profit:.2f}")
