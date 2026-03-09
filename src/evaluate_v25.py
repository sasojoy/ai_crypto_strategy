

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

def run_evaluation_v25(df, initial_balance=10000, params=None):
    if df.empty: return None

    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, params['ema_f'])
    df['ema_s'] = calculate_ema(df, params['ema_s'])
    df['atr'] = calculate_atr(df, 14)
    df['adx'] = calculate_adx(df, 14)
    ha = calculate_heikin_ashi(df)
    df = pd.concat([df, ha], axis=1)
    df['support_12h'], df['resistance_12h'] = calculate_sr_levels(df, window=12)
    df['rsi_slope'] = calculate_rsi_slope(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['bb_upper'], df['bb_lower'], df['bb_width'], _ = calculate_bollinger_bands(df, 20, 2)
    
    # 1H EMA 20 for direction
    df_1h = df.resample('h', on='timestamp').last().ffill()
    df_1h['ema20_1h'] = calculate_ema(df_1h, 20)
    df_1h['ema20_1h_prev'] = df_1h['ema20_1h'].shift(1)
    df = df.merge(df_1h[['ema20_1h', 'ema20_1h_prev']], left_on=df['timestamp'].dt.floor('h'), right_index=True, how='left')

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
            # Iteration 25: 2.5x Volume + 1H EMA 20 Direction
            avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[i]
            vol_ok = latest['volume'] > (avg_vol_5 * 2.5)
            ema20_up = latest['ema20_1h'] > latest['ema20_1h_prev']
            ha_long = latest['ha_close'] > latest['ha_open'] and prev['ha_close'] > prev['ha_open']
            rsi_ok_long = latest['rsi'] < 80 and latest['rsi_slope'] > 0
            
            # Squeeze: BB Width < 20-period average BB Width
            avg_bb_width = df['bb_width'].rolling(20).mean().iloc[i]
            squeeze = latest['bb_width'] < avg_bb_width

            # Strict Trend Filter: 15m Price > 15m EMA 50
            trend_ok = latest['close'] > latest['ema50']
            
            # Squeeze: BB Width < 20-period average BB Width
            avg_bb_width = df['bb_width'].rolling(20).mean().iloc[i]
            squeeze = latest['bb_width'] < avg_bb_width

            long_signal = ema20_up and trend_ok and ha_long and rsi_ok_long and squeeze and (vol_ok and latest['close'] > prev['resistance_12h'])

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
            # 1. Zombie Cleanup (Iteration 25: ADX < 15 & Loss)
            hours_held = (latest['timestamp'] - entry_time).total_seconds() / 3600
            is_loss = (side == 'LONG' and latest['close'] < entry_price)
            if latest['adx'] < 15 and hours_held > 4 and is_loss:
                price_diff_pct = abs(latest['close'] - entry_price) / entry_price
                if price_diff_pct < 0.005:
                    exit_price = latest['close']
                    profit = (exit_price - entry_price) * pos_size
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'Zombie Cleanup'})
                    in_position = False
                    continue

            # 2. SL / TP
            sl_price = entry_price - (params['sl_mult'] * df.iloc[i-1]['atr'])
            tp_price = entry_price + (params['sl_mult'] * df.iloc[i-1]['atr'] * 2) # 2:1 RR
            if latest['low'] <= sl_price:
                exit_price = sl_price
                profit = (exit_price - entry_price) * pos_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'SL'})
                in_position = False
            elif latest['high'] >= tp_price:
                exit_price = tp_price
                profit = (exit_price - entry_price) * pos_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit, 'result': 'TP'})
                in_position = False

    return {"balance": balance, "trades": trades, "df": df}

def calculate_sharpe(df, initial_balance):
    df = df.copy()
    df['equity'] = initial_balance
    # This is a simplified equity curve calculation for Sharpe
    # In a real backtest we'd need to track equity per step
    # For now, we'll use the final balance and trade history
    return 0 # Placeholder

if __name__ == "__main__":
    with open('config/params.json', 'r') as f:
        params = json.load(f)
    
    symbol = 'SOL/USDT'
    print(f"Evaluating {symbol} for 90 days (Iteration 25)...")
    df = fetch_backtest_data(symbol, days=90)
    res = run_evaluation_v25(df, params=params)
    
    if res:
        trades_df = pd.DataFrame(res['trades'])
        if not trades_df.empty:
            win_rate = (trades_df['profit'] > 0).sum() / len(trades_df)
            net_profit = res['balance'] - 10000
            
            # Sharpe Calculation (Daily Returns)
            trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
            daily_pnl = trades_df.set_index('exit_time')['profit'].resample('D').sum().fillna(0)
            sharpe = (daily_pnl.mean() / daily_pnl.std() * np.sqrt(365)) if daily_pnl.std() != 0 else 0

            print("\n" + "="*40)
            print(f"📊 ITERATION 25 BACKTEST: {symbol}")
            print("="*40)
            print(f"Net Profit: ${net_profit:.2f}")
            print(f"Win Rate: {win_rate*100:.2f}%")
            print(f"Sharpe Ratio: {sharpe:.2f}")
            print(f"Total Trades: {len(trades_df)}")
            print("="*40)
            
            if win_rate >= 0.55:
                print("✅ Win rate >= 55%. Ready for deployment.")
            else:
                print("❌ Win rate < 55%. Optimization required.")
        else:
            print("No trades executed.")

