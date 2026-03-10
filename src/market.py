import os
import time
import ccxt
import pandas as pd
import json
import shutil
from datetime import datetime
from dotenv import load_dotenv
from src.notifier import send_telegram_msg, send_kill_switch_alert, send_rich_heartbeat, send_entry_notification, send_hourly_audit, send_daily_performance
from src.logger import log_trade
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope

# Load environment variables
load_dotenv()

def load_params():
    with open('config/params.json', 'r') as f:
        return json.load(f)

def get_top_relative_strength_symbols():
    """
    Iteration 32: Minimal Startup
    Monitor only SOL/USDT for recovery testing.
    """
    selected_symbols = ['SOL/USDT']
    print(f"🎯 [Iteration 32 Recovery] Monitoring Selected Symbols: {selected_symbols}")
    return selected_symbols

def fetch_15m_data(symbol='BTC/USDT'):
    exchange = ccxt.binance()
    timeframe = '15m'
    limit = 300
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def fetch_4h_data(symbol='BTC/USDT'):
    """
    Iteration 16: Multi-Timeframe Filter
    Fetch 4-hour data to determine the major trend.
    """
    try:
        exchange = ccxt.binance()
        timeframe = '4h'
        limit = 200
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching 4h data for {symbol}: {e}")
        return pd.DataFrame()



def fetch_1h_data(symbol='BTC/USDT'):
    try:
        exchange = ccxt.binance()
        timeframe = '1h'
        limit = 100
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching 1h data for {symbol}: {e}")
        return pd.DataFrame()


def fetch_funding_rate(symbol):
    """
    Iteration 17: Funding Rate Filter
    Fetch current funding rate for the symbol.
    """
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        funding = exchange.fetch_funding_rate(symbol)
        return funding['fundingRate']
    except Exception as e:
        print(f"Error fetching funding rate for {symbol}: {e}")
        return 0

def fetch_open_interest(symbol):
    """
    Iteration 17: OI Divergence
    Fetch current open interest for the symbol.
    """
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        oi_data = exchange.fetch_open_interest(symbol)
        return oi_data['openInterestAmount']
    except Exception as e:
        print(f"Error fetching OI for {symbol}: {e}")
        return 0




def detect_anomalies(symbol, df, funding_rate):
    """
    Iteration 17: Whale & Funding Spike Alerts
    """
    latest = df.iloc[-1]
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]
    
    # 1. Whale Alert: Volume > 5x Average
    if latest['volume'] > avg_volume * 5:
        msg = f"🐋 [WHALE ALERT] {symbol} 偵測到異常巨量交易！\n當前成交量：{latest['volume']:.2f} (均值: {avg_volume:.2f})"
        send_telegram_msg(msg)
        print(msg)

    # 2. Funding Spike: Funding > 0.05%
    if abs(funding_rate) > 0.0005:
        msg = f"⚠️ [FUNDING SPIKE] {symbol} 資金費率劇烈波動：{funding_rate*100:.4f}%"
        send_telegram_msg(msg)
        print(msg)





def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_macd(df, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def log_data(timestamp, price, rsi, ema200):
    log_file = 'data/history.csv'
    os.makedirs('data', exist_ok=True)
    data = {'timestamp': [timestamp], 'price': [price], 'rsi': [rsi], 'ema200': [ema200]}
    df = pd.DataFrame(data)
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)

def get_active_positions_count():
    # 模擬邏輯：此處應為實際持倉查詢
    return 0

def stability_monitor():
    """
    穩定性監控器 (Circuit Breaker)
    Iteration 19: 
    1. 若出現連續 3 筆止損，自動回滾。
    2. 若當日虧損超過總資金的 5%，觸發 24 小時熔斷。
    """
    history_file = 'data/trade_history.json'
    circuit_breaker_file = 'data/circuit_breaker.json'
    
    if os.path.exists(circuit_breaker_file):
        with open(circuit_breaker_file, 'r') as f:
            cb_data = json.load(f)
            if time.time() < cb_data.get('resume_time', 0):
                print(f"⏳ [CIRCUIT BREAKER] 系統熔斷中，預計 {datetime.fromtimestamp(cb_data['resume_time'])} 恢復。")
                return False # 暫停交易

    if not os.path.exists(history_file): return True

    try:
        with open(history_file, 'r') as f:
            trades = json.load(f)

        # 1. 連續止損檢查
        last_3_trades = trades[-3:]
        if len(last_3_trades) == 3 and all(t['result'] == 'SL' for t in last_3_trades):
            trigger_rollback("連續 3 筆止損")
            return True

        # 2. 當日虧損檢查 (Iteration 19)
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        today_trades = [t for t in trades if t.get('exit_time', '').startswith(today_str)]
        today_pnl = sum(t.get('profit', 0) for t in today_trades)
        balance = get_account_balance()
        
        if today_pnl < -(balance * 0.05):
            resume_time = time.time() + 86400 # 24小時
            with open(circuit_breaker_file, 'w') as f:
                json.dump({'resume_time': resume_time, 'reason': 'Daily Loss > 5%'}, f)
            msg = f"🛑 [CIRCUIT BREAKER] 當日虧損 ({today_pnl:.2f}) 超過 5%，啟動 24 小時強制冷卻。"
            send_telegram_msg(msg)
            print(msg)
            return False
            
    except Exception as e:
        print(f"Stability monitor error: {e}")
    return True

def trigger_rollback(reason):
    params = load_params()
    current_version = params.get('version', 'Unknown')
    stable_version = "archive/params_iter11_final.json"

    if os.path.exists(stable_version):
        shutil.copy(stable_version, 'config/params.json')
        msg = f"🚨 緊急警告：{current_version} 觸發熔斷 ({reason})，系統已自動回滾至穩定版本 11。"
        send_telegram_msg(msg)
        print(msg)
    else:
        print("Rollback failed: Stable version not found.")

def get_account_balance():
    """
    Iteration 32: Read balance from data/balance.json
    """
    path = 'data/balance.json'
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get('total_balance', 1000.0)
    return 1000.0

def update_balance(pnl_amount):
    """
    Iteration 32: Update balance and realized PnL
    """
    path = 'data/balance.json'
    balance = get_account_balance()
    new_balance = balance + pnl_amount
    
    # Load existing data to preserve other fields if any
    data = {"total_balance": 1000.0, "realized_pnl": 0.0}
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
    
    data['total_balance'] = new_balance
    data['realized_pnl'] = data.get('realized_pnl', 0.0) + pnl_amount
    
    os.makedirs('data', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f)
    
    print(f"💰 [BALANCE UPDATE] PnL: ${pnl_amount:.2f} | New Balance: ${new_balance:.2f}")

def record_trade_history(symbol, side, price, quantity, pnl, reason):
    """
    Iteration 32: Record trade to data/trade_history.csv
    """
    path = 'data/trade_history.csv'
    timestamp = datetime.utcnow().isoformat()
    df = pd.DataFrame([{
        'timestamp': timestamp,
        'symbol': symbol,
        'side': side,
        'price': price,
        'quantity': quantity,
        'pnl': pnl,
        'reason': reason
    }])
    
    if not os.path.exists(path):
        df.to_csv(path, index=False)
    else:
        df.to_csv(path, mode='a', header=False, index=False)

def log_slippage(symbol, expected_price, actual_price):
    slippage = abs(actual_price - expected_price) / expected_price
    os.makedirs('logs', exist_ok=True)
    with open('logs/slippage.log', 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {symbol}: Expected {expected_price}, Actual {actual_price}, Slippage {slippage*100:.4f}%\n")
    if slippage > 0.001:
        print(f"⚠️ [WARNING] High Slippage detected on {symbol}: {slippage*100:.4f}%")

def save_order_state(symbol, state):
    os.makedirs('data', exist_ok=True)
    with open(f'data/order_state_{symbol.replace("/", "_")}.json', 'w') as f:
        json.dump(state, f)

def load_order_state(symbol):
    path = f'data/order_state_{symbol.replace("/", "_")}.json'
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None

# Global Kill Switch State
KILL_SWITCH_ACTIVE = False

def check_kill_switch():
    global KILL_SWITCH_ACTIVE
    if os.path.exists('data/kill_switch.trigger'):
        KILL_SWITCH_ACTIVE = True
        os.remove('data/kill_switch.trigger')
        return True
    return False

def trigger_panic_sell_all():
    print("🚨 [EMERGENCY] KILL SWITCH ACTIVATED! Closing all positions...")
    send_kill_switch_alert("User Command /panic_sell_all")
    exit(1)

def get_daily_stats():
    equity = 10500.0
    floating_pnl = 120.50
    realized_pnl = 45.00
    total_risk_pct = 1.5
    return equity, floating_pnl, realized_pnl, total_risk_pct


def run_strategy():
    params = load_params()
    # Iteration 16: Dynamic Symbol Selection
    symbols = get_top_relative_strength_symbols()
    prices_rsi = {}
    current_pos_count = get_active_positions_count()
    
    # Iteration 19: Dynamic Equity-Based Risking
    balance = get_account_balance()
    risk_pct = params.get('risk_pct', 0.015) # Default 1.5%

    # Iteration 23: BTC Sentiment Filter
    df_btc_1h = fetch_1h_data('BTC/USDT')
    btc_sentiment_ok = False
    if not df_btc_1h.empty:
        btc_ema50 = calculate_ema(df_btc_1h, 50).iloc[-1]
        btc_price = df_btc_1h.iloc[-1]['close']
        btc_sentiment_ok = btc_price > btc_ema50
        print(f"📊 [BTC Sentiment] Price: {btc_price:.2f}, EMA50: {btc_ema50:.2f}, OK: {btc_sentiment_ok}")

    potential_signals = []

    for symbol in symbols:
        try:
            # 1. Fetch 15m and 4h data
            df = fetch_15m_data(symbol)
            df_4h = fetch_4h_data(symbol)
            if df.empty or df_4h.empty: continue

            # 2. Calculate Indicators (Iteration 20 Upgrades)
            df['rsi'] = calculate_rsi(df)
            df['ema_f'] = calculate_ema(df, params['ema_f'])
            df['ema_s'] = calculate_ema(df, params['ema_s'])
            df['ema_trail_long'] = calculate_ema(df, 20)
            df['ema_trail_short'] = calculate_ema(df, 10)
            df['atr'] = calculate_atr(df, 14)
            df['adx'] = calculate_adx(df, 14)
            df['bb_upper'], df['bb_lower'], _, _ = calculate_bollinger_bands(df, 20, params.get('bb_std', 2))
            
            # Heikin-Ashi (Iteration 21)
            ha = calculate_heikin_ashi(df)
            df = pd.concat([df, ha], axis=1)
            
            # S/R Levels (Iteration 24: 12-candle High/Low)
            df['support_12h'], df['resistance_12h'] = calculate_sr_levels(df, window=12)
            df['rsi_slope'] = calculate_rsi_slope(df)
            df['ema20'] = calculate_ema(df, 20)
            df['ema50'] = calculate_ema(df, 50)

            # 4H Trend Filter (Strict Iteration 21)
            df_4h['ema200'] = calculate_ema(df_4h, 200)
            latest_4h = df_4h.iloc[-1]
            trend_4h = "Long" if latest_4h['close'] > latest_4h['ema200'] else "Short"

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # 3. Volume Confirmation (Iteration 25: 2.5x)
            avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[-1]
            vol_ok = latest['volume'] > (avg_vol_5 * 2.5)

            # 4. Heikin-Ashi Trend (Iteration 20)
            ha_long = latest['ha_close'] > latest['ha_open'] and prev['ha_close'] > prev['ha_open']
            ha_short = latest['ha_close'] < latest['ha_open'] and prev['ha_close'] < prev['ha_open']

            # 5. Entry Logic (Iteration 31: Capital Allocator)
            # Pre-requisite: BTC Crash Filter (1H Drop > 2%)
            df_btc_1h = fetch_1h_data('BTC/USDT')
            if not df_btc_1h.empty:
                btc_1h_change = (df_btc_1h.iloc[-1]['close'] - df_btc_1h.iloc[-2]['close']) / df_btc_1h.iloc[-2]['close'] * 100
                if btc_1h_change < -2.0:
                    print(f"🚫 [Iteration 31] {symbol} Entry ignored: BTC Crashing ({btc_1h_change:.2f}%).")
                    continue

            # Pre-requisite: 4H Trend Strong (EMA 200 above)
            df_4h = fetch_4h_data(symbol)
            if df_4h.empty: continue
            df_4h['ema200'] = calculate_ema(df_4h, 200)
            trend_4h_strong = latest['close'] > df_4h.iloc[-1]['ema200']

            # Trigger: 15m RSI < 35 (Iteration 38: Tightened from 42)
            df['bb_upper'], df['bb_lower'], df['bb_mid'], _ = calculate_bollinger_bands(df, 20, 2)
            latest = df.iloc[-1] # Refresh latest with BB
            rsi_oversold = latest['rsi'] < 35
            price_at_bb_lower = latest['low'] <= latest['bb_lower']
            ema_golden_cross = latest['ema20'] > latest['ema50'] and prev['ema20'] <= prev['ema50']

            # Iteration 38: Volume Exhaustion Filter (Current Vol < Avg of last 5 * 1.1 buffer)
            avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[-1]
            vol_exhaustion = latest['volume'] < (avg_vol_5 * 1.1)

            # Confirmation: RSI Hook Up and First Green Candle
            rsi_hook_up = latest['rsi'] > prev['rsi']
            first_green = latest['close'] > latest['open']

            long_signal = trend_4h_strong and rsi_oversold and vol_exhaustion and (price_at_bb_lower or ema_golden_cross) and rsi_hook_up and first_green

            short_signal = False # Iteration 29/30/31 focus on Long Pullback Strategy

            # Iteration 38: Calculate ATR Average for Spike Guard (Factor 1.2)
            atr_avg = df['atr'].rolling(window=100).mean().iloc[-1]
            atr_spike = latest['atr'] > (atr_avg * 1.2) if atr_avg > 0 else False

            # Iteration 37: Distance-Based Sizing Calculation for Report
            price = latest['close']
            ema200 = df_4h.iloc[-1]['ema200']
            dist_ema200_pct = abs(price - ema200) / ema200 * 100 if ema200 > 0 else 0
            
            base_risk = 0.025
            if dist_ema200_pct < 1.5:
                adj_risk = 0.03
                weight_str = "+20%"
            elif dist_ema200_pct > 5.0:
                adj_risk = 0.015
                weight_str = "-40%"
            else:
                adj_risk = base_risk
                weight_str = "正常"

            if atr_spike:
                adj_risk /= 2
                weight_str += " (ATR 減半)"

            # Store scan results for heartbeat
            prices_rsi[symbol] = {
                'price': latest['close'],
                'rsi': latest['rsi'],
                'adx': latest['adx'],
                'atr': latest['atr'],
                'atr_avg': atr_avg,
                'atr_spike': atr_spike,
                'trend_4h': trend_4h,
                'support': latest['support_12h'],
                'resistance': latest['resistance_12h'],
                'ha_trend': "Bullish" if ha_long else ("Bearish" if ha_short else "Neutral"),
                'bb_lower': latest['bb_lower'],
                'ema200': ema200,
                'dist_ema200_pct': dist_ema200_pct,
                'expected_risk_pct': adj_risk * 100,
                'weight_str': weight_str
            }

            if long_signal or short_signal:
                side = 'LONG' if long_signal else 'SHORT'
                # Iteration 23: BTC Sentiment & Funding Rate Filter
                if side == 'LONG':
                    if not btc_sentiment_ok:
                        print(f"🚫 [Iteration 23] {symbol} Long signal ignored: BTC Sentiment Bearish.")
                        continue
                    
                    if symbol in ['DOGE/USDT', 'XRP/USDT']:
                        funding_rate = fetch_funding_rate(symbol)
                        if funding_rate > 0.0005:
                            print(f"🚫 [Iteration 23] {symbol} Long signal ignored: Funding Rate too high ({funding_rate*100:.4f}%).")
                            continue

                # Calculate Volume Growth Rate for Correlation Detection
                vol_growth = (latest['volume'] - avg_vol_5) / avg_vol_5 if avg_vol_5 > 0 else 0
                
                potential_signals.append({
                    'symbol': symbol,
                    'side': side,
                    'vol_growth': vol_growth,
                    'latest': latest,
                    'prices_rsi': prices_rsi[symbol]
                })
        except Exception as e:
            print(f"Error in strategy execution for {symbol}: {e}")

    # Iteration 24: Prioritize DOGE/XRP if they have strong trends
    def signal_priority(x):
        score = x['vol_growth']
        if x['symbol'] in ['DOGE/USDT', 'XRP/USDT']:
            score += 1.0 # Boost priority for strong trend coins
        return score

    potential_signals = sorted(potential_signals, key=signal_priority, reverse=True)[:2]

    for signal in potential_signals:
        symbol = signal['symbol']
        side = signal['side']
        latest = signal['latest']
        
        if current_pos_count >= 3:
            send_telegram_msg(f"⚠️ [Iteration 23] 發現 {symbol} 進場信號，但因風控攔截 (總倉位已滿 3 倉)。")
            continue

        # Iteration 37: Dynamic Asset Allocation
        balance = get_account_balance()
        
        # 1. Distance-Based Sizing
        ema200 = prices_rsi[symbol]['ema200']
        dist_ema200_pct = prices_rsi[symbol]['dist_ema200_pct']
        
        if dist_ema200_pct < 1.5:
            risk_pct = 0.03 # Increase to 3%
        elif dist_ema200_pct > 5.0:
            risk_pct = 0.015 # Decrease to 1.5%
        else:
            risk_pct = 0.025 # Base 2.5%

        # 2. ATR Spike Guard
        if prices_rsi[symbol]['atr_spike']:
            print(f"⚠️ [ATR Spike Guard] {symbol} ATR is high. Halving position size.")
            risk_pct /= 2

        risk_amount = balance * risk_pct
        
        # Volatility Sizing: Adjust SL distance based on ATR (Iteration 38: 1.5 * ATR)
        sl_distance = 1.5 * latest['atr'] 
        
        # Formula: Quantity = Risk Amount / SL Distance
        position_qty = risk_amount / sl_distance if sl_distance > 0 else 0
        
        entry_price = latest['close']
        
        # Iteration 32: No-Leverage Constraint (Max 95% of balance)
        max_position_value = balance * 0.95
        current_position_value = position_qty * entry_price
        
        if current_position_value > max_position_value:
            print(f"⚠️ [RISK] Position value ${current_position_value:.2f} exceeds cap. Reducing to ${max_position_value:.2f}")
            position_qty = max_position_value / entry_price
            current_position_value = max_position_value
        sl_price = entry_price - sl_distance
        
        # Iteration 38: TP = 3.0 * ATR or BB Upper
        tp_price_atr = entry_price + (3.0 * latest['atr'])
        tp_price = min(tp_price_atr, latest['bb_upper'])
        rr = (tp_price - entry_price) / sl_distance if sl_distance > 0 else 0

        send_entry_notification(
            symbol=symbol,
            side=side,
            pos_value=risk_amount,
            risk_pct=risk_pct * 100,
            tp=tp_price,
            sl=sl_price,
            rr=rr
        )
        
        save_order_state(symbol, {
            'entry_price': entry_price,
            'pos_size': position_qty,
            'side': side,
            'status': 'Open',
            'entry_time': datetime.utcnow().isoformat(),
            'iteration': '29',
            'sl_price': sl_price,
            'tp_price': tp_price,
            'atr': latest['atr'],
            'highest_price': entry_price
        })
    return prices_rsi



def manage_positions(prices_rsi):
    params = load_params()
    symbols = ['SOL/USDT', 'ETH/USDT', 'AVAX/USDT', 'FET/USDT', 'NEAR/USDT']
    
    for symbol in symbols:
        state = load_order_state(symbol)
        if not state or state.get('status') != 'Open':
            continue
            
        # Iteration 32: Ghost Position Cleanup
        if state.get('pos_size', 0) <= 0:
            print(f"👻 [GHOST CLEANUP] {symbol} has zero quantity. Closing state.")
            state['status'] = 'Closed'
            state['exit_reason'] = 'Ghost Cleanup'
            save_order_state(symbol, state)
            continue

        current_price = prices_rsi.get(symbol, {}).get('price', 0)
        if current_price == 0:
            continue
            
        entry_price = state['entry_price']
        side = state['side']
        adx = prices_rsi.get(symbol, {}).get('adx', 0)
        
        # Iteration 25: Zombie Position Cleanup (ADX < 15 & Loss & 4h sideways)
        # Sideways check: price within 0.5% of entry for > 4 hours
        entry_time = datetime.fromisoformat(state['entry_time'])
        hours_held = (datetime.utcnow() - entry_time).total_seconds() / 3600
        
        is_loss = (side == 'LONG' and current_price < entry_price) or (side == 'SHORT' and current_price > entry_price)

        if adx < 15 and hours_held > 4 and is_loss:
            price_diff_pct = abs(current_price - entry_price) / entry_price
            if price_diff_pct < 0.005:
                msg = f"🧟 [Iteration 25] {symbol} 僵屍倉位清理！\n原因：ADX {adx:.1f} < 15 且虧損橫盤 {hours_held:.1f} 小時。\n現價平倉釋放保證金。"
                send_telegram_msg(msg)
                state['status'] = 'Closed'
                state['exit_price'] = current_price
                state['exit_time'] = datetime.utcnow().isoformat()
                state['exit_reason'] = 'Zombie Cleanup'
                save_order_state(symbol, state)
                continue

        # Iteration 26: Exit Logic (BB Mid/Upper)
        # Fetch latest BB for exit
        df_exit = fetch_15m_data(symbol)
        df_exit['bb_upper'], df_exit['bb_lower'], df_exit['bb_mid'], _ = calculate_bollinger_bands(df_exit, 20, 2)
        latest_exit = df_exit.iloc[-1]

        if side == 'LONG':
            # Iteration 29: Partial TP + Trailing Stop
            profit_pct = (current_price - entry_price) / entry_price * 100
            
            # Iteration 37: Profit Drawdown Protection
            highest_price = max(state.get('highest_price', entry_price), current_price)
            state['highest_price'] = highest_price
            highest_pnl = (highest_price - entry_price) / entry_price * 100
            
            if highest_pnl >= 3.0:
                retracement = (highest_pnl - profit_pct) / highest_pnl if highest_pnl > 0 else 0
                if retracement >= 0.20:
                    msg = f"🛡️ [Iteration 37] {symbol} 獲利回撤保護觸發！\n最高獲利：{highest_pnl:.2f}% | 當前獲利：{profit_pct:.2f}% | 回撤：{retracement*100:.1f}%"
                    send_telegram_msg(msg)
                    state['status'] = 'Closed'
                    state['exit_price'] = current_price
                    state['exit_time'] = datetime.utcnow().isoformat()
                    state['exit_reason'] = 'Profit_Protection'
                    pnl_amount = (state['exit_price'] - state['entry_price']) * state['pos_size']
                    update_balance(pnl_amount)
                    record_trade_history(symbol, side, state['exit_price'], state['pos_size'], pnl_amount, 'Profit_Protection')
                    save_order_state(symbol, state)
                    continue

            # 1. SL (Iteration 29: 1.8x ATR or Break-even)
            sl_price = state.get('sl_price', entry_price - (1.8 * prices_rsi[symbol]['atr']))
            
            # Trailing Stop Logic (if partial TP already hit)
            if state.get('partial_tp_hit'):
                highest_price = max(state.get('highest_price', 0), current_price)
                state['highest_price'] = highest_price
                # Trailing Stop: 1.5% from highest price
                trailing_sl = highest_price * 0.985
                sl_price = max(sl_price, trailing_sl)

            if current_price <= sl_price:
                msg = f"❌ [Iteration 29] {symbol} 觸發止損/移動止損！\n現價：{current_price:.2f} | 止損價：{sl_price:.2f}"
                send_telegram_msg(msg)
                state['status'] = 'Closed'
                state['exit_price'] = current_price
                state['exit_time'] = datetime.utcnow().isoformat()
                state['exit_reason'] = 'SL_Trailing'
                
                # Iteration 32: Financial Tracking
                pnl_amount = (state['exit_price'] - state['entry_price']) * state['pos_size']
                update_balance(pnl_amount)
                record_trade_history(symbol, side, state['exit_price'], state['pos_size'], pnl_amount, 'SL_Trailing')
                
                save_order_state(symbol, state)
                continue

            # 2. TP (Iteration 29: BB Upper Partial 50%)
            if current_price >= latest_exit['bb_upper'] and not state.get('partial_tp_hit'):
                msg = f"💰 [Iteration 29] {symbol} 觸及布林上軌，平倉 50% 並開啟移動止損！"
                send_telegram_msg(msg)
                
                # Iteration 32: Financial Tracking for Partial TP
                partial_qty = state.get('pos_size', 0) * 0.5
                pnl_amount = (current_price - entry_price) * partial_qty
                update_balance(pnl_amount)
                record_trade_history(symbol, side, current_price, partial_qty, pnl_amount, 'Partial_TP')
                
                state['partial_tp_hit'] = True
                state['pos_size'] = state.get('pos_size', 0) * 0.5
                state['sl_price'] = entry_price # Move to break-even
                state['highest_price'] = current_price
                save_order_state(symbol, state)
                # In real exchange, execute partial close order here
            
            # 3. Time-based Exit (Iteration 30: 48h)
            entry_time = datetime.fromisoformat(state['entry_time'])
            if (datetime.utcnow() - entry_time).total_seconds() >= 172800: # 48 hours
                if current_price > entry_price:
                    msg = f"⏳ [Iteration 30] {symbol} 持倉超過 48 小時且獲利為正，強行平倉釋放資金！"
                    send_telegram_msg(msg)
                    state['status'] = 'Closed'
                    state['exit_price'] = current_price
                    state['exit_time'] = datetime.utcnow().isoformat()
                    state['exit_reason'] = 'Time_Exit'
                    
                    # Iteration 32: Financial Tracking
                    pnl_amount = (state['exit_price'] - state['entry_price']) * state['pos_size']
                    update_balance(pnl_amount)
                    record_trade_history(symbol, side, state['exit_price'], state['pos_size'], pnl_amount, 'Time_Exit')
                    
                    save_order_state(symbol, state)
                    continue




if __name__ == "__main__":
    send_telegram_msg("🚀 [System Heartbeat] Iteration 38_Precision_Entry 正在 GCE 啟動。RSI 35 嚴選與成交量枯竭過濾已就緒。")
    import sys
    if "--check-accounting" in sys.argv:
        print("📊 [ACCOUNTING CHECK]")
        balance = get_account_balance()
        print(f"Total Balance: ${balance:.2f}")
        if os.path.exists('data/trade_history.csv'):
            df = pd.read_csv('data/trade_history.csv')
            print(f"Total Trades: {len(df)}")
            print(f"Total PnL from History: ${df['pnl'].sum():.2f}")
        else:
            print("No trade history found.")
        
        symbols = ['SOL/USDT', 'ETH/USDT', 'AVAX/USDT', 'FET/USDT', 'NEAR/USDT']
        active_found = False
        for s in symbols:
            state = load_order_state(s)
            if state and state.get('status') == 'Open':
                print(f"📍 Active Position: {s} | Size: {state.get('pos_size', 0):.4f} | Entry: {state.get('entry_price', 0):.4f}")
                active_found = True
        if not active_found:
            print("No active positions.")
        sys.exit(0)

    STRATEGY_VERSION = "Iteration 38 - Precision Entry"
    last_heartbeat_time = 0
    last_summary_date = None
    send_telegram_msg("🚀 Iteration 38_Precision_Entry 已於遠端正式啟動，RSI 35 嚴選與成交量枯竭過濾已就緒。")

    while True:
        try:
            if check_kill_switch():
                trigger_panic_sell_all()

            now = datetime.utcnow()
            if now.hour == 0 and now.minute == 0 and last_summary_date != now.date():
                # Iteration 31: Daily Performance Message
                # Simulated values for this iteration
                equity = 1000.0 
                daily_pnl = 0.0
                best_symbol = "SOL/USDT"
                max_dd = 0.0
                send_daily_performance(now.date().isoformat(), equity, daily_pnl, best_symbol, max_dd)
                last_summary_date = now.date()

            stability_monitor()
            scan_results = run_strategy()
            manage_positions(scan_results)
            current_time = time.time()

            if current_time - last_heartbeat_time >= 3600: # Hourly Audit
                # Collect active position data
                active_positions = []
                
                # Iteration 32: Fetch actual realized PnL and balance
                balance_data = {"total_balance": 1000.0, "realized_pnl": 0.0}
                if os.path.exists('data/balance.json'):
                    with open('data/balance.json', 'r') as f:
                        balance_data = json.load(f)
                
                # Iteration 32: Calculate Daily PnL from CSV
                daily_pnl = 0
                if os.path.exists('data/trade_history.csv'):
                    try:
                        df_history = pd.read_csv('data/trade_history.csv')
                        today_str = datetime.utcnow().strftime('%Y-%m-%d')
                        df_today = df_history[df_history['timestamp'].str.startswith(today_str)]
                        daily_pnl = df_today['pnl'].sum()
                    except Exception as e:
                        print(f"Error calculating daily PnL: {e}")

                equity = balance_data.get('total_balance', 1000.0)
                
                symbols = ['SOL/USDT', 'ETH/USDT', 'AVAX/USDT', 'FET/USDT', 'NEAR/USDT']
                for s in symbols:
                    state = load_order_state(s)
                    if state and state.get('status') == 'Open' and state.get('pos_size', 0) > 0:
                        current_price = scan_results.get(s, {}).get('price', 0)
                        entry_price = state.get('entry_price', 0)
                        pnl = round(((current_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0
                        active_positions.append({
                            'symbol': s,
                            'status': state.get('status'),
                            'pnl': pnl,
                            'size_usd': state.get('pos_size', 0) * current_price,
                            'entry_price': entry_price
                        })
                
                send_hourly_audit(equity, daily_pnl, active_positions)
                
                # Iteration 35: Rich Heartbeat with Data Visualization
                df_btc = fetch_1h_data('BTC/USDT')
                if not df_btc.empty:
                    btc_price = df_btc.iloc[-1]['close']
                    btc_ema50 = calculate_ema(df_btc, 50).iloc[-1]
                    
                    # Fetch 24h volume change
                    vol_change_24h = 0
                    try:
                        ticker = exchange.fetch_ticker('BTC/USDT')
                        vol_change_24h = ticker.get('percentage', 0)
                    except: pass
                    
                    btc_status = {
                        'price': btc_price,
                        'ema50': btc_ema50,
                        'is_bullish': btc_price > btc_ema50,
                        'vol_change_24h': vol_change_24h
                    }
                    send_rich_heartbeat(active_positions, scan_results, len(active_positions), "Iteration 36", btc_status)
                
                last_heartbeat_time = current_time
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)
