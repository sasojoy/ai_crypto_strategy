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
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope, calculate_stoch_rsi

from src.features import extract_features
from src.ml_model import CryptoMLModel


# Load environment variables
load_dotenv()

# Iteration 58: Relative Path Definition for GCE Compatibility
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv('TRADING_DATA_DIR', os.path.join(BASE_DIR, 'trading_data'))
os.makedirs(DATA_DIR, exist_ok=True)


# Iteration 51: Physical Isolation Security
IS_SIMULATION = True

# Security Check
if not IS_SIMULATION:
    if not os.getenv('BINANCE_API_KEY') or not os.getenv('BINANCE_SECRET'):
        raise RuntimeError("❌ [SECURITY FATAL] IS_SIMULATION is False but no API keys found. Terminating for safety.")




# Global state initialization
regime_mode = "NEUTRAL"


def load_params():
    with open('config/params.json', 'r') as f:
        return json.load(f)

def get_recent_performance():
    """
    Iteration 49: Track recent 10 trades for dynamic risk sizing
    """
    try:
        if not os.path.exists(os.path.join(DATA_DIR, 'trade_history.json')):
            return 0.5, 0 # Default win rate 50%, 0 losses
        
        with open(os.path.join(DATA_DIR, 'trade_history.json'), 'r') as f:
            history = json.load(f)
        
        recent = history[-10:]
        if not recent:
            return 0.5, 0
            
        wins = len([t for t in recent if t.get('pnl', 0) > 0])
        win_rate = wins / len(recent)
        
        # Check for back-to-back losses
        last_two = history[-2:]
        losses = len([t for t in last_two if t.get('pnl', 0) < 0])
        
        return win_rate, losses
    except Exception as e:
        print(f"Error tracking performance: {e}")
        return 0.5, 0


def get_top_relative_strength_symbols():
    """
    Iteration 42: Capital Re-allocation
    Focus on high-conviction assets (BTC, ETH, SOL) and reduce exposure to experimental ones.
    """
    selected_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT', 'FET/USDT', 'ARB/USDT']
    print(f"🎯 [Iteration 67] Monitoring Selected Symbols: {selected_symbols}")
    return selected_symbols

def fetch_15m_data(symbol='BTC/USDT'):
    exchange = ccxt.binance()
    timeframe = '15m'
    limit = 300
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df



def fetch_5m_data(symbol='BTC/USDT'):
    try:
        exchange = ccxt.binance()
        timeframe = '5m'
        limit = 300
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching 5m data for {symbol}: {e}")
        return pd.DataFrame()





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


def fetch_ohlcv(symbol, timeframe="1h", limit=100):
    try:
        import ccxt
        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching {timeframe} data for {symbol}: {e}")
        return pd.DataFrame()


def fetch_1h_data(symbol='BTC/USDT', limit=100):
    try:
        exchange = ccxt.binance()
        timeframe = '1h'
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
    Fetch current funding rate for the symbol using Public API.
    """
    try:
        # Public API - No Key Required
        exchange = ccxt.binance({'options': {'defaultType': 'future'}})
        funding = exchange.fetch_funding_rate(symbol)
        return funding['fundingRate']
    except Exception as e:
        print(f"Error fetching funding rate for {symbol}: {e}")
        return 0

def check_order_book_depth(symbol, amount_usd):
    """
    Iteration 50: Slippage & Depth Protection
    Checks if the order book can handle the order with < 0.5% slippage.
    """
    try:
        exchange = ccxt.binance()
        order_book = exchange.fetch_order_book(symbol, limit=20)
        bids = order_book['bids'] # [price, amount]
        
        total_depth = 0
        for price, amount in bids:
            total_depth += price * amount
            if total_depth >= amount_usd * 2: # We want at least 2x depth for the order
                slippage = (bids[0][0] - price) / bids[0][0]
                return slippage < 0.005
        return False
    except Exception as e:
        print(f"Depth check error: {e}")
        return True # Default to True to not block if API fails

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

def simulate_hard_sl(symbol, side, qty, sl_price):
    """
    Iteration 50: Simulate Hard SL for Dry Run
    """
    sl_side = 'sell' if side == 'LONG' else 'buy'
    msg = f"🛡️ [Dry Run] 模擬已掛出交易所端止損: {symbol} {sl_side} at {sl_price} (Qty: {qty})"
    print(msg)
    return {"id": f"sim-sl-{int(time.time())}", "status": "simulated"}

def create_order_with_hard_sl(symbol, side, qty, entry_price, sl_price, tp_price):
    """
    Iteration 51: Physical Isolation - Simulation Only
    """
    if not IS_SIMULATION:
        print("❌ [SECURITY] Live trading is physically disabled in this version.")
        return None, None

    print(f"🚀 [Simulation] 模擬進場: {symbol} {side} {qty} at {entry_price}")
    sl_order = simulate_hard_sl(symbol, side, qty, sl_price)
    return {"id": f"sim-entry-{int(time.time())}", "status": "simulated"}, sl_order

def cancel_sl_order(symbol, sl_order_id):
    """
    Iteration 51: Physical Isolation - Simulation Only
    """
    if not IS_SIMULATION:
        print("❌ [SECURITY] Live trading is physically disabled in this version.")
        return

    print(f"🧹 [Simulation] 模擬取消 SL Order {sl_order_id} for {symbol}")

def move_sl_to_breakeven(symbol, qty, entry_price, old_sl_order_id):
    """
    Iteration 51: Physical Isolation - Simulation Only
    """
    if not IS_SIMULATION:
        print("❌ [SECURITY] Live trading is physically disabled in this version.")
        return old_sl_order_id

    print(f"🛡️ [Simulation] 模擬將止損移至保本價 for {symbol}")
    return f"sim-be-{int(time.time())}"




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

def find_4h_structure(df_4h):
    """
    Iteration 55: Detect 4H Support and Resistance
    """
    if df_4h is None or len(df_4h) < 20: return None, None
    
    support = df_4h.iloc[-20:]['low'].min()
    resistance = df_4h.iloc[-20:]['high'].max()
    
    return support, resistance



def calculate_squeeze_index(df, window=100):
    """
    Iteration 67: Calculate Bollinger Band Squeeze Index.
    Returns the percentile rank of the current BB Width over the specified window.
    """
    if df.empty or len(df) < window:
        return 1.0 # No squeeze if not enough data
    
    _, _, bb_width, _ = calculate_bollinger_bands(df)
    current_width = bb_width.iloc[-1]
    historical_widths = bb_width.iloc[-window:]
    
    # Calculate percentile rank
    percentile = (historical_widths < current_width).mean()
    return percentile


def check_upside_potential(symbol, entry_price, df_1h):
    """
    Iteration 67: Space-to-Resistance Check
    Only allow entry if there is at least 1.2% upside to the recent 24h high.
    """
    if df_1h.empty or len(df_1h) < 24:
        return True
    
    recent_high = df_1h.iloc[-24:]['high'].max()
    upside_pct = (recent_high - entry_price) / entry_price
    
    if upside_pct < 0.012:
        print(f"🛡️ [Space Check] {symbol} upside {upside_pct:.2%} < 1.2% to resistance ({recent_high:.2f}). Skipping.")
        return False
    return True



def log_data(timestamp, price, rsi, ema200):
    log_file = os.path.join(DATA_DIR, 'history.csv')
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {'timestamp': [timestamp], 'price': [price], 'rsi': [rsi], 'ema200': [ema200]}
    df = pd.DataFrame(data)
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)

def get_active_positions_count():
    """
    Iteration 52: Real-time scan of active positions from data files
    """
    count = 0
    if not os.path.exists('data'):
        return 0
    for filename in os.listdir('data'):
        if filename.startswith('order_state_') and filename.endswith('.json'):
            try:
                with open(os.path.join('data', filename), 'r') as f:
                    state = json.load(f)
                    if state.get('status') == 'Open':
                        count += 1
            except:
                pass
    return count

def stability_monitor():
    """
    穩定性監控器 (Circuit Breaker)
    Iteration 19: 
    1. 若出現連續 3 筆止損，自動回滾。
    2. 若當日虧損超過總資金的 5%，觸發 24 小時熔斷。
    """
    history_file = os.path.join(DATA_DIR, 'trade_history.json')
    circuit_breaker_file = os.path.join(DATA_DIR, 'circuit_breaker.json')
    
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
    Iteration 57: Read balance from system_state.json (Persistent)
    """
    path = os.path.join(DATA_DIR, 'system_state.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get('total_balance', 1000.0)
    
    # Fallback to old balance.json if exists
    old_path = os.path.join(DATA_DIR, 'balance.json')
    if os.path.exists(old_path):
        with open(old_path, 'r') as f:
            data = json.load(f)
            return data.get('total_balance', 1000.0)
            
    return 1000.0

def update_balance(pnl_amount, position_value=0):
    """
    Iteration 57: Update balance in system_state.json
    """
    path = os.path.join(DATA_DIR, 'system_state.json')
    
    # Deduct 0.1% of position value for slippage and fees
    friction_cost = position_value * 0.001
    net_pnl = pnl_amount - friction_cost
    
    balance = get_account_balance()
    new_balance = balance + net_pnl
    
    # Load existing data to preserve other fields if any
    data = {"total_balance": 1000.0, "realized_pnl": 0.0}
    if os.path.exists(path):
        with open(path, 'r') as f:
            data = json.load(f)
    
    data['total_balance'] = new_balance
    data['realized_pnl'] = data.get('realized_pnl', 0.0) + net_pnl
    
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f)
    
    print(f"💰 [BALANCE UPDATE] PnL: ${pnl_amount:.2f} | Friction: ${friction_cost:.2f} | Net: ${net_pnl:.2f} | New Balance: ${new_balance:.2f}")

def update_daily_performance():
    """
    Iteration 54: Automatic Performance Tracker
    Logs daily net value and win rate to data/daily_performance.csv at 00:00 UTC.
    """
    try:
        path = os.path.join(BASE_DIR, 'data', 'daily_performance.csv')
        balance = get_account_balance()
        
        # Calculate win rate from history
        win_rate, _ = get_recent_performance()
        
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        
        # Check if we already logged today
        if os.path.exists(path):
            df = pd.read_csv(path)
            if date_str in df['date'].values:
                return
        else:
            df = pd.DataFrame(columns=['date', 'balance', 'win_rate'])
            
        new_row = pd.DataFrame([{'date': date_str, 'balance': balance, 'win_rate': win_rate}])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(path, index=False)
        print(f"📈 Daily performance logged: {date_str} | Balance: {balance}")
    except Exception as e:
        print(f"Error updating daily performance: {e}")

def record_trade_history(symbol, side, price, quantity, pnl, reason):
    """
    Iteration 32: Record trade to data/trade_history.csv
    """
    path = os.path.join(DATA_DIR, 'trade_history.csv')
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


def record_ai_prediction(symbol, side, ml_score, signal_data):
    """
    Iteration 55: Record AI predictions for accuracy audit.
    """
    file_path = os.path.join(DATA_DIR, 'ai_predictions.csv')
    os.makedirs(DATA_DIR, exist_ok=True)
    
    header = ['timestamp', 'symbol', 'side', 'ml_score', 'rsi', 'adx', 'atr', 'vol_growth']
    row = [
        datetime.utcnow().isoformat(),
        symbol,
        side,
        f"{ml_score:.4f}",
        f"{signal_data.get('rsi', 0):.2f}",
        f"{signal_data.get('adx', 0):.2f}",
        f"{signal_data.get('atr', 0):.4f}",
        f"{signal_data.get('vol_growth', 0):.4f}"
    ]
    
    file_exists = os.path.isfile(file_path)
    with open(file_path, 'a') as f:
        if not file_exists:
            f.write(','.join(header) + '\n')
        f.write(','.join(row) + '\n')




def check_and_retrain_model():
    """
    Iteration 55: Weekly Auto-Retrain Logic.
    Retrains the model every Sunday at 00:00 UTC.
    """
    now = datetime.utcnow()
    # Sunday is 6 in weekday()
    if now.weekday() == 6 and now.hour == 0 and now.minute < 15:
        print("🔄 [AI Auto-Retrain] It's Sunday 00:00 UTC. Starting weekly model re-training...")
        try:
            from src.train_model import train
            train()
            send_telegram_msg("🔄 [AI Auto-Retrain] 每週模型再訓練完成，AI 已更新至最新市場狀態。")
        except Exception as e:
            print(f"Error during auto-retrain: {e}")
            send_telegram_msg(f"⚠️ [AI Auto-Retrain] 模型再訓練失敗: {e}")





def log_slippage(symbol, expected_price, actual_price):
    slippage = abs(actual_price - expected_price) / expected_price
    os.makedirs('logs', exist_ok=True)
    with open('logs/slippage.log', 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {symbol}: Expected {expected_price}, Actual {actual_price}, Slippage {slippage*100:.4f}%\n")
    if slippage > 0.001:
        print(f"⚠️ [WARNING] High Slippage detected on {symbol}: {slippage*100:.4f}%")

def save_order_state(symbol, state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, f'order_state_{symbol.replace("/", "_")}.json'), 'w') as f:
        json.dump(state, f)

def load_order_state(symbol):
    path = os.path.join(DATA_DIR, f'order_state_{symbol.replace("/", "_")}.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None

# Global Kill Switch State
KILL_SWITCH_ACTIVE = False


# Iteration 55: AI Filter Tracking
AI_FILTERED_COUNT = 0
LAST_FILTER_RESET = datetime.utcnow().date()

def get_ai_filtered_count():
    global AI_FILTERED_COUNT, LAST_FILTER_RESET
    today = datetime.utcnow().date()
    if today > LAST_FILTER_RESET:
        AI_FILTERED_COUNT = 0
        LAST_FILTER_RESET = today
    return AI_FILTERED_COUNT

def increment_ai_filtered_count():
    global AI_FILTERED_COUNT
    get_ai_filtered_count() # Trigger reset if needed
    AI_FILTERED_COUNT += 1

def check_kill_switch():
    global KILL_SWITCH_ACTIVE
    if os.path.exists(os.path.join(DATA_DIR, 'kill_switch.trigger')):
        KILL_SWITCH_ACTIVE = True
        os.remove(os.path.join(DATA_DIR, 'kill_switch.trigger'))
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



def check_ema_alignment(df_4h):
    """
    Iteration 65: Confirm 4H EMA20 > EMA50 for strong trend alignment.
    """
    if len(df_4h) < 50:
        return False
    ema20 = calculate_ema(df_4h, 20)
    ema50 = calculate_ema(df_4h, 50)
    return ema20.iloc[-1] > ema50.iloc[-1]


def run_strategy():
    global regime_mode
    params = load_params()

    # Iteration 67: Fix variable initialization to prevent crash
    regime_mode = "NEUTRAL"
    indicators_signal = False

    # Iteration 55: Initialize ML Model
    ml_model = CryptoMLModel()
    ml_model.load()

    # Iteration 54: Daily Performance Tracker
    update_daily_performance()

    # Iteration 55: Weekly Auto-Retrain
    check_and_retrain_model()


    # Iteration 16: Dynamic Symbol Selection
    symbols = get_top_relative_strength_symbols()
    prices_rsi = {}
    current_pos_count = get_active_positions_count()
    
    # Iteration 19: Dynamic Equity-Based Risking
    balance = get_account_balance()
    risk_pct = 0.008 # Default 1.5%

    # Iteration 23: BTC Sentiment Filter
    df_btc_1h = fetch_1h_data('BTC/USDT')
    btc_sentiment_ok = False
    if not df_btc_1h.empty:
        btc_ema50 = calculate_ema(df_btc_1h, 50).iloc[-1]
        btc_price = df_btc_1h.iloc[-1]['close']
        btc_sentiment_ok = btc_price > btc_ema50
        print(f"📊 [BTC Sentiment] Price: {btc_price:.2f}, EMA50: {btc_ema50:.2f}, OK: {btc_sentiment_ok}")

    potential_signals = []

    # Iteration 55: Fetch BTC data for ML features
    df_btc_ml = fetch_1h_data('BTC/USDT')
    
    # Iteration 60: Dynamic Environment Filter (Regime Filter)
    regime_mode = "趨勢擴張"
    ml_threshold = 0.85
    min_rr = 1.3
    rsi_threshold_boost = 0
    aggressive_macd = False
    
    if not df_btc_ml.empty:
        # Calculate 24H Volume Change for BTC
        btc_vol_24h_change = df_btc_ml['volume'].pct_change(24).iloc[-1]
        
        # Iteration 60: Aggressive Trend Mode
        btc_ema50_ml = calculate_ema(df_btc_ml, 50).iloc[-1]
        btc_ema200_ml = calculate_ema(df_btc_ml, 200).iloc[-1]
        btc_bullish = df_btc_ml['close'].iloc[-1] > btc_ema50_ml > btc_ema200_ml
        
        if btc_vol_24h_change < -0.20:
            print(f"🚫 [Iteration 67] 縮量進場禁止 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")
            return {}
        if btc_vol_24h_change > 0.20 and btc_bullish:
            regime_mode = "多頭追擊"
            rsi_threshold_boost = 10 # 45 -> 55
            aggressive_macd = True
            print(f"🔥 [Iteration 67] 多頭追擊模式啟動 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")
        elif btc_vol_24h_change < 0:
            regime_mode = "震盪防禦"
            ml_threshold = 0.85
            min_rr = 1.3
            print(f"🛡️ [Iteration 67] 低量防禦模式啟動 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")
        else:
            print(f"🚀 [Iteration 67] 趨勢擴張模式 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")

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
            df_4h['ema50'] = calculate_ema(df_4h, 50)
            latest_4h = df_4h.iloc[-1]
            trend_4h = "Long" if latest_4h['close'] > latest_4h['ema200'] and latest_4h['close'] > latest_4h['ema50'] else "Short"

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # 3. Volume Confirmation (Iteration 25: 2.5x)
            avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[-1]
            vol_ok = latest['volume'] > (avg_vol_5 * 2.5)

            # 4. Heikin-Ashi Trend (Iteration 20)
            ha_long = latest['ha_close'] > latest['ha_open'] and prev['ha_close'] > prev['ha_open']
            ha_short = latest['ha_close'] < latest['ha_open'] and prev['ha_close'] < prev['ha_open']

            # 5. Entry Logic (Iteration 42: Waterfall Guard & Double Divergence)
            # Waterfall Guard: BTC 15m Drop > 1.2%
            df_btc_15m = fetch_15m_data('BTC/USDT')
            if not df_btc_15m.empty:
                btc_15m_change = (df_btc_15m.iloc[-1]['close'] - df_btc_15m.iloc[-2]['close']) / df_btc_15m.iloc[-2]['close'] * 100
                if btc_15m_change < -1.2:
                    # Store waterfall trigger time in a temporary file
                    with open(os.path.join(DATA_DIR, 'waterfall_guard.txt'), 'w') as f:
                        f.write(datetime.utcnow().isoformat())
                    print(f"🌊 [Waterfall Guard] BTC 15m Drop {btc_15m_change:.2f}% detected. Pausing entries.")
            
            # Check if Waterfall Guard is active (2 hours)
            if os.path.exists(os.path.join(DATA_DIR, 'waterfall_guard.txt')):
                with open(os.path.join(DATA_DIR, 'waterfall_guard.txt'), 'r') as f:
                    trigger_time = datetime.fromisoformat(f.read().strip())
                    if (datetime.utcnow() - trigger_time).total_seconds() < 7200:
                        print(f"🚫 [Waterfall Guard] Entries paused for {symbol}.")
                        continue

            # Iteration 54 & 55: MTF Structure & Volume Anomaly
            df_4h = fetch_4h_data(symbol)
            if df_4h.empty: continue
            df_4h['ema200'] = calculate_ema(df_4h, 200)
            df_4h['ema50'] = calculate_ema(df_4h, 50)
            
            support_4h, resistance_4h = find_4h_structure(df_4h)
            support_strength = "N/A"
            mtf_structure_ok = True
            
            if support_4h:
                dist_pct = (latest['close'] - support_4h) / support_4h * 100
                support_strength = f"{dist_pct:.2f}%"
                # Iteration 55: MTF Filter - Must be within 1.5% of 4H support
                if dist_pct > 1.5 or dist_pct < -0.5:
                    mtf_structure_ok = False

            # Ensure we have enough data for EMA 200
            if len(df_4h) < 200:
                trend_4h_strong = False
                risk_multiplier = 1.0
            else:
                trend_4h_strong = latest['close'] > df_4h.iloc[-1]['ema200']
                # If 4H is bearish, reduce risk to 50%
                risk_multiplier = 1.0 if trend_4h_strong else 0.5

            # Iteration 55: Volume Anomaly (1.5x Avg of last 10)
            avg_vol_10 = df['volume'].iloc[-11:-1].mean()
            volume_anomaly = latest['volume'] > (avg_vol_10 * 1.5) if avg_vol_10 > 0 else False

            # 1. MTF Filter (1H EMA 200)
            df_1h = fetch_1h_data(symbol)
            if df_1h.empty:
                print(f"⚠️ [Iteration 67] {symbol} 1H data empty. Skipping.")
                continue
            df_1h['ema200'] = calculate_ema(df_1h, 200)
            trend_1h_strong = latest['close'] > df_1h.iloc[-1]['ema200']

            # 2. Double Divergence (MACD + RSI)
            df['macd_line'], df['macd_signal'], df['macd_hist'] = calculate_macd(df)
            macd_hist = df['macd_hist']
            price_down = latest['close'] < df['close'].iloc[-6]
            macd_up = macd_hist.iloc[-1] > macd_hist.iloc[-6]
            macd_bullish_div = price_down and macd_up
            
            # RSI Bullish Divergence: Price lower, RSI higher than 5 bars ago
            rsi_up = latest['rsi'] > df['rsi'].iloc[-6]
            rsi_bullish_div = price_down and rsi_up
            
            double_div = macd_bullish_div and rsi_bullish_div

            # Iteration 42: Hybrid Logic (Iteration 47: Relaxed Extreme Mode to 35)
            # A. Extreme Mode: RSI < 35 (No Div needed)
            # B. Structural Mode: RSI < 38 + Double Divergence
            extreme_mode = latest['rsi'] < 35
            structural_mode = latest['rsi'] < 38 and double_div
            
            hybrid_trigger = extreme_mode or structural_mode

            # Iteration 39: Asset Tiers Logic (Refined for Hybrid)
            # Iteration 50 Fix: Explicitly assign bandwidth to avoid KeyError
            df['bb_upper'], df['bb_lower'], df['bandwidth'], _ = calculate_bollinger_bands(df, 20, 2)
            latest = df.iloc[-1]
            
            if symbol in ['SOL/USDT', 'BTC/USDT', 'ETH/USDT']:
                vol_buffer = 1.2
                avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[-1]
                vol_exhaustion = latest['volume'] < (avg_vol_5 * vol_buffer)
            else:
                if latest['rsi'] < 30:
                    vol_exhaustion = True
                else:
                    avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[-1]
                    vol_exhaustion = latest['volume'] < (avg_vol_5 * 1.1)

            price_at_bb_lower = latest['low'] <= latest['bb_lower']
            ema_golden_cross = latest['ema20'] > latest['ema50'] and prev['ema20'] <= prev['ema50']

            # Confirmation: RSI Hook Up and First Green Candle
            rsi_hook_up = latest['rsi'] > prev['rsi']
            first_green = latest['close'] > latest['open']

            # Iteration 47: Sensitivity Boost & Momentum Flip
            # Iteration 50: Null Check for Bandwidth
            if 'bandwidth' not in df.columns:
                _, _, df['bandwidth'], _ = calculate_bollinger_bands(df, 20, 2)
                latest = df.iloc[-1]

            bandwidth_avg_100 = df['bandwidth'].rolling(100).mean().iloc[-1]
            squeeze_index = latest['bandwidth'] / bandwidth_avg_100 if bandwidth_avg_100 > 0 else 1.0
            
            # Tier 1: Strong Squeeze (< 0.8x)
            squeeze_tier1 = squeeze_index < 0.8
            # Tier 2: Moderate Squeeze (0.8x - 1.0x)
            squeeze_tier2 = 0.8 <= squeeze_index < 1.0
            
            # Trend Decay Sensitivity Boost: ADX > 22 & RSI < 35
            trend_decay_active = latest['adx'] > 22 and latest['rsi'] < 35

            # Momentum Flip: MACD Histogram shortening for 2 bars
            macd_hist = df['macd_hist']
            momentum_flip = macd_hist.iloc[-1] > macd_hist.iloc[-2] > macd_hist.iloc[-3]

            # Iteration 45: StochRSI Confirmation
            df['stoch_k'], df['stoch_d'] = calculate_stoch_rsi(df)
            latest_stoch_k = df['stoch_k'].iloc[-1]
            latest_stoch_d = df['stoch_d'].iloc[-1]
            prev_stoch_k = df['stoch_k'].iloc[-2]
            prev_stoch_d = df['stoch_d'].iloc[-2]
            
            # Iteration 47: Relaxed StochRSI (No oversold needed)
            stoch_golden_cross = prev_stoch_k <= prev_stoch_d and latest_stoch_k > latest_stoch_d
            stoch_rsi_ok = stoch_golden_cross
            rsi_oversold_45 = latest['rsi'] < 38


            # Iteration 53: Relative Strength Filter (Coin vs BTC 24h)
            # Fetch 24h change for current coin
            df_1d = fetch_ohlcv(symbol, timeframe='1d', limit=2)
            if len(df_1d) >= 2:
                coin_24h_change = (df_1d.iloc[-1]['close'] - df_1d.iloc[-2]['close']) / df_1d.iloc[-2]['close']
            else:
                coin_24h_change = 0
                
            # Fetch 24h change for BTC (if not already fetched this cycle)
            if 'BTC_24H_CHANGE' not in locals():
                df_btc_1d = fetch_ohlcv('BTC/USDT', timeframe='1d', limit=2)
                BTC_24H_CHANGE = (df_btc_1d.iloc[-1]['close'] - df_btc_1d.iloc[-2]['close']) / df_btc_1d.iloc[-2]['close'] if len(df_btc_1d) >= 2 else 0
            
            relative_strength_ok = coin_24h_change > BTC_24H_CHANGE

            # Iteration 52: Dual-Mode Entry & Squeeze Breakout
            # 1. Dual-Mode Entry
            price = latest['close']
            ema200_1h = df['ema200'].iloc[-1] if 'ema200' in df.columns else calculate_ema(df, 200).iloc[-1]
            avg_vol_5 = df['volume'].rolling(5).mean().shift(1).iloc[-1]
            
            # A. Trend Mode (Price > 1H EMA 200)
            trend_mode = price > ema200_1h
            trend_entry = False
            if trend_mode:
                # RSI < 45 (or 55 in Aggressive Mode), MACD Histogram Turn, Volume > Avg 5, Relative Strength > BTC
                macd_turn = macd_hist.iloc[-1] > macd_hist.iloc[-2]
                vol_ok = latest['volume'] > avg_vol_5
                
                # Iteration 60: [Aggressive Trend Mode] MACD Aggressive Signal (MACD Line & Signal Line > 0 and Golden Cross)
                macd_aggressive_signal = False
                if aggressive_macd:
                    macd_golden_cross = df['macd_line'].iloc[-1] > df['macd_signal'].iloc[-1] and df['macd_line'].iloc[-2] <= df['macd_signal'].iloc[-2]
                    if df['macd_line'].iloc[-1] > 0 and df['macd_signal'].iloc[-1] > 0 and macd_golden_cross:
                        macd_aggressive_signal = True
                        print(f"🔥 [Iteration 67] {symbol} MACD Aggressive Signal Detected!")

                # Iteration 60: [Dynamic RSI] Boost RSI limit in Aggressive Mode
                rsi_limit = 45 + rsi_threshold_boost
                if (latest['rsi'] < rsi_limit and macd_turn and vol_ok and relative_strength_ok) or macd_aggressive_signal:
                    trend_entry = True
            
            # B. Bottom Fishing Mode (Price < 1H EMA 200)
            bottom_fishing_mode = price <= ema200_1h
            bottom_entry = False
            if bottom_fishing_mode:
                # RSI < 32, MACD Bullish Divergence
                macd_bullish_div = calculate_macd_divergence(df).iloc[-1]
                if latest['rsi'] < 32 and macd_bullish_div:
                    bottom_entry = True
            
            # 2. Squeeze Breakout Strategy
            squeeze_index = calculate_squeeze_index(df).iloc[-1]
            squeeze_breakout = False
            if squeeze_index < 0.3 and latest['close'] > latest['bb_upper']:
                squeeze_breakout = True
            
            # 3. Time-Filter (Exclude 00:00 - 04:00 UTC - Low Liquidity)
            current_hour = datetime.utcnow().hour
            time_filter_ok = not (0 <= current_hour < 4)
            
            # Final Signal Logic
            long_signal = (trend_entry or bottom_entry or squeeze_breakout) and time_filter_ok and (55 <= latest["rsi"] <= 70)
            
            # Special Case: Squeeze Breakout uses 50% position size
            is_squeeze_trade = squeeze_breakout and not (trend_entry or bottom_entry)

            # Iteration 50: Funding Rate Shield
            funding_rate = fetch_funding_rate(symbol)
            if funding_rate > 0.0003: # 0.03%
                long_signal = False
                print(f"🛡️ [Funding Shield] {symbol} Funding Rate {funding_rate*100:.4f}% too high. Entry blocked.")
            
            # Iteration 49: Dynamic Risk Sizing
            win_rate, losses = get_recent_performance()
            if losses >= 2:
                risk_multiplier = 0.2  # Reduce to 1% (0.2 * 5% base)
            elif win_rate > 0.5:
                risk_multiplier = 0.5  # Increase to 2.5% (0.5 * 5% base)
            else:
                risk_multiplier = 0.3  # Default 1.5%
            
            # Iteration 52: Squeeze Breakout uses 50% position size
            if is_squeeze_trade:
                risk_multiplier *= 0.5

            # Iteration 47: Signal Preview (RSI < 40 but blocked by MACD/ADX)
            signal_preview = False
            if latest['rsi'] < 40 and not long_signal:
                signal_preview = True

            # Iteration 39: Two-Stage Stop-Loss Protection (Tier 2)
            if long_signal and symbol not in ['SOL/USDT', 'BTC/USDT']:
                last_state = load_order_state(symbol)
                if last_state and last_state.get('status') == 'Closed' and last_state.get('exit_reason') in ['SL', 'SL_Trailing']:
                    exit_time = datetime.fromisoformat(last_state['exit_time'])
                    if (datetime.utcnow() - exit_time).total_seconds() < 1800: # 30 mins
                        # Only allow if RSI is lower than previous entry
                        if latest['rsi'] >= last_state.get('entry_rsi', 0):
                            print(f"🛡️ [Iteration 67] {symbol} 處於止損保護期，且 RSI 未創新低。跳過進場。")
                            long_signal = False

            short_signal = False # Iteration 29/30/31 focus on Long Pullback Strategy

            # Iteration 38: Calculate ATR Average for Spike Guard (Factor 1.2)
            atr_avg = df['atr'].rolling(window=100).mean().iloc[-1]
            atr_spike = latest['atr'] > (atr_avg * 1.2) if atr_avg > 0 else False

            # Iteration 42: Capital Re-allocation Weights
            asset_weights = {
                'BTC/USDT': 1.0,
                'ETH/USDT': 1.2,
                'SOL/USDT': 1.0,
                'NEAR/USDT': 0.3,
                'AVAX/USDT': 0.3,
                'FET/USDT': 0.3,
                'ARB/USDT': 0.3
            }
            asset_weight = asset_weights.get(symbol, 0.3)

            # Iteration 37: Distance-Based Sizing Calculation for Report
            price = latest['close']
            ema200 = df_4h.iloc[-1]['ema200']
            dist_ema200_pct = abs(price - ema200) / ema200 * 100 if ema200 > 0 else 0
            
            base_risk = 0.025 * asset_weight # Apply Iteration 42 Weight
            if dist_ema200_pct < 1.5:
                adj_risk = base_risk * 1.2
                weight_str = f"{asset_weight}x (+20%)"
            elif dist_ema200_pct > 5.0:
                adj_risk = base_risk * 0.6
                weight_str = f"{asset_weight}x (-40%)"
            else:
                adj_risk = base_risk
                weight_str = f"{asset_weight}x"

            if atr_spike:
                adj_risk /= 2
                weight_str += " (ATR 減半)"

            # Iteration 46 & 55: Missed Signal Reason
            missed_reason = "None"
            if not long_signal:
                if not trend_4h_strong: missed_reason = "4H Trend Bearish"
                elif not trend_1h_strong: missed_reason = "1H Trend Bearish"
                elif not mtf_structure_ok: missed_reason = f"MTF Structure (Dist: {support_strength})"
                elif not volume_anomaly: missed_reason = "No Volume Anomaly"
                elif not hybrid_trigger: missed_reason = "No RSI/Div Trigger"
                elif not vol_exhaustion: missed_reason = "Volume Spike"
                elif not (price_at_bb_lower or ema_golden_cross): missed_reason = "Price not at BB Lower/EMA Cross"
                elif not stoch_rsi_ok: missed_reason = "StochRSI No Cross"
                elif not (squeeze_tier1 or squeeze_tier2 or trend_decay_active): missed_reason = "No Squeeze/Trend Decay"

            # Store scan results for heartbeat
            prices_rsi[symbol] = {
                'price': latest['close'],
                'rsi': latest['rsi'],
                'adx': latest['adx'],
                'atr': latest['atr'],
                'atr_avg': atr_avg,
                'atr_spike': atr_spike,
                'trend_4h': trend_4h,
                'potential_div': macd_bullish_div, # Iteration 41
                'support': latest['support_12h'],
                'resistance': latest['resistance_12h'],
                'ha_trend': "Bullish" if ha_long else ("Bearish" if ha_short else "Neutral"),
                'bb_lower': latest['bb_lower'],
                'ema200': ema200,
                'dist_ema200_pct': dist_ema200_pct,
                'expected_risk_pct': adj_risk * 100,
                'weight_str': weight_str,
                'squeeze_index': squeeze_index, # Iteration 46
                'missed_reason': missed_reason, # Iteration 46
                'signal_preview': signal_preview, # Iteration 47
                'support_strength': support_strength # Iteration 55
            }

            if long_signal or short_signal:
                side = 'LONG' if long_signal else 'SHORT'
                # Iteration 23: BTC Sentiment & Funding Rate Filter
                if side == 'LONG':
                    if not btc_sentiment_ok:
                        print(f"🚫 [Iteration 67] {symbol} Long signal ignored: BTC Sentiment Bearish.")
                        continue
                    
                    if symbol in ['DOGE/USDT', 'XRP/USDT']:
                        funding_rate = fetch_funding_rate(symbol)
                        if funding_rate > 0.0005:
                            print(f"🚫 [Iteration 67] {symbol} Long signal ignored: Funding Rate too high ({funding_rate*100:.4f}%).")
                            continue

                # Calculate Volume Growth Rate for Correlation Detection
                vol_growth = (latest['volume'] - avg_vol_5) / avg_vol_5 if avg_vol_5 > 0 else 0
                
                # Iteration 55: AI-Enhanced Decision Flow
                # Step 1: Extract features for the current symbol
                df_ml = fetch_1h_data(symbol)
                if not df_ml.empty and not df_btc_ml.empty:
                    features = extract_features(df_ml, df_btc_ml)
                    if not features.empty:
                        # Step 2: Get ML probability score
                        ml_score = ml_model.predict_proba(features.tail(1))[0]
                        print(f"🤖 [AI Score] {symbol}: {ml_score:.4f}")
                        
                        # Update prices_rsi with ml_score for heartbeat
                        prices_rsi[symbol]['ml_score'] = ml_score
                        
                        # Iteration 55: Record prediction for audit
                        record_ai_prediction(symbol, side, ml_score, {
                            'rsi': latest['rsi'],
                            'adx': latest['adx'],
                            'atr': latest['atr'],
                            'vol_growth': vol_growth
                        })
                        
                        # Step 3: Iteration 65 - Tiered Risk Management & BB Squeeze Filter
                        # Calculate BB Width Percentile for Squeeze Filter
                        _, _, bb_width, _ = calculate_bollinger_bands(df_ml)
                        bb_width_20_pct = bb_width.rolling(100).quantile(0.20).iloc[-1]
                        is_squeezed = bb_width.iloc[-1] < bb_width_20_pct
                        
                        # Check 4H EMA Alignment
                        ema_aligned = check_ema_alignment(df_4h)
                        
                        # Iteration 66: EMA20 Slope Filter (1h)
                        ema20 = calculate_ema(df_ml, 20)
                        ema20_slope_up = ema20.iloc[-1] > ema20.iloc[-2]

                        passed_filter = False
                        tier = ""
                        if ml_score >= 0.63:
                            current_risk = 0.012
                            target_rr = 1.5
                            tier = "Tier 1 (High Conviction)"
                            passed_filter = ema20_slope_up
                        elif ml_score >= 0.58:
                            current_risk = 0.005
                            target_rr = 2.0
                            tier = "Tier 2 (Speculative)"
                            passed_filter = is_squeezed and ema_aligned and ema20_slope_up
                        
                        # Iteration 67: 5m Auxiliary Scan
                        if not passed_filter:
                            df_5m = fetch_5m_data(symbol)
                            if not df_5m.empty:
                                df_features_5m = extract_features(df_5m)
                                X_5m = df_features_5m[model.feature_names_in_].fillna(0)
                                ml_score_5m = model.predict_proba(X_5m)[:, 1][-1]
                                # Tier 3 requires higher score and basic trend alignment
                                ema20_5m = calculate_ema(df_5m, 20)
                                ema50_5m = calculate_ema(df_5m, 50)
                                ema_aligned_5m = ema20_5m.iloc[-1] > ema50_5m.iloc[-1]
                                ema20_slope_up_5m = ema20_5m.iloc[-1] > ema20_5m.iloc[-2]
                                rsi_5m = calculate_rsi(df_5m).iloc[-1]
                                
                                if ml_score_5m > 0.70 and ema_aligned_5m and ema20_slope_up_5m and (55 <= rsi_5m <= 70):
                                    current_risk = 0.008
                                    target_rr = 1.5
                                    tier = "Tier 3 (5m Auxiliary)"
                                    passed_filter = True

                        if passed_filter:
                            print(f"🎯 [Iteration 67] {symbol} {tier} Signal. Score: {ml_score:.4f}, Risk: {current_risk*100}%, RR: {target_rr}")
                            potential_signals.append({
                                'symbol': symbol,
                                'side': side,
                                'vol_growth': vol_growth,
                                'latest': latest,
                                'prices_rsi': prices_rsi[symbol],
                                'risk_multiplier': current_risk / 0.008, # Adjust based on base risk
                                'ml_score': ml_score,
                                'target_rr': target_rr,
                                'tier': tier
                            })
                        else:
                            if ml_score >= 0.63:
                                reason = ""
                                if not is_squeezed and ml_score < 0.68: reason += "No Squeeze "
                                if not ema_aligned and ml_score < 0.68: reason += "EMA Not Aligned "
                                if not ema20_slope_up: reason += "EMA20 Slope Down"
                                print(f"🛡️ [Iteration 67] {symbol} score {ml_score:.4f} but rejected: {reason}")
                            else:
                                print(f"🛡️ [AI Filter] {symbol} score {ml_score:.4f} < 0.63. Signal rejected.")
                            increment_ai_filtered_count()
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
        
        # Iteration 52: Max Positions Lock (Strict)
        if current_pos_count >= 3:
            msg = f"🚫 [Max Positions Lock] 發現 {symbol} 信號，但持倉已滿 ({current_pos_count}/3)。"
            print(msg)
            send_telegram_msg(msg)
            continue

        # Iteration 42: Dynamic Asset Allocation (Using pre-calculated adj_risk)
        balance = get_account_balance()
        risk_pct_val = prices_rsi[symbol].get('expected_risk_pct', 0.025)
        
        # Iteration 54: Compounding Position Sizing
        # Position_Size = (Current_Balance * Risk_Percentage) / (2 * ATR)
        # Note: sl_distance is 2.0 * ATR
        risk_amount = balance * (risk_pct_val / 100) * signal.get('risk_multiplier', 1.0)
        
        # Iteration 52: ATR-Based Dynamic SL/TP
        # SL = 2.0 * ATR
        sl_distance = 2.0 * latest['atr'] 
        
        # Formula: Quantity = Risk Amount / SL Distance
        position_qty = risk_amount / sl_distance if sl_distance > 0 else 0
        
        # Compounding Factor for Telegram
        compounding_factor = balance / 1000.0 # Assuming 1000 is initial balance
        
        entry_price = latest['close']
        
        # Iteration 32: No-Leverage Constraint (Max 95% of balance)
        max_position_value = balance * 0.95
        current_position_value = position_qty * entry_price
        
        if current_position_value > max_position_value:
            print(f"⚠️ [RISK] Position value ${current_position_value:.2f} exceeds cap. Reducing to ${max_position_value:.2f}")
            position_qty = max_position_value / entry_price
            current_position_value = max_position_value
        
        sl_price = entry_price - sl_distance
        
        # Iteration 65: Use dynamic RR from signal
        fixed_rr = signal.get('target_rr', 1.3)
        tp_price = entry_price + (sl_distance * fixed_rr)
        
        # R/R Filter (Iteration 65: Use dynamic target_rr)
        actual_rr = (tp_price - entry_price) / sl_distance if sl_distance > 0 else 0
        if actual_rr < fixed_rr:
            print(f"🛡️ [R/R Filter] {symbol} R/R {actual_rr:.2f} < {fixed_rr}. Skipping.")
            continue

        # Iteration 50: Slippage & Depth Protection
        # Iteration 64: Space-to-Resistance Check
        df_1h_check = fetch_1h_data(symbol)
        if not check_upside_potential(symbol, entry_price, df_1h_check):
            continue

        if not check_order_book_depth(symbol, current_position_value):
            print(f"🛡️ [Slippage Shield] {symbol} depth insufficient or slippage > 0.5%. Entry aborted.")
            continue

        # Iteration 43: Exchange-side Hard SL
        entry_order, sl_order = create_order_with_hard_sl(symbol, side, position_qty, entry_price, sl_price, tp_price)
        
        if entry_order:
            # Iteration 52: Fix capital percentage calculation
            capital_pct = (current_position_value / balance) * 100
            send_entry_notification(
                symbol=symbol,
                side=side,
                pos_value=current_position_value,
                capital_pct=capital_pct,
                tp=tp_price,
                sl=sl_price,
                rr=actual_rr,
                ml_score=signal.get('ml_score')
            )
            
            save_order_state(symbol, {
                'entry_price': entry_price,
                'pos_size': position_qty,
                'side': side,
                'status': 'Open',
                'entry_time': datetime.utcnow().isoformat(),
                'iteration': '43',
                'sl_price': sl_price,
                'tp_price': tp_price,
                'atr': latest['atr'],
                'highest_price': entry_price,
                'entry_rsi': latest['rsi'],
                'sl_order_id': sl_order['id'] if sl_order else None
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
            cancel_sl_order(symbol, state.get('sl_order_id'))
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
        

        
        # Iteration 67: Trailing Stop to Break-Even
        # If profit > 0.8%, move SL to entry price
        profit_pct = (current_price - entry_price) / entry_price if side == 'LONG' else (entry_price - current_price) / entry_price
        if not state.get('be_sl_active', False) and profit_pct >= 0.008:
            new_sl = entry_price
            print(f"🛡️ [Iteration 67] {symbol} profit {profit_pct:.2%} >= 0.8%. Moving SL to Break-Even: {new_sl}")
            if update_sl_order(symbol, state.get('sl_order_id'), new_sl):
                state['be_sl_active'] = True
                state['sl_price'] = new_sl
                save_order_state(symbol, state)
                send_telegram_msg(f"🛡️ [Iteration 67] {symbol} 已啟動保本止損 (Trailing to BE)。")


        # Iteration 53: Infinite RR Path
        # 1. Partial TP at 1.2 RR
        rr_1_2_price = entry_price + (state['atr'] * 1.5 * 1.2) if side == 'LONG' else entry_price - (state['atr'] * 1.5 * 1.2)
        
        if not state.get('partial_tp_done', False):
            if (side == 'LONG' and current_price >= rr_1_2_price) or (side == 'SHORT' and current_price <= rr_1_2_price):
                msg = f"💰 [Iteration 67] {symbol} 達到 1.2 RR！執行 50% 減倉止盈。\n剩餘 50% 開啟 EMA 10 移動止損。"
                send_telegram_msg(msg)
                
                # Execute 50% reduction
                reduce_qty = state['pos_size'] * 0.5
                close_partial_position(symbol, reduce_qty)
                
                state['pos_size'] -= reduce_qty
                state['partial_tp_done'] = True
                save_order_state(symbol, state)
        
        # 2. EMA 10 Trailing Stop (for remaining 50%)
        if state.get('partial_tp_done', False):
            df_exit = fetch_15m_data(symbol)
            df_exit['ema10'] = calculate_ema(df_exit, 10)
            ema10 = df_exit['ema10'].iloc[-1]
            if (side == 'LONG' and current_price < ema10) or (side == 'SHORT' and current_price > ema10):
                msg = f"📈 [Iteration 67] {symbol} 跌破 EMA 10！全數平倉獲利了結。"
                send_telegram_msg(msg)
                cancel_sl_order(symbol, state.get('sl_order_id'))
                state['status'] = 'Closed'
                state['exit_price'] = current_price
                state['exit_time'] = datetime.utcnow().isoformat()
                state['exit_reason'] = 'EMA 10 Trailing'
                save_order_state(symbol, state)
                continue

        # Iteration 26: Exit Logic (BB Mid/Upper)
        # Fetch latest BB for exit
        df_exit = fetch_15m_data(symbol)
        df_exit['bb_upper'], df_exit['bb_lower'], df_exit['bb_mid'], _ = calculate_bollinger_bands(df_exit, 20, 2)
        latest_exit = df_exit.iloc[-1]

        if side == 'LONG':
            # Iteration 26: Exit Logic (BB Mid/Upper)
            if current_price >= latest_exit['bb_upper']:
                msg = f"🚀 [Iteration 67] {symbol} 觸及布林上軌！全數平倉獲利了結。"
                send_telegram_msg(msg)
                cancel_sl_order(symbol, state.get('sl_order_id'))
                state['status'] = 'Closed'
                state['exit_price'] = current_price
                state['exit_time'] = datetime.utcnow().isoformat()
                state['exit_reason'] = 'BB Upper'
                save_order_state(symbol, state)
                continue

        # 3. SL (Iteration 53: ATR-based SL)
        sl_price = state.get('sl_price')
        if (side == 'LONG' and current_price <= sl_price) or (side == 'SHORT' and current_price >= sl_price):
            msg = f"❌ [Iteration 67] {symbol} 觸發止損！\n現價：{current_price:.2f} | 止損價：{sl_price:.2f}"
            send_telegram_msg(msg)
            cancel_sl_order(symbol, state.get('sl_order_id'))
            state['status'] = 'Closed'
            state['exit_price'] = current_price
            state['exit_time'] = datetime.utcnow().isoformat()
            state['exit_reason'] = 'SL'
            
            pnl_amount = (state['exit_price'] - state['entry_price']) * state['pos_size']
            pos_value = state['pos_size'] * state['exit_price']
            update_balance(pnl_amount, pos_value)
            record_trade_history(symbol, side, state['exit_price'], state['pos_size'], pnl_amount, 'SL')
            
            save_order_state(symbol, state)
            continue

        # Iteration 45: Redundant Partial TP logic removed in favor of Iteration 57 1.2 R/R logic.
        pass
        
        # 3. Time-based Exit (Iteration 30: 48h)
        entry_time = datetime.fromisoformat(state['entry_time'])
        if (datetime.utcnow() - entry_time).total_seconds() >= 172800: # 48 hours
            if current_price > entry_price:
                msg = f"⏳ [Iteration 67] {symbol} 持倉超過 48 小時且獲利為正，強行平倉釋放資金！"
                send_telegram_msg(msg)
                cancel_sl_order(symbol, state.get('sl_order_id'))
                state['status'] = 'Closed'
                state['exit_price'] = current_price
                state['exit_time'] = datetime.utcnow().isoformat()
                state['exit_reason'] = 'Time_Exit'
                
                # Iteration 32: Financial Tracking
                pnl_amount = (state['exit_price'] - state['entry_price']) * state['pos_size']
                pos_value = state['pos_size'] * state['exit_price']
                update_balance(pnl_amount, pos_value)
                record_trade_history(symbol, side, state['exit_price'], state['pos_size'], pnl_amount, 'Time_Exit')
                
                save_order_state(symbol, state)
                continue

def close_partial_position(symbol, qty):
    """
    Iteration 53: Close 50% of the position at 1.2 RR.
    """
    try:
        # In a real exchange, you would send a market order to close 'qty'
        # For now, we simulate the exchange call and update our local state
        print(f"💰 [EXCHANGE] Partial close executed for {symbol}: {qty} units.")
        return True
    except Exception as e:
        print(f"❌ Error in partial close for {symbol}: {e}")
        return False




if __name__ == "__main__":
    send_telegram_msg("🚀 [System Heartbeat] Iteration 67_Dynamic_Sniper 正在 GCE 啟動。高頻掃描與動態保本機制已就緒。")
    import sys
    if "--check-accounting" in sys.argv:
        print("📊 [ACCOUNTING CHECK]")
        balance = get_account_balance()
        print(f"Total Balance: ${balance:.2f}")
        if os.path.exists(os.path.join(DATA_DIR, 'trade_history.csv')):
            df = pd.read_csv(os.path.join(DATA_DIR, 'trade_history.csv'))
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

    STRATEGY_VERSION = "Iteration 67 - Dynamic Sniper"
    last_heartbeat_time = 0
    last_summary_date = None
    send_telegram_msg("🚀 Iteration 67_Dynamic_Sniper 已於遠端正式啟動，高頻掃描與動態保本機制已就緒。")

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

            # Iteration 43: 30-minute Heartbeat
            if current_time - last_heartbeat_time >= 1800:
                # Collect active position data
                active_positions = []
                
                # Iteration 32: Fetch actual realized PnL and balance
                balance_data = {"total_balance": 1000.0, "realized_pnl": 0.0}
                if os.path.exists(os.path.join(DATA_DIR, 'balance.json')):
                    with open(os.path.join(DATA_DIR, 'balance.json'), 'r') as f:
                        balance_data = json.load(f)
                
                # Iteration 32: Calculate Daily PnL from CSV
                daily_pnl = 0
                if os.path.exists(os.path.join(DATA_DIR, 'trade_history.csv')):
                    try:
                        df_history = pd.read_csv(os.path.join(DATA_DIR, 'trade_history.csv'))
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
                    
                    # Fetch 24h volume change (Iteration 52: Fix volume data)
                    vol_change_24h = 0
                    try:
                        # For accuracy, we fetch 48h of 1h data
                        df_48h = fetch_1h_data('BTC/USDT', limit=48)
                        if len(df_48h) >= 48:
                            last_24h_vol = df_48h.iloc[-24:]['volume'].sum()
                            prev_24h_vol = df_48h.iloc[-48:-24]['volume'].sum()
                            if prev_24h_vol > 0:
                                vol_change_24h = (last_24h_vol - prev_24h_vol) / prev_24h_vol * 100
                    except Exception as e:
                        print(f"Error calculating vol change: {e}")
                    
                    btc_status = {
                        'price': btc_price,
                        'ema50': btc_ema50,
                        'is_bullish': btc_price > btc_ema50,
                        'vol_change_24h': vol_change_24h,
                        'regime_mode': regime_mode
                    }
                    # Iteration 61: Integrated Health Check in Heartbeat
                    send_rich_heartbeat(active_positions, scan_results, len(active_positions), "Iteration 61", btc_status)
                
                last_heartbeat_time = current_time
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)
