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


def run_evaluation(df, initial_balance=10000, rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True, adx_min=25, bb_std=2, df_4h=None, compounding=True):
    if df.empty: return {"score": 0, "profit": 0, "win_rate": 0, "max_dd": 0, "trades": 0}

    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, ema_f)
    df['ema_s'] = calculate_ema(df, ema_s)
    df['ema_trail_long'] = calculate_ema(df, 20)
    df['ema_trail_short'] = calculate_ema(df, 10)
    df['atr'] = calculate_atr(df, 14)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['adx'] = calculate_adx(df, 14)
    df['bb_upper'], df['bb_lower'], df['bb_bandwidth'], df['bb_percent_b'] = calculate_bollinger_bands(df, 20, bb_std)
    
    # Bollinger Band Squeeze (5th percentile of bandwidth)
    df['bw_min'] = df['bb_bandwidth'].rolling(100).quantile(0.05)

    # 4H Trend Filter
    if df_4h is not None:
        df_4h['ema200'] = calculate_ema(df_4h, 200)
        df = df.merge(df_4h[['timestamp', 'ema200']], on='timestamp', how='left').ffill()
    else:
        df['ema200'] = 0

    df = df.dropna().reset_index(drop=True)
    balance = initial_balance
    trades = []
    in_position = False
    scaled_out = False
    entry_price = 0
    sl_price = 0
    pos_size = 0
    entry_idx = 0
    side = None # 'LONG' or 'SHORT'

    for i in range(1, len(df)):
        latest = df.iloc[i]
        prev = df.iloc[i-1]

        if not in_position:
            is_squeezed = latest['bb_bandwidth'] < latest['bw_min']
            
            # Long Entry Logic
            adx_ok_long = latest['adx'] > (18 if is_squeezed else adx_min)
            trend_ok_long = latest['close'] > latest['ema200'] if latest['ema200'] > 0 else True
            
            # Iteration 19: Mean Reversion Signal
            long_mr_signal = latest['rsi'] < 20 and latest['close'] < latest['bb_lower']
            
            long_signal = (
                (trend_ok_long and adx_ok_long and
                latest['close'] > latest['ema_f'] and
                latest['ema_f'] > latest['ema_s'] and
                (is_squeezed and latest['close'] > latest['bb_upper'] or (prev['rsi'] < rsi_th and latest['rsi'] > rsi_th)))
                or (long_mr_signal and trend_ok_long)
            )

            # Short Entry Logic (Iteration 18)
            adx_ok_short = latest['adx'] > 30
            trend_ok_short = latest['close'] < latest['ema200'] if latest['ema200'] > 0 else True
            
            # Iteration 19: Mean Reversion Signal
            short_mr_signal = latest['rsi'] > 80 and latest['close'] > latest['bb_upper']

            short_signal = (
                (trend_ok_short and adx_ok_short and
                latest['close'] < latest['ema_f'] and
                latest['ema_f'] < latest['ema_s'] and
                (is_squeezed and latest['close'] < latest['bb_lower'] or (prev['rsi'] > (100-rsi_th) and latest['rsi'] < (100-rsi_th))))
                or (short_mr_signal and trend_ok_short)
            )

            if long_signal or short_signal:
                in_position = True
                side = 'LONG' if long_signal else 'SHORT'
                scaled_out = False
                entry_price = latest['close']
                entry_idx = i
                
                # Iteration 19: Compounding vs Simple Interest
                risk_basis = balance if compounding else initial_balance
                risk_amount = risk_basis * 0.015
                
                sl_dist = sl_mult * latest['atr']
                sl_price = entry_price - sl_dist if side == 'LONG' else entry_price + sl_dist
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0

                trades.append({'entry_time': latest['timestamp'], 'entry_price': entry_price, 'size': pos_size, 'side': side, 'status': 'Open'})
        else:
            # 1. Scaling Out
            if not scaled_out:
                if side == 'LONG' and latest['high'] >= latest['bb_upper']:
                    scaled_out = True
                    exit_price = latest['bb_upper']
                    profit = (exit_price - entry_price) * (pos_size * 0.5)
                    balance += profit
                    sl_price = entry_price # Move to Breakeven
                    trades[-1].update({'scaled_out_time': latest['timestamp'], 'scaled_out_price': exit_price, 'status': 'ScaledOut'})
                elif side == 'SHORT' and latest['low'] <= latest['bb_lower']:
                    scaled_out = True
                    exit_price = latest['bb_lower']
                    profit = (entry_price - exit_price) * (pos_size * 0.7) # Short scale out 70%
                    balance += profit
                    sl_price = entry_price # Move to Breakeven
                    trades[-1].update({'scaled_out_time': latest['timestamp'], 'scaled_out_price': exit_price, 'status': 'ScaledOut'})

            # 2. Time Stop
            if (i - entry_idx) >= 12 and abs(latest['close'] - entry_price) / entry_price < 0.005:
                exit_price = latest['close']
                if side == 'LONG':
                    rem_size = pos_size * 0.5 if scaled_out else pos_size
                    profit = (exit_price - entry_price) * rem_size
                else:
                    rem_size = pos_size * 0.3 if scaled_out else pos_size
                    profit = (entry_price - exit_price) * rem_size
                balance += profit
                trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit + (trades[-1].get('profit', 0) if scaled_out else 0), 'result': 'TimeStop'})
                in_position = False
                continue

            # 3. Trailing Stop or SL
            if side == 'LONG':
                current_sl = max(sl_price, latest['ema_trail_long']) if scaled_out else sl_price
                if latest['low'] <= current_sl:
                    exit_price = current_sl
                    profit = (exit_price - entry_price) * (pos_size * 0.5 if scaled_out else pos_size)
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit + (trades[-1].get('profit', 0) if scaled_out else 0), 'result': 'Exit'})
                    in_position = False
            else:
                current_sl = min(sl_price, latest['ema_trail_short']) if scaled_out else sl_price
                if latest['high'] >= current_sl:
                    exit_price = current_sl
                    profit = (entry_price - exit_price) * (pos_size * 0.3 if scaled_out else pos_size)
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit + (trades[-1].get('profit', 0) if scaled_out else 0), 'result': 'Exit'})
                    in_position = False

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df["profit"] > 0).sum() / total_trades if total_trades > 0 else 0
    net_profit = balance - initial_balance
    if total_trades > 0:
        trades_df["cum_profit"] = trades_df["profit"].cumsum() + initial_balance
        peak = trades_df["cum_profit"].cummax()
        drawdown = (trades_df["cum_profit"] - peak) / peak
        max_dd = abs(drawdown.min())
    else:
        max_dd = 0
    score = (net_profit * win_rate) / max_dd if max_dd != 0 else 0
    return {"score": score, "profit": net_profit, "win_rate": win_rate, "max_dd": max_dd, "trades": total_trades, "trades_list": trades, "df": df}


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

import matplotlib.pyplot as plt

def generate_backtest_plot(df, trades, initial_balance=10000):
    if not trades:
        print("No trades to plot.")
        return

    trades_df = pd.DataFrame(trades)
    df = df.copy()

    # Calculate Equity Curve
    df['equity'] = float(initial_balance)
    current_balance = float(initial_balance)
    for _, trade in trades_df.iterrows():
        if 'exit_time' in trade:
            df.loc[df['timestamp'] >= trade['exit_time'], 'equity'] += trade['profit']

    # Calculate Sharpe Ratio (Daily)
    df['returns'] = df['equity'].pct_change()
    daily_returns = df.set_index('timestamp')['returns'].resample('D').sum()
    sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if daily_returns.std() != 0 else 0

    plt.figure(figsize=(15, 10))

    # Subplot 1: Price and Trades
    ax1 = plt.subplot(2, 1, 1)
    plt.plot(df['timestamp'], df['close'], label='Price', alpha=0.5)

    # Plot Entries
    plt.scatter(trades_df['entry_time'], trades_df['entry_price'], marker='^', color='green', label='Buy', s=100)

    # Plot Exits
    if 'exit_time' in trades_df.columns:
        plt.scatter(trades_df['exit_time'], trades_df['exit_price'], marker='v', color='red', label='Sell', s=100)

    plt.title(f"Backtest Results - Sharpe Ratio: {sharpe:.2f}")
    plt.legend()
    plt.grid(True)

    # Subplot 2: Equity Curve
    ax2 = plt.subplot(2, 1, 2, sharex=ax1)
    plt.plot(df['timestamp'], df['equity'], label='Equity Curve', color='blue')
    plt.fill_between(df['timestamp'], initial_balance, df['equity'], where=(df['equity'] >= initial_balance), color='green', alpha=0.1)
    plt.fill_between(df['timestamp'], initial_balance, df['equity'], where=(df['equity'] < initial_balance), color='red', alpha=0.1)
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig('backtest_result.png')
    plt.close()
    print(f"Backtest plot saved to backtest_result.png. Sharpe Ratio: {sharpe:.2f}")
    return sharpe
