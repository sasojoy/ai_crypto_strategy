import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import joblib
import json
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope
from src.features import extract_features

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
            print(f"Error fetching data: {e}")
            break
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_multi_symbol_backtest(symbols=['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT', 'NEAR/USDT'], days=30):
    all_trades = []
    initial_balance = 10000
    
    for symbol in symbols:
        print(f"Fetching data for {symbol}...")
        df_15m = fetch_backtest_data(symbol, timeframe='15m', days=days)
        df_5m = fetch_backtest_data(symbol, timeframe='5m', days=days)
        if df_15m.empty or df_5m.empty: continue
        
        model_path = 'models/rf_model.joblib'
        model = joblib.load(model_path)
        
        # Prepare 15m indicators
        df_15m['atr'] = calculate_atr(df_15m, 14)
        df_15m['ema200'] = calculate_ema(df_15m, 200)
        df_15m['ema50'] = calculate_ema(df_15m, 50)
        df_15m['ema20'] = calculate_ema(df_15m, 20)
        df_15m['rsi'] = calculate_rsi(df_15m)
        _, _, df_15m['bb_width'], _ = calculate_bollinger_bands(df_15m)
        df_features_15m = extract_features(df_15m)
        feature_cols = model.feature_names_in_
        X_15m = df_features_15m[feature_cols].fillna(0)
        df_15m['ml_prob'] = 0.0
        df_15m.loc[df_features_15m.index, 'ml_prob'] = model.predict_proba(X_15m)[:, 1]

        # Prepare 5m indicators
        df_5m['atr'] = calculate_atr(df_5m, 14)
        df_5m['ema200'] = calculate_ema(df_5m, 200)
        df_5m['ema50'] = calculate_ema(df_5m, 50)
        df_5m['ema20'] = calculate_ema(df_5m, 20)
        df_5m['rsi'] = calculate_rsi(df_5m)
        _, _, df_5m['bb_width'], _ = calculate_bollinger_bands(df_5m)
        df_features_5m = extract_features(df_5m)
        X_5m = df_features_5m[feature_cols].fillna(0)
        df_5m['ml_prob'] = 0.0
        df_5m.loc[df_features_5m.index, 'ml_prob'] = model.predict_proba(X_5m)[:, 1]

        in_position = False
        for i in range(100, len(df_15m)):
            latest_15m = df_15m.iloc[i]
            
            if not in_position:
                ml_score_15m = latest_15m['ml_prob']
                bb_width_20_pct_15m = df_15m['bb_width'].iloc[i-100:i].quantile(0.20)
                is_squeezed_15m = latest_15m['bb_width'] < bb_width_20_pct_15m
                ema_aligned_15m = latest_15m['ema20'] > latest_15m['ema50']
                ema20_slope_up_15m = df_15m['ema20'].iloc[i] > df_15m['ema20'].iloc[i-1]

                passed_filter = False
                tier = 0
                risk = 0
                rr = 0

                if ml_score_15m >= 0.63: # Tier 1
                    tier, risk, rr, passed_filter = 1, 0.012, 1.5, ema20_slope_up_15m
                elif ml_score_15m >= 0.58: # Tier 2
                    tier, risk, rr = 2, 0.005, 2.0
                    passed_filter = is_squeezed_15m and ema_aligned_15m and ema20_slope_up_15m
                
                # 5m Auxiliary Scan
                if not passed_filter:
                    ts = latest_15m['timestamp']
                    df_5m_prev = df_5m[df_5m['timestamp'] <= ts]
                    if not df_5m_prev.empty:
                        latest_5m = df_5m_prev.iloc[-1]
                        # Tier 3 requires higher score and basic trend alignment
                        ema_aligned_5m = latest_5m['ema20'] > latest_5m['ema50']
                        ema20_slope_up_5m = df_5m_prev['ema20'].iloc[-1] > df_5m_prev['ema20'].iloc[-2] if len(df_5m_prev) > 1 else False
                        if latest_5m['ml_prob'] > 0.70 and ema_aligned_5m and ema20_slope_up_5m and (55 <= latest_5m['rsi'] <= 70):
                            tier, risk, rr, passed_filter = 3, 0.008, 1.5, True

                # Space Check (1.2%)
                recent_high = df_15m['high'].iloc[max(0, i-96):i].max()
                upside_pct = (recent_high - latest_15m['close']) / latest_15m['close']
                if upside_pct < 0.012: passed_filter = False

                if passed_filter and (55 <= latest_15m['rsi'] <= 70) and latest_15m['close'] > latest_15m['ema200']:
                    in_position = True
                    entry_time = latest_15m['timestamp']
                    entry_price = latest_15m['close']
                    sl_dist = 2 * latest_15m['atr']
                    sl_price = entry_price - sl_dist
                    tp_price = entry_price + (sl_dist * rr)
                    pos_size = (initial_balance * risk) / sl_dist if sl_dist > 0 else 0
                    all_trades.append({
                        'symbol': symbol, 'tier': tier, 'profit': 0, 
                        'entry_time': entry_time, 'entry_price': entry_price, 
                        'sl': sl_price, 'tp': tp_price, 'size': pos_size, 
                        'exit_time': None, 'trailing_active': False
                    })
            else:
                t = all_trades[-1]
                # Use 5m data for exit precision
                ts = latest_15m['timestamp']
                df_5m_slice = df_5m[(df_5m['timestamp'] >= ts) & (df_5m['timestamp'] < ts + pd.Timedelta(minutes=15))]
                
                for _, row_5m in df_5m_slice.iterrows():
                    # Trailing Stop: If profit > 0.8%, move SL to entry
                    current_profit_pct = (row_5m['close'] - t['entry_price']) / t['entry_price']
                    if not t['trailing_active'] and current_profit_pct >= 0.008:
                        t['sl'] = t['entry_price']
                        t['trailing_active'] = True

                    if row_5m['low'] <= t['sl']:
                        t['profit'] = (t['sl'] - t['entry_price']) * t['size']
                        t['exit_time'] = row_5m['timestamp']
                        in_position = False
                        break
                    elif row_5m['high'] >= t['tp']:
                        t['profit'] = (t['tp'] - t['entry_price']) * t['size']
                        t['exit_time'] = row_5m['timestamp']
                        in_position = False
                        break
                if not in_position: continue

    trades_df = pd.DataFrame(all_trades)
    if trades_df.empty:
        print("No trades found.")
        return

    # Calculate Metrics
    def get_stats(df_subset):
        if df_subset.empty: return [0, 0, 0, 0, 0, "0:00:00"]
        n = len(df_subset)
        wins = (df_subset['profit'] > 0).sum()
        losses = n - wins
        wr = (wins / n) * 100
        profit = df_subset['profit'].sum()
        durations = (df_subset['exit_time'] - df_subset['entry_time']).dropna()
        avg_dur = str(durations.mean()).split('.')[0] if not durations.empty else "N/A"
        return [n, wins, losses, f"{wr:.2f}%", f"${profit:.2f}", avg_dur]

    t1 = trades_df[trades_df['tier'] == 1]
    t2 = trades_df[trades_df['tier'] == 2]
    total = trades_df

    stats_t1 = get_stats(t1)
    stats_t2 = get_stats(t2)
    stats_total = get_stats(total)

    print("\n### Multi-Symbol Backtest Report (BTC, ETH, SOL, AVAX, NEAR)")
    print("| 項目 | Tier 1 (0.7+) | Tier 2 (0.6+) | 總計 (Total) |")
    print("| :--- | :--- | :--- | :--- |")
    labels = ["交易次數 (n)", "勝場數", "敗場數", "勝率 (%)", "淨獲利 ($)", "平均持倉時間"]
    for i in range(len(labels)):
        print(f"| {labels[i]} | {stats_t1[i]} | {stats_t2[i]} | {stats_total[i]} |")

    # Consecutive Losses & Max DD
    trades_df = trades_df.sort_values('entry_time')
    trades_df['is_win'] = trades_df['profit'] > 0
    consecutive = trades_df['is_win'].groupby((trades_df['is_win'] != trades_df['is_win'].shift()).cumsum()).cumcount() + 1
    max_consecutive_losses = consecutive[~trades_df['is_win']].max() if not trades_df['is_win'].all() else 0
    
    trades_df['cum_profit'] = trades_df['profit'].cumsum() + initial_balance
    max_dd_amt = (trades_df['cum_profit'].cummax() - trades_df['cum_profit']).max()
    peak = trades_df['cum_profit'].cummax()
    max_dd_pct = ((peak - trades_df['cum_profit']) / peak).max() * 100

    print(f"\n**連續虧損紀錄：**")
    print(f"- 最大連續止損次數 (Max Consecutive Losses): {max_consecutive_losses}")
    print(f"- 最大資產回撤 (Max Drawdown): ${max_dd_amt:.2f} ({max_dd_pct:.2f}%)")

if __name__ == "__main__":
    run_multi_symbol_backtest()
