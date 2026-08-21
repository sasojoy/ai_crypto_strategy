import re

path = 'src/evaluate.py'
with open(path, 'r') as f:
    content = f.read()

new_run_evaluation = """
def run_evaluation(df, initial_balance=10000, rsi_th=30, ema_f=50, ema_s=200, sl_mult=2, macd_confirm=True, adx_min=25, bb_std=2, df_4h=None):
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
            long_signal = (
                trend_ok_long and adx_ok_long and
                latest['close'] > latest['ema_f'] and
                latest['ema_f'] > latest['ema_s'] and
                (is_squeezed and latest['close'] > latest['bb_upper'] or (prev['rsi'] < rsi_th and latest['rsi'] > rsi_th))
            )

            # Short Entry Logic (Iteration 18)
            adx_ok_short = latest['adx'] > 30
            trend_ok_short = latest['close'] < latest['ema200'] if latest['ema200'] > 0 else True
            short_signal = (
                trend_ok_short and adx_ok_short and
                latest['close'] < latest['ema_f'] and
                latest['ema_f'] < latest['ema_s'] and
                (is_squeezed and latest['close'] < latest['bb_lower'] or (prev['rsi'] > (100-rsi_th) and latest['rsi'] < (100-rsi_th)))
            )

            if long_signal or short_signal:
                in_position = True
                side = 'LONG' if long_signal else 'SHORT'
                scaled_out = False
                entry_price = latest['close']
                entry_idx = i
                
                risk_amount = balance * 0.015
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
"""

pattern = r'def run_evaluation\(.*?\):.*?in_position = False\n\s+scaled_out = False'
# The pattern above is too short and might match multiple things or fail.
# Let's use a more robust pattern for the whole function.
pattern = r'def run_evaluation\(.*?\):.*?in_position = False\n\s+scaled_out = False'
# Actually, let's just replace from def run_evaluation to the end of the loop.

pattern = r'def run_evaluation\(.*?\):.*?in_position = False\n\s+scaled_out = False'

# Let's try to find the whole function
pattern = r'def run_evaluation\(.*?\):.*?return \{"score": score, "profit": net_profit, "win_rate": win_rate, "max_dd": max_dd, "trades": total_trades, "trades_list": trades, "df": df\}'
new_content = re.sub(pattern, new_run_evaluation + '\n    trades_df = pd.DataFrame(trades)\n    total_trades = len(trades_df)\n    win_rate = (trades_df["profit"] > 0).sum() / total_trades if total_trades > 0 else 0\n    net_profit = balance - initial_balance\n    if total_trades > 0:\n        trades_df["cum_profit"] = trades_df["profit"].cumsum() + initial_balance\n        peak = trades_df["cum_profit"].cummax()\n        drawdown = (trades_df["cum_profit"] - peak) / peak\n        max_dd = abs(drawdown.min())\n    else:\n        max_dd = 0\n    score = (net_profit * win_rate) / max_dd if max_dd != 0 else 0\n    return {"score": score, "profit": net_profit, "win_rate": win_rate, "max_dd": max_dd, "trades": total_trades, "trades_list": trades, "df": df}', content, flags=re.DOTALL)

with open(path, 'w') as f:
    f.write(new_content)
