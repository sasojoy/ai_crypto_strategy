import sys

path = 'src/market.py'
with open(path, 'r') as f:
    content = f.read()

new_run_strategy = """
def run_strategy():
    params = load_params()
    # Iteration 16: Dynamic Symbol Selection
    symbols = get_top_relative_strength_symbols()
    prices_rsi = {}
    current_pos_count = get_active_positions_count()
    balance = get_account_balance()

    for symbol in symbols:
        try:
            # 1. Fetch 15m and 4h data
            df = fetch_15m_data(symbol)
            df_4h = fetch_4h_data(symbol)
            if df.empty or df_4h.empty: continue

            # 2. Calculate Indicators
            df['rsi'] = calculate_rsi(df)
            df['ema_f'] = calculate_ema(df, params['ema_f'])
            df['ema_s'] = calculate_ema(df, params['ema_s'])
            df['ema_trail_long'] = calculate_ema(df, 20)
            df['ema_trail_short'] = calculate_ema(df, 10) # Sensitive for shorts
            df['atr'] = calculate_atr(df, 14)
            _, _, df['macd_hist'] = calculate_macd(df)
            df['adx'] = calculate_adx(df, 14)
            df['bb_upper'], df['bb_lower'], df['bb_bandwidth'], df['bb_percent_b'] = calculate_bollinger_bands(df, 20, params.get('bb_std', 2))

            # 4H Trend Filter
            df_4h['ema200'] = calculate_ema(df_4h, 200)
            trend_4h = "Long" if df_4h.iloc[-1]['close'] > df_4h.iloc[-1]['ema200'] else "Short"

            # Bollinger Band Squeeze (5th percentile of bandwidth)
            df['bw_min'] = df['bb_bandwidth'].rolling(100).quantile(0.05)
            is_squeezed = df.iloc[-1]['bb_bandwidth'] < df.iloc[-1]['bw_min']

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # 3. Iteration 17 & 18: Funding & OI Filters
            funding_rate = fetch_funding_rate(symbol)
            current_oi = fetch_open_interest(symbol)

            # Funding Filter: Avoid Longs if overheated (> 0.03%), Avoid Shorts if oversold (< -0.01%)
            long_funding_ok = funding_rate < 0.0003
            short_funding_ok = funding_rate > -0.0001 # 防止軋空風險

            # OI Divergence: Price Down + OI Up for Short
            oi_ok = current_oi > 0

            # 4. Entry Logic (Iteration 18: Bi-directional)
            adx_threshold_long = 18 if is_squeezed else params.get('adx_min', 25)
            adx_threshold_short = 30 # 做空需要更強動能
            
            adx_ok_long = latest['adx'] > adx_threshold_long
            adx_ok_short = latest['adx'] > adx_threshold_short

            # 5. Anomaly Detection
            detect_anomalies(symbol, df, funding_rate)

            # Long Entry Signal
            long_signal = (
                trend_4h == "Long" and
                adx_ok_long and
                long_funding_ok and
                oi_ok and
                latest['close'] > latest['ema_f'] and
                latest['ema_f'] > latest['ema_s'] and
                (is_squeezed and latest['close'] > latest['bb_upper'] or (prev['rsi'] < params['rsi_th'] and latest['rsi'] > params['rsi_th']))
            )

            # Short Entry Signal (Iteration 18)
            short_signal = (
                trend_4h == "Short" and
                adx_ok_short and
                short_funding_ok and
                oi_ok and
                latest['close'] < latest['ema_f'] and
                latest['ema_f'] < latest['ema_s'] and
                (is_squeezed and latest['close'] < latest['bb_lower'] or (prev['rsi'] > (100 - params['rsi_th']) and latest['rsi'] < (100 - params['rsi_th'])))
            )

            # Store scan results for heartbeat
            prices_rsi[symbol] = {
                'price': latest['close'],
                'rsi': latest['rsi'],
                'adx': latest['adx'],
                'trend_4h': trend_4h,
                'squeezed': is_squeezed,
                'funding': funding_rate,
                'oi': current_oi
            }

            if long_signal or short_signal:
                if current_pos_count >= 3:
                    send_telegram_msg(f"⚠️ [Iteration 18] 發現 {symbol} 進場信號，但因風控攔截 (總倉位已滿 3 倉)。")
                    continue

                side = 'LONG' if long_signal else 'SHORT'
                risk_amount = balance * 0.015
                sl_distance = params['sl_mult'] * latest['atr']
                position_size = risk_amount / sl_distance if sl_distance > 0 else 0

                target_desc = "BB Upper" if side == 'LONG' else "BB Lower"
                trail_desc = "EMA 20" if side == 'LONG' else "EMA 10 (Sensitive)"

                msg = (
                    f"🚀 [Iteration 18] 全天候對沖進場 ({side})\\n"
                    f"----------------------------\\n"
                    f"幣種：{symbol} | 價格：{latest['close']:.2f}\\n"
                    f"趨勢 (4H)：{trend_4h} | 擠壓狀態：{is_squeezed}\\n"
                    f"倉位：{position_size:.4f} (Risk 1.5%)\\n"
                    f"----------------------------\\n"
                    f"🎯 獲利計畫：\\n"
                    f"1. 觸及 {target_desc} 減倉 70% (Short) / 50% (Long) 並移至保本。\\n"
                    f"2. 啟動 {trail_desc} 追蹤止損。\\n"
                    f"3. 時間止損：3 小時內未脫離成本區則強制平倉。"
                )
                send_telegram_msg(msg)
                save_order_state(symbol, {
                    'entry_price': latest['close'],
                    'pos_size': position_size,
                    'side': side,
                    'status': 'Open',
                    'entry_time': datetime.utcnow().isoformat(),
                    'iteration': '18'
                })
        except Exception as e:
            print(f"Error in strategy execution for {symbol}: {e}")
    return prices_rsi
"""

import re
# Find the run_strategy function and replace it
pattern = r'def run_strategy\(\):.*?return prices_rsi'
new_content = re.sub(pattern, new_run_strategy, content, flags=re.DOTALL)

with open(path, 'w') as f:
    f.write(new_content)
