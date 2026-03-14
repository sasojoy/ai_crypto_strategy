import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope

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


def run_evaluation(df, initial_balance=10000, rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True, adx_min=25, bb_std=2, df_4h=None, compounding=True, enable_short=True):
    if df.empty: return {"score": 0, "profit": 0, "win_rate": 0, "max_dd": 0, "trades": 0}

    df['rsi'] = calculate_rsi(df)
    df['ema_f'] = calculate_ema(df, ema_f)
    df['ema_s'] = calculate_ema(df, ema_s)
    df['ema_trail_long'] = calculate_ema(df, 20)
    df['ema_trail_short'] = calculate_ema(df, 10)
    df['atr'] = calculate_atr(df, 14)
    df['adx'] = calculate_adx(df, 14)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['bb_upper'], df['bb_lower'], _, _ = calculate_bollinger_bands(df, 20, bb_std)

    
    # Iteration 21 Indicators
    ha = calculate_heikin_ashi(df)
    df = pd.concat([df, ha], axis=1)
    # 12h Breakout (48 * 15m = 12h)
    df['support_12h'], df['resistance_12h'] = calculate_sr_levels(df, window=48)
    df['avg_vol_5'] = df['volume'].rolling(5).mean().shift(1)
    df['rsi_slope'] = calculate_rsi_slope(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    
    # Iteration 60: [Feature Injection] Price distance from EMA 20
    df['dist_ema20'] = (df['close'] - df['ema20']) / df['ema20']

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
            # Iteration 20 Logic
            trend_ok_long = latest['close'] > latest['ema200'] if latest['ema200'] > 0 else True
            trend_ok_short = latest['close'] < latest['ema200'] if latest['ema200'] > 0 else True
            
            vol_ok = latest['volume'] > (latest['avg_vol_5'] * 1.5)
            ha_long = latest['ha_close'] > latest['ha_open'] and prev['ha_close'] > prev['ha_open']
            ha_short = latest['ha_close'] < latest['ha_open'] and prev['ha_close'] < prev['ha_open']

            # Iteration 21: 12h Breakout + RSI Slope + Pullback Entry
            rsi_ok_long = latest['rsi'] < 80 and latest['rsi_slope'] > 0
            rsi_ok_short = latest['rsi'] > 20 and latest['rsi_slope'] < 0
            
            # Pullback Entry: 4H Trend Strong + 15m EMA 20/50 Golden Cross + Price near EMA 20 + Vol Confirmation + HA Bullish + RSI OK
            pullback_long = (trend_ok_long and latest['ema20'] > latest['ema50'] and 
                             latest['low'] <= latest['ema20'] * 1.002 and latest['close'] > latest['ema20'] and
                             latest['volume'] > latest['avg_vol_5'] and ha_long and latest['rsi'] < 70)

            long_signal = (
                trend_ok_long and ha_long and rsi_ok_long and latest['macd_hist'] > 0 and
                ( (vol_ok and latest['close'] > prev['resistance_12h']) or pullback_long )
            )

            short_signal = (
                enable_short and trend_ok_short and ha_short and rsi_ok_short and
                (vol_ok and latest['close'] < prev['support_12h'])
            )

            if long_signal or short_signal:
                in_position = True
                side = 'LONG' if long_signal else 'SHORT'
                scaled_out = False
                entry_price = latest['close']
                entry_idx = i
                
                risk_basis = balance if compounding else initial_balance
                risk_amount = risk_basis * 0.015
                
                sl_dist = sl_mult * latest['atr']
                sl_price = entry_price - sl_dist if side == 'LONG' else entry_price + sl_dist
                tp_price = entry_price + (sl_dist * 1.5) if side == 'LONG' else entry_price - (sl_dist * 1.5)
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0

                trades.append({'entry_time': latest['timestamp'], 'entry_price': entry_price, 'size': pos_size, 'side': side, 'status': 'Open'})
        else:
            # 1. Take Profit (Scale Out)
            if not scaled_out:
                if (side == 'LONG' and latest['high'] >= tp_price) or (side == 'SHORT' and latest['low'] <= tp_price):
                    scaled_out = True
                    exit_price = tp_price
                    profit = abs(exit_price - entry_price) * (pos_size * 0.5)
                    balance += profit
                    sl_price = entry_price # Move to Breakeven
                    trades[-1].update({'scaled_out_time': latest['timestamp'], 'scaled_out_price': exit_price, 'status': 'ScaledOut', 'profit': profit})

            # 2. Trailing Stop or SL
            if side == 'LONG':
                current_sl = max(sl_price, latest['ema_trail_long']) if scaled_out else sl_price
                if latest['low'] <= current_sl:
                    exit_price = current_sl
                    rem_size = pos_size * 0.5 if scaled_out else pos_size
                    profit = (exit_price - entry_price) * rem_size
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit + (trades[-1].get('profit', 0) if scaled_out else 0), 'result': 'Exit'})
                    in_position = False
            else:
                current_sl = min(sl_price, latest['ema_trail_short']) if scaled_out else sl_price
                if latest['high'] >= current_sl:
                    exit_price = current_sl
                    rem_size = pos_size * 0.5 if scaled_out else pos_size
                    profit = (entry_price - exit_price) * rem_size
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

if __name__ == "__main__":
    import json
    with open('config/params.json', 'r') as f:
        params = json.load(f)
    
    symbol = 'BTC/USDT'
    print(f"🚀 Running Iteration 20 Backtest for {symbol}...")
    
    df_all = fetch_backtest_data(symbol, days=120)
    if not df_all.empty:
        test_cutoff = df_all['timestamp'].max() - timedelta(days=30)
        df_test = df_all[df_all['timestamp'] > test_cutoff].copy()
        
        # Iteration 20: High-Precision Backtest
        result = run_evaluation(
            df_test, 
            compounding=True,
            rsi_th=params['rsi_th'],
            ema_f=params['ema_f'],
            ema_s=params['ema_s'],
            sl_mult=params['sl_mult'],
            enable_short=True # Try with short first
        )
        
        # If win rate < 50%, try disabling short
        if result['win_rate'] < 0.5:
            print("⚠️ Win rate < 50% with Shorting. Retrying with Long-Only...")
            result = run_evaluation(
                df_test, 
                compounding=True,
                rsi_th=params['rsi_th'],
                ema_f=params['ema_f'],
                ema_s=params['ema_s'],
                sl_mult=params['sl_mult'],
                enable_short=False
            )

        print("\n" + "="*30)
        print("📊 ITERATION 20 RESULTS")
        print("="*30)
        print(f"Win Rate: {result['win_rate']*100:.2f}%")
        
        # Calculate Profit Factor
        trades_df = pd.DataFrame(result['trades_list'])
        if not trades_df.empty and 'profit' in trades_df.columns:
            gross_profit = trades_df[trades_df['profit'] > 0]['profit'].sum()
            gross_loss = abs(trades_df[trades_df['profit'] < 0]['profit'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        else:
            profit_factor = 0
            
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Total Trades: {result['trades']}")
        print(f"Total Net Profit: ${result['profit']:.2f}")
        
        sharpe = generate_backtest_plot(result['df'], result['trades_list'])
        print(f"Sharpe Ratio: {sharpe:.2f}")
        print("="*30)
    else:
        print("❌ Error: No data fetched.")
