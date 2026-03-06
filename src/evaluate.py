import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=120):
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
            print(f"Error fetching data: {e}")
            break
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_evaluation(df, initial_balance=10000, rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True, adx_min=25, bb_std=2):
    if df.empty: return {"score": 0, "profit": 0, "win_rate": 0, "max_dd": 0, "trades": 0}

    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, ema_f)
    df['ema_s'] = calculate_ema(df, ema_s)
    df['ema_trail'] = calculate_ema(df, 20) # For trailing stop
    df['atr'] = calculate_atr(df, 14)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['adx'] = calculate_adx(df, 14)
    df['bb_upper'], df['bb_lower'], df['bb_bandwidth'], df['bb_percent_b'] = calculate_bollinger_bands(df, 20, bb_std)
    df['atr_ma24h'] = df['atr'].rolling(96).mean()

    df = df.dropna().reset_index(drop=True)
    balance = initial_balance
    trades = []
    in_position = False
    scaled_out = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    pos_size = 0

    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]

        if not in_position:
            adx_ok = latest['adx'] > adx_min
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            macd_ok = True
            if macd_confirm:
                macd_ok = latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']

            if adx_ok and volatility_ok and macd_ok and \
               latest['close'] > latest['ema_f'] and \
               latest['ema_f'] > latest['ema_s'] and \
               prev['rsi'] < rsi_th and latest['rsi'] > rsi_th:
                in_position = True
                scaled_out = False
                entry_price = latest['close']
                sl_price = entry_price - (sl_mult * latest['atr'])
                tp_price = entry_price + (sl_mult * 2 * latest['atr'])

                # Risk-based sizing (1% risk)
                risk_amount = balance * 0.01
                sl_dist = entry_price - sl_price
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0

                trades.append({'entry_time': latest['timestamp'], 'entry_price': entry_price, 'size': pos_size, 'status': 'Open'})
        else:
            # 1. Scaling Out (BB Upper)
            if not scaled_out and latest['high'] >= latest['bb_upper']:
                scaled_out = True
                exit_price = latest['bb_upper']
                profit = (exit_price - entry_price) * (pos_size * 0.5)
                balance += profit
                # Move to Breakeven
                sl_price = entry_price
                trades[-1]['scaled_out_time'] = latest['timestamp']
                trades[-1]['scaled_out_price'] = exit_price
                trades[-1]['status'] = 'ScaledOut'

            # 2. Trailing Stop (EMA 20) or Initial SL (Breakeven if scaled out)
            current_sl = max(sl_price, latest['ema_trail']) if scaled_out else sl_price

            if latest['low'] <= current_sl:
                exit_price = current_sl
                remaining_size = pos_size * 0.5 if scaled_out else pos_size
                profit = (exit_price - entry_price) * remaining_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit + (trades[-1].get('profit', 0) if scaled_out else 0), 'result': 'Exit'})
                in_position = False
                scaled_out = False

    if not trades or 'exit_price' not in trades[-1]:
        if trades and 'exit_price' not in trades[-1]: trades.pop()
        if not trades: return {"score": 0, "profit": 0, "win_rate": 0, "max_dd": 0, "trades": 0}

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df['profit'] > 0).sum() / total_trades
    net_profit = balance - initial_balance
    trades_df['cum_profit'] = trades_df['profit'].cumsum() + initial_balance
    peak = trades_df['cum_profit'].cummax()
    drawdown = (trades_df['cum_profit'] - peak) / peak
    max_dd = abs(drawdown.min())
    score = (net_profit * win_rate) / max_dd if max_dd != 0 else 0
    return {"score": score, "profit": net_profit, "win_rate": win_rate, "max_dd": max_dd, "trades": total_trades}


def get_full_report(symbol='BTC/USDT', rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True, adx_min=25, bb_std=2):
    df_all = fetch_backtest_data(symbol, days=120)
    if df_all.empty: return None
    test_cutoff = df_all['timestamp'].max() - timedelta(days=30)
    df_train = df_all[df_all['timestamp'] <= test_cutoff].copy()
    df_test = df_all[df_all['timestamp'] > test_cutoff].copy()
    res_tr = run_evaluation(df_train, rsi_th=rsi_th, ema_f=ema_f, ema_s=ema_s, sl_mult=sl_mult, macd_confirm=macd_confirm, adx_min=adx_min, bb_std=bb_std)
    res_ts = run_evaluation(df_test, rsi_th=rsi_th, ema_f=ema_f, ema_s=ema_s, sl_mult=sl_mult, macd_confirm=macd_confirm, adx_min=adx_min, bb_std=bb_std)
    report_str = f"### [Strategy Iteration] Report - {datetime.now().strftime('%Y-%m-%d')}\n"
    report_str += f"#### Symbol: {symbol} | RSI: {rsi_th} | EMA_F: {ema_f} | EMA_S: {ema_s} | SL: {sl_mult} | ADX_Min: {adx_min}\n"
    report_str += "| Period | Score | Net Profit | Win Rate | Max Drawdown | Trades |\n"
    report_str += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    report_str += f"| **Train (90d)** | {res_tr['score']:.2f} | ${res_tr['profit']:.2f} | {res_tr['win_rate']*100:.2f}% | {res_tr['max_dd']*100:.2f}% | {res_tr['trades']} |\n"
    report_str += f"| **Test (30d)** | {res_ts['score']:.2f} | ${res_ts['profit']:.2f} | {res_ts['win_rate']*100:.2f}% | {res_ts['max_dd']*100:.2f}% | {res_ts['trades']} |\n"
    return {"symbol": symbol, "train": res_tr, "test": res_ts, "report_str": report_str}
