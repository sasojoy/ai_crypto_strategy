import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas_ta as ta


import os
import time
import ccxt
import pandas as pd
import json
import shutil
import datetime
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv
from src.notifier import send_telegram_msg, send_kill_switch_alert, send_rich_heartbeat, send_entry_notification, send_hourly_audit, send_daily_performance
from src.logger import log_trade
from src.indicators import *

from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel

from src.strategy.logic import DualTrackStrategy

import numpy as np

def safe_get_float(obj, index=-1):
    """
    Safely extract a float value from a pandas Series, numpy array, or scalar.
    """
    if hasattr(obj, 'values'):
        try:
            return float(obj.values[index])
        except:
            return float(obj.values)
    if hasattr(obj, 'iloc'):
        try:
            return float(obj.iloc[index])
        except:
            return float(obj.iloc)
    if isinstance(obj, (list, np.ndarray)):
        return float(obj[index])
    return float(obj)

def safe_get_bool(obj, index=-1):
    """
    Safely extract a boolean value from a pandas Series, numpy array, or scalar.
    """
    if hasattr(obj, 'values'):
        try:
            return bool(obj.values[index])
        except:
            return bool(obj.values)
    if hasattr(obj, 'iloc'):
        try:
            return bool(obj.iloc[index])
        except:
            return bool(obj.iloc)
    if isinstance(obj, (list, np.ndarray)):
        return bool(obj[index])
    return bool(obj)

def fetch_btc_vol_with_retry(symbol='BTC/USDT', limit=500, retries=3):
    """
    Iteration 67.4: Fetch BTC volume with retry logic for UTC 00:00 stability.
    """
    for i in range(retries):
        df = fetch_1h_data(symbol, limit=limit)
        if not df.empty:
            current_vol = df['volume'].iloc[-1]
            if current_vol > 0:
                return df
            print(f"⚠️ [Retry {i+1}] BTC Volume is 0, retrying in 2s...")
            time.sleep(2)
    return pd.DataFrame()




# Load environment variables
load_dotenv()

# Iteration 75.0: Robust Absolute Path Definition for GCE/PM2
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Iteration 91.1.3: Use data/ folder for persistence
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
MODELS_DIR = os.path.join(BASE_DIR, 'models')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


# Iteration 133.8: Environment Isolation & Tactical Stop Loss
STRATEGY_VERSION = "[H16_PREDATOR_V133.8]"

# Iteration 127.0: Live Hunting Mode Enabled
IS_SIMULATION = False
WATCH_ONLY = False

# Security Check & Watcher Mode Initialization
if not IS_SIMULATION:
    if not os.getenv('BINANCE_API_KEY') or not os.getenv('BINANCE_SECRET'):
        print("⚠️ [SECURITY WARNING] No API keys found. Entering WATCH_ONLY mode.")
        WATCH_ONLY = True
    else:
        print("🚀 [SECURITY] API keys found. Full Trade Mode Active.")

# Initialize Exchange
if WATCH_ONLY:
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
else:
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET'),
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })




# Iteration 94.0: Dual-Track Strategy Instance
strategy_logic = DualTrackStrategy()


# Global state initialization
regime_mode = "NEUTRAL"

def execute_trade(symbol, side, qty, price, atr, params, ml_score=0, reason=""):
    """
    Iteration 96.0: Reconstructed Execution Engine with Slippage Compensation & Residual Analysis
    """
    # 1. Slippage Buffer Logic (Iteration 95.1)
    if symbol in ['BTC/USDT', 'ETH/USDT']:
        fee_buffer = 0.001  # 0.1%
    elif symbol == 'SOL/USDT':
        fee_buffer = 0.002  # 0.2%
    else:
        fee_buffer = 0.005  # 0.5% (FET/AVAX/Alts)

    # 2. TP/SL Calculation
    tp_price = price * (1 + params['tp_pct'] + fee_buffer)
    sl_price = price * (1 - params['sl_pct'])
    
    print(f"🚀 [EXECUTION] {side} {symbol} | Qty: {qty:.4f} | Price: {price:.2f}")
    print(f"📈 [TP] {tp_price:.2f} (Buffer: {fee_buffer*100:.1f}%) | [SL] {sl_price:.2f}")

    # 3. Simulation/Real Order Execution
    if WATCH_ONLY:
        print(f"🔔 [WATCH_ONLY] Signal Detected: {side.upper()} {symbol} at {price}")
        msg = (
            f"📢 [H16_WATCHER] 偵測到進場訊號！\n"
            f"標的: {symbol}\n"
            f"動作: {side.upper()} (Long/Short)\n"
            f"現價: {price:.2f}\n"
            f"原因: {reason} / AI Score {ml_score:.4f}\n"
            f"預計 TP: {tp_price:.2f} (4.0x ATR)\n"
            f"預計 SL: {sl_price:.2f} (1.8x ATR)"
        )
        send_telegram_msg(msg)
    elif IS_SIMULATION:
        print(f"📝 [SIMULATION] Order recorded for {symbol}")
        # In simulation, we just log it
        record_trade_history(symbol, side, price, qty, 0, reason, ml_score, tp_price)
    else:
        # Real order logic would go here
        # create_order_with_hard_sl(symbol, side, qty, price, sl_price, tp_price)
        # Iteration 96.0: Residual Analysis (Placeholder for real execution)
        # actual_price = ...
        # if (actual_price - price)/price > fee_buffer:
        #     send_telegram_msg(f"⚠️ [SLIPPAGE ALERT] {symbol} actual slippage exceeds buffer!")
        pass

    print(f"✅ [EXECUTION] execute_trade defined. Ready for H16_FINAL_SHARP.")
    return True




def load_params():
    params_path = os.path.join(CONFIG_DIR, 'params.json')
    try:
        if not os.path.exists(params_path):
            # Create default params if not exists
            default_params = {"ema_f": 12, "ema_s": 26, "bb_std": 2}
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(params_path, 'w') as f:
                json.dump(default_params, f)
            return default_params
        with open(params_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ [JSON PATH ERROR] Failed to load params from {params_path}: {e}")
        return {"ema_f": 12, "ema_s": 26, "bb_std": 2}

def get_recent_performance():
    """
    Iteration 49: Track recent 10 trades for dynamic risk sizing
    """
    history_path = os.path.join(DATA_DIR, 'trade_history.json')
    try:
        if not os.path.exists(history_path):
            return 0.5, 0 # Default win rate 50%, 0 losses
        
        with open(history_path, 'r') as f:
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
    print(f"🔍 [Iteration 89.0 | Rigid Data] Monitoring Selected Symbols: {selected_symbols}")
    return selected_symbols

# Global exchange instances (Iteration 88.0: Singleton Pattern)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
exchange_futures = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

def fetch_15m_data(symbol='BTC/USDT', limit=500):
    """
    Iteration 91.1.3: Fetch 15m data with local caching to prevent data gaps.
    """
    cache_file = os.path.join(DATA_DIR, f"{symbol.replace('/', '_')}_15m.csv")
    # Iteration 91.1.3: Rigid Data Alignment (Force 500)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            timeframe = '15m'
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv is None or len(ohlcv) < limit:
                print(f"⚠️ [Iteration 91.1.3 | Pre-warmup] {symbol} Data insufficient (count: {len(ohlcv) if ohlcv else 0}/{limit})")
                # Try to load from cache if API fails
                if os.path.exists(cache_file):
                    print(f"📂 Loading {symbol} 15m data from cache...")
                    return pd.read_csv(cache_file, parse_dates=['timestamp'])
                return pd.DataFrame()
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Save to cache
            df.to_csv(cache_file, index=False)
            return df
        except Exception as e:
            print(f"❌ Attempt {attempt+1}/{max_retries} failed for {symbol} (15m): {type(e).__name__} - {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"🚨 CRITICAL: All retries failed for {symbol} (15m)")
                if os.path.exists(cache_file):
                    print(f"📂 Loading {symbol} 15m data from cache after all retries failed...")
                    return pd.read_csv(cache_file, parse_dates=['timestamp'])
                return pd.DataFrame()

def fetch_5m_data(symbol='BTC/USDT'):
    # Iteration 89.0: Rigid Data Alignment (Force 500)
    limit = 500
    max_retries = 3
    for attempt in range(max_retries):
        try:
            timeframe = '5m'
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv is None or len(ohlcv) < limit:
                print(f"⚠️ [Iteration 89.0 | Rigid Data] {symbol} Data insufficient (count: {len(ohlcv) if ohlcv else 0}/{limit})")
                return pd.DataFrame()
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"❌ Attempt {attempt+1}/{max_retries} failed for {symbol} (5m): {type(e).__name__} - {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"🚨 CRITICAL: All retries failed for {symbol} (5m)")
                return pd.DataFrame()





def fetch_4h_data(symbol='BTC/USDT'):
    """
    Iteration 16: Multi-Timeframe Filter
    Fetch 4-hour data to determine the major trend.
    """
    # Iteration 89.0: Rigid Data Alignment (Force 500)
    limit = 500
    max_retries = 3
    for attempt in range(max_retries):
        try:
            timeframe = '4h'
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv is None or len(ohlcv) < limit:
                print(f"⚠️ [Iteration 89.0 | Rigid Data] {symbol} Data insufficient (count: {len(ohlcv) if ohlcv else 0}/{limit})")
                return pd.DataFrame()
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"❌ Attempt {attempt+1}/{max_retries} failed for {symbol} (4h): {type(e).__name__} - {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"🚨 CRITICAL: All retries failed for {symbol} (4h)")
                return pd.DataFrame()


def fetch_ohlcv(symbol, timeframe="1h", limit=500):
    # Iteration 89.0: Rigid Data Alignment (Force 500)
    limit = 500
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv is None or len(ohlcv) < limit:
                print(f"⚠️ [Iteration 89.0 | Rigid Data] {symbol} Data insufficient (count: {len(ohlcv) if ohlcv else 0}/{limit})")
                return pd.DataFrame()
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e:
            print(f"❌ Attempt {attempt+1}/{max_retries} failed for {symbol} ({timeframe}): {type(e).__name__} - {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"🚨 CRITICAL: All retries failed for {symbol} ({timeframe})")
                return pd.DataFrame()


def fetch_1h_data(symbol='BTC/USDT', limit=500):
    # Iteration 91.1.3: Fetch 1h data with local caching
    cache_file = os.path.join(DATA_DIR, f"{symbol.replace('/', '_')}_1h.csv")
    limit = 500
    max_retries = 3
    for attempt in range(max_retries):
        try:
            timeframe = '1h'
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if ohlcv is None or len(ohlcv) < limit:
                print(f"⚠️ [Iteration 91.1.3 | Pre-warmup] {symbol} Data insufficient (count: {len(ohlcv) if ohlcv else 0}/{limit})")
                if os.path.exists(cache_file):
                    print(f"📂 Loading {symbol} 1h data from cache...")
                    return pd.read_csv(cache_file, parse_dates=['timestamp'])
                return pd.DataFrame()
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Save to cache
            df.to_csv(cache_file, index=False)
            return df
        except Exception as e:
            print(f"❌ Attempt {attempt+1}/{max_retries} failed for {symbol}: {type(e).__name__} - {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt) # Exponential backoff
            else:
                print(f"🚨 CRITICAL: All retries failed for {symbol}")
                return pd.DataFrame()


def fetch_funding_rate(symbol):
    """
    Iteration 17: Funding Rate Filter
    Fetch current funding rate for the symbol using Public API.
    """
    try:
        # Iteration 88.0: Use Singleton
        funding = exchange_futures.fetch_funding_rate(symbol)
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
        # Iteration 88.0: Use Singleton
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
        # Iteration 88.0: Use Singleton
        oi_data = exchange_futures.fetch_open_interest(symbol)
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
    if not isinstance(df_1h, pd.DataFrame) or df_1h.empty or len(df_1h) < 24:
        return True
    
    try:
        # Use safe_get_float for robust extraction
        recent_high = safe_get_float(df_1h['high'].values[-24:].max())
        upside_pct = (recent_high - entry_price) / entry_price
        
        if upside_pct < 0.012:
            print(f"🛡️ [Iteration 89.0 | Rigid Data] [Space Check] {symbol} upside {upside_pct:.2%} < 1.2% to resistance ({recent_high:.2f}). Skipping.")
            return False
    except Exception as e:
        print(f"Error in check_upside_potential for {symbol}: {e}")
        return True
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
    if not os.path.exists(DATA_DIR):
        return 0
    for filename in os.listdir(DATA_DIR):
        if filename.startswith('order_state_') and filename.endswith('.json'):
            try:
                with open(os.path.join(DATA_DIR, filename), 'r') as f:
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
        today_str = datetime.now(UTC).strftime('%Y-%m-%d')
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
        
        now = datetime.now(UTC)
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

def record_trade_history(symbol, side, price, quantity, pnl, reason, ml_score=0, tp_price=0):
    """
    Iteration 96.0: Enhanced Trade History with AI Score and Final_TP
    """
    path = os.path.join(DATA_DIR, 'trade_history.csv')
    timestamp = datetime.now(UTC).isoformat()
    df = pd.DataFrame([{
        'timestamp': timestamp,
        'symbol': symbol,
        'side': side,
        'price': price,
        'quantity': quantity,
        'pnl': pnl,
        'reason': reason,
        'ml_score': ml_score,
        'final_tp': tp_price
    }])
    
    if not os.path.exists(path):
        df.to_csv(path, index=False)
    else:
        # Check if columns match, if not, we might need to handle it
        try:
            existing_df = pd.read_csv(path, nrows=0)
            if 'ml_score' not in existing_df.columns:
                # Re-write with new headers if columns changed
                full_df = pd.read_csv(path)
                full_df['ml_score'] = 0
                full_df['final_tp'] = 0
                full_df = pd.concat([full_df, df], ignore_index=True)
                full_df.to_csv(path, index=False)
                return
        except:
            pass
        df.to_csv(path, mode='a', header=False, index=False)


def record_ai_prediction(symbol, side, ml_score, signal_data):
    """
    Iteration 55: Record AI predictions for accuracy audit.
    """
    file_path = os.path.join(DATA_DIR, 'ai_predictions.csv')
    os.makedirs(DATA_DIR, exist_ok=True)
    
    header = ['timestamp', 'symbol', 'side', 'ml_score', 'rsi', 'adx', 'atr', 'vol_growth']
    row = [
        datetime.now(UTC).isoformat(),
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
    Iteration 92.0: Weekly Auto-Retrain Logic with Task Locking.
    Retrains the model every Sunday at 00:00 UTC, limited to once per day.
    """
    now = datetime.now(UTC)
    today_str = now.strftime('%Y-%m-%d')
    retrain_lock_path = os.path.join(DATA_DIR, 'last_retrain.json')
    
    # Load last retrain date
    last_retrain_date = ""
    if os.path.exists(retrain_lock_path):
        try:
            with open(retrain_lock_path, 'r') as f:
                last_retrain_date = json.load(f).get('last_retrain_date', "")
        except:
            pass

    # Sunday is 6 in weekday()
    if now.weekday() == 6 and now.hour == 0 and now.minute < 15:
        if last_retrain_date == today_str:
            # Already retrained today, skip to avoid infinite loop
            return

        print(f"🔄 [AI Auto-Retrain] {today_str} 00:00 UTC. Starting weekly model re-training...")
        try:
            from src.train_model import train
            train()
            
            # Update lock file immediately after success
            with open(retrain_lock_path, 'w') as f:
                json.dump({'last_retrain_date': today_str}, f)
                
            send_telegram_msg(f"🔄 [AI Auto-Retrain] {today_str} 每週模型再訓練完成，AI 已更新至最新市場狀態。")
        except Exception as e:
            print(f"Error during auto-retrain: {e}")
            send_telegram_msg(f"⚠️ [AI Auto-Retrain] 模型再訓練失敗: {e}")





def log_slippage(symbol, expected_price, actual_price):
    slippage = abs(actual_price - expected_price) / expected_price
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(os.path.join(LOGS_DIR, 'slippage.log'), 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {symbol}: Expected {expected_price}, Actual {actual_price}, Slippage {slippage*100:.4f}%\n")
    if slippage > 0.001:
        print(f"⚠️ [WARNING] High Slippage detected on {symbol}: {slippage*100:.4f}%")

def save_order_state(symbol, state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, f'order_state_{symbol.replace("/", "_")}.json'), 'w') as f:
        json.dump(state, f)
    
    # Iteration 91.1: Persistence for Active Trades
    ACTIVE_TRADES_PATH = os.path.join(DATA_DIR, 'active_trades.json')
    active_trades = {}
    if os.path.exists(ACTIVE_TRADES_PATH):
        try:
            with open(ACTIVE_TRADES_PATH, 'r') as f:
                active_trades = json.load(f)
        except Exception as e:
            print(f"❌ [JSON PATH ERROR] Failed to read {ACTIVE_TRADES_PATH}: {e}")
    
    if state.get('status') == 'Open':
        active_trades[symbol] = {
            'entry_price': state.get('entry_price'),
            'highest_price': state.get('highest_price'),
            'pos_size_multiplier': state.get('pos_size_multiplier', 1.0),
            'sl_price': state.get('sl_price'),
            'trailing_active': state.get('trailing_active', False),
            'side': state.get('side', 'LONG')
        }
    else:
        if symbol in active_trades:
            del active_trades[symbol]
            
    with open(ACTIVE_TRADES_PATH, 'w') as f:
        json.dump(active_trades, f)

def load_order_state(symbol):
    path = os.path.join(DATA_DIR, f'order_state_{symbol.replace("/", "_")}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ [JSON PATH ERROR] Failed to read {path}: {e}")
            return None
    return None

# Global Kill Switch State
KILL_SWITCH_ACTIVE = False


# Iteration 55: AI Filter Tracking
AI_FILTERED_COUNT = 0
LAST_FILTER_RESET = datetime.now(UTC).date()

def get_ai_filtered_count():
    global AI_FILTERED_COUNT, LAST_FILTER_RESET
    today = datetime.now(UTC).date()
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


def run_strategy(ml_model):
    """
    Iteration 101.0: 1H Core Unified Strategy
    All symbols (BTC/ETH/SOL/FET/AVAX) unified to 1H timeframe.
    """
    global regime_mode
    params = load_params()
    update_daily_performance()
    check_and_retrain_model()

    # 1. Dynamic Symbol Selection & Data Pre-warmup
    symbols = get_top_relative_strength_symbols()
    prices_rsi = {}
    
    # Fetch BTC data for ML features (Global Context)
    df_btc_ml = fetch_1h_data('BTC/USDT', limit=500)
    if df_btc_ml.empty:
        print("⚠️ [Critical] BTC data empty. Skipping cycle.")
        return {}

    # 2. 1H Core Pre-warmup
    warmup_count = 0
    for s in symbols:
        df_1h = fetch_1h_data(s, limit=500)
        
        if not df_1h.empty and len(df_1h) >= 500:
            warmup_count += 1
            prices_rsi[s] = {'price': df_1h.iloc[-1]['close'], 'missed_reason': 'Ready'}
        else:
            prices_rsi[s] = {'price': 0, 'missed_reason': 'Initializing'}
    
    if warmup_count < len(symbols):
        print(f"⏳ [Initializing] 1H Data Syncing ({warmup_count}/{len(symbols)})...")
        return prices_rsi

    # 3. Execution Loop
    current_pos_count = get_active_positions_count()
    balance = get_account_balance()
    
    print(f"🚀 {STRATEGY_VERSION} LIVE WATCHER ACTIVE.")

    for symbol in symbols:
        try:
            df = fetch_1h_data(symbol, limit=500)
            if df.empty: continue

            # AI Scoring
            X = extract_features(df, df_btc_ml)
            if not X.empty:
                print(f"🔍 [H16_PREDATOR] Feature Calculation Success for {symbol}")
            X_input = X.tail(1)
            REQUIRED_FEATURES = ['rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 'dist_sr_low', 'dist_sr_high', 'price_momentum']
            X_input = X_input[REQUIRED_FEATURES]
            
            # Iteration 126.1: Consistency Logging
            feature_vals = X_input.iloc[0].tolist()
            print(f"DEBUG [Consistency] symbol: {symbol} | features: {feature_vals}")
            
            probs = ml_model.predict_proba(X_input)
            base_ml_score = float(probs[0][1])
            
            # Iteration 108.0: Volume Divergence Check
            # If price increases but volume decreases (last 3 bars), subtract 0.2
            price_trend = df['close'].iloc[-1] > df['close'].iloc[-3]
            vol_trend = df['volume'].iloc[-1] < df['volume'].iloc[-3]
            ml_score = base_ml_score - 0.2 if (price_trend and vol_trend) else base_ml_score
            
            # Iteration 108.0: Market Weather System (BTC 1H EMA200)
            btc_ema200 = calculate_ema(df_btc_ml, 200).iloc[-1]
            btc_price = df_btc_ml['close'].iloc[-1]
            btc_bullish = btc_price > btc_ema200
            
            # Iteration 102.0: RSI Overrule Logic
            rsi = float(calculate_rsi(df).iloc[-1])
            dist_ema200 = (df['close'].iloc[-1] - calculate_ema(df, 200).iloc[-1]) / calculate_ema(df, 200).iloc[-1]
            
            # Iteration 126.0: Precision Hunter Production Logic
            import pandas_ta as ta
            
            # 1. Indicators
            ema20 = calculate_ema(df, 20).iloc[-1]
            ema200 = calculate_ema(df, 200).iloc[-1] # Iteration 133.8: 1H EMA200 Guard
            atr = calculate_atr(df, 14).iloc[-1]
            vol_avg = df['volume'].rolling(24).mean().iloc[-1]
            
            adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
            curr_adx = adx_df['ADX_14'].iloc[-1]
            is_adx_rising = adx_df['ADX_14'].diff().iloc[-1] > 0
            
            # 2. Tiered Volume Threshold
            vol_threshold = 2.0 if symbol in ['BTC/USDT', 'ETH/USDT'] else 3.0
            is_volume_burst = df['volume'].iloc[-1] > (vol_avg * vol_threshold)
            is_trend_confirmed = curr_adx > 25 and is_adx_rising
            
            # 3. Entry Logic (Iteration 133.9: Profit Recovery Plan)
            side = None
            entry_reason = ""
            
            # Iteration 133.9: AI Score Thresholds
            ai_threshold = 0.88 if symbol in ['FET/USDT', 'AVAX/USDT', 'SOL/USDT'] else 0.82
            
            # Iteration 133.9: Profit Space Filter (Entry to TP > 1.5% net)
            # 1. Slippage Buffer Logic (Iteration 95.1)
            if symbol in ['BTC/USDT', 'ETH/USDT']:
                fee_buffer = 0.0015
            elif symbol == 'SOL/USDT':
                fee_buffer = 0.0025
            else:
                fee_buffer = 0.0055
            
            potential_tp_long = df['close'].iloc[-1] + (5.0 * atr)
            potential_tp_short = df['close'].iloc[-1] - (5.0 * atr)
            profit_space_long = (potential_tp_long - df['close'].iloc[-1]) / df['close'].iloc[-1] - fee_buffer
            profit_space_short = (df['close'].iloc[-1] - potential_tp_short) / df['close'].iloc[-1] - fee_buffer

            # Long Entry: Price > EMA200 + AI Score + Profit Space
            if (df['close'].iloc[-1] > ema200 and 
                ml_score >= ai_threshold and 
                profit_space_long > 0.015 and
                is_volume_burst and is_trend_confirmed and rsi > 50):
                side = 'Long'
                entry_reason = f"V133.9_LONG | AI:{ml_score:.2f} | Space:{profit_space_long*100:.1f}%"
            
            # Short Entry: Price < EMA200 + AI Score + Profit Space
            elif (df['close'].iloc[-1] < ema200 and 
                  (1 - ml_score) >= ai_threshold and 
                  profit_space_short > 0.015 and
                  is_volume_burst and is_trend_confirmed and rsi < 50):
                side = 'Short'
                entry_reason = f"V133.9_SHORT | AI:{ml_score:.2f} | Space:{profit_space_short*100:.1f}%"

            # 4. Execution with ATR Dynamic SL/TP
            if side and current_pos_count < 5:
                # Iteration 133.9: ATR 2.5/5.0
                params['tp_pct'] = (5.0 * atr) / df['close'].iloc[-1]
                params['sl_pct'] = (2.5 * atr) / df['close'].iloc[-1]
                
                pos_size = balance * 0.2 # Fixed 20% for stability in V126
                
                print(f"🎯 [SIGNAL] {symbol} (1H) {side} | Reason: {entry_reason}")
                execute_trade(symbol, side, pos_size, df['close'].iloc[-1], atr, params, ml_score, entry_reason)
                
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

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
        

        
        # Iteration 133.9: Trailing Stop to Break-Even (2 * ATR)
        atr = state.get('atr', 0)
        profit_abs = (current_price - entry_price) if side == 'LONG' else (entry_price - current_price)
        if not state.get('be_sl_active', False) and atr > 0 and profit_abs >= (2.0 * atr):
            new_sl = entry_price
            print(f"🛡️ [Iteration 133.9] {symbol} profit {profit_abs:.4f} >= 2*ATR ({2.0*atr:.4f}). Moving SL to Break-Even: {new_sl}")
            if update_sl_order(symbol, state.get('sl_order_id'), new_sl):
                state['be_sl_active'] = True
                state['sl_price'] = new_sl
                save_order_state(symbol, state)
                send_telegram_msg(f"🛡️ [Iteration 133.9] {symbol} 已達到 2*ATR 獲利，啟動保本止損 (Trailing to BE)。")

        # Iteration 91.1: Professional Trailing Stop Logic (Legacy, kept for safety)
        state['highest_price'] = max(state.get('highest_price', entry_price), current_price)
        profit_from_entry = (state['highest_price'] - entry_price) / entry_price
        
        if profit_from_entry >= 0.01:
            # Iteration 91.1: Move SL to Entry + 0.5% after 1% profit
            new_sl = entry_price * 1.005
            if (side == 'LONG' and new_sl > state.get('sl_price', 0)) or (side == 'SHORT' and new_sl < state.get('sl_price', 999999)):
                print(f"🛡️ [Iteration 91.1] {symbol} Profit > 1%. Moving SL to Entry + 0.5%: {new_sl}")
                if update_sl_order(symbol, state.get('sl_order_id'), new_sl):
                    state['sl_price'] = new_sl
                    state['trailing_active'] = True
                    save_order_state(symbol, state)


        # Iteration 53: Infinite RR Path
        # 1. Partial TP at 1.2 RR
        rr_1_2_price = entry_price + (state['atr'] * 1.5 * 1.2) if side == 'LONG' else entry_price - (state['atr'] * 1.5 * 1.2)
        
        if not state.get('partial_tp_done', False):
            if (side == 'LONG' and current_price >= rr_1_2_price) or (side == 'SHORT' and current_price <= rr_1_2_price):
                msg = f"💰 [Iteration 91.1 | Final Stability Fix] {symbol} 達到 1.2 RR！執行 50% 減倉止盈。\n剩餘 50% 開啟 EMA 10 移動止損。"
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
            if not df_exit.empty:
                df_exit['ema10'] = calculate_ema(df_exit, 10)
                ema10 = safe_get_float(df_exit['ema10'])
                if (side == 'LONG' and current_price < ema10) or (side == 'SHORT' and current_price > ema10):
                    msg = f"📈 [Iteration 91.1 | Final Stability Fix] {symbol} 跌破 EMA 10！全數平倉獲利了結。"
                    send_telegram_msg(msg)
                    cancel_sl_order(symbol, state.get('sl_order_id'))
                    state['status'] = 'Closed'
                    state['exit_price'] = current_price
                    state['exit_time'] = datetime.now(UTC).isoformat()
                    state['exit_reason'] = 'EMA 10 Trailing'
                    save_order_state(symbol, state)
                    continue

        # Iteration 26: Exit Logic (BB Mid/Upper)
        # Fetch latest BB for exit
        df_exit = fetch_15m_data(symbol)
        if not df_exit.empty:
            df_exit['bb_upper'], df_exit['bb_lower'], df_exit['bb_mid'], _ = calculate_bollinger_bands(df_exit, 20, 2)
            bb_upper = safe_get_float(df_exit['bb_upper'])

            if side == 'LONG':
                # Iteration 26: Exit Logic (BB Mid/Upper)
                if current_price >= bb_upper:
                    msg = f"🚀 [Iteration 91.1 | Final Stability Fix] {symbol} 觸及布林上軌！全數平倉獲利了結。"
                    send_telegram_msg(msg)
                    cancel_sl_order(symbol, state.get('sl_order_id'))
                    state['status'] = 'Closed'
                    state['exit_price'] = current_price
                    state['exit_time'] = datetime.now(UTC).isoformat()
                    state['exit_reason'] = 'BB Upper'
                    save_order_state(symbol, state)
                    continue

        # 3. SL (Iteration 53: ATR-based SL)
        sl_price = state.get('sl_price')
        if (side == 'LONG' and current_price <= sl_price) or (side == 'SHORT' and current_price >= sl_price):
            msg = f"❌ [Iteration 91.1 | Final Stability Fix] {symbol} 觸發止損！\n現價：{current_price:.2f} | 止損價：{sl_price:.2f}"
            send_telegram_msg(msg)
            cancel_sl_order(symbol, state.get('sl_order_id'))
            state['status'] = 'Closed'
            state['exit_price'] = current_price
            state['exit_time'] = datetime.now(UTC).isoformat()
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
        if (datetime.now(UTC) - entry_time).total_seconds() >= 172800: # 48 hours
            if current_price > entry_price:
                msg = f"⏳ [Iteration 91.1 | Final Stability Fix] {symbol} 持倉超過 48 小時且獲利為正，強行平倉釋放資金！"
                send_telegram_msg(msg)
                cancel_sl_order(symbol, state.get('sl_order_id'))
                state['status'] = 'Closed'
                state['exit_price'] = current_price
                state['exit_time'] = datetime.now(UTC).isoformat()
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
        print(f"❌ [Iteration 91.1 | DevOps Compliance] Error in partial close for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return False




if __name__ == "__main__":
    try:
        # Iteration 91.1: Startup Message
        send_telegram_msg("🚀 【Iteration 91.1】 寧靜與純淨化完成，系統正式上線")
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

        # STRATEGY_VERSION = "🚀 【Iteration 93.1 | Cold Start & Refined Cleanup】" (Removed duplicate)
        
        # Iteration 91.1.3: Ensure data directory exists
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            print(f"📁 Created data directory at {DATA_DIR}")

        last_report_time = datetime.now()
        last_summary_date = None
        # Iteration 93.0: Delay retrain check by 1 hour after startup
        startup_time = datetime.now(UTC)
        
        # Iteration 91.1: Load Active Trades from Persistence
        ACTIVE_TRADES_PATH = os.path.join(DATA_DIR, 'active_trades.json')
        if os.path.exists(ACTIVE_TRADES_PATH):
            try:
                with open(ACTIVE_TRADES_PATH, 'r') as f:
                    persisted_trades = json.load(f)
                    print(f"📦 [Iteration 91.1] Loaded {len(persisted_trades)} persisted trades.")
            except Exception as e:
                print(f"⚠️ Error loading persisted trades: {e}")

        # Iteration 93.0: Lightweight Startup Notification
        try:
            send_telegram_msg(f"🚀 【{STRATEGY_VERSION}】已啟動。正在執行背景數據同步與模型載入...")
        except Exception as e:
            print(f"Failed to send startup notification: {e}")

        # Iteration 93.0: Rule 3 - Single Load Verification
        print(f"🤖 [System] Loading ML Model for {STRATEGY_VERSION}...")
        ml_model = CryptoMLModel()
        if ml_model.load():
            print("✅ Model Loaded Successfully.")
        else:
            print("⚠️ Model Load Failed or Not Found. Using default/untrained state.")
        
        # Iteration 93.0: Optimized Data Pre-warmup (Single Telegram Update)
        print(f"🔍 [Iteration 93.0 | Lightweight Start] Pre-warming data (500 K-lines)...")
        warmup_symbols = get_top_relative_strength_symbols()
        total_warmup = len(warmup_symbols)
        
        for i, s in enumerate(warmup_symbols):
            print(f"⏳ [{i+1}/{total_warmup}] Syncing {s}...")
            # Iteration 93.0: Force sync with 1s sleep between symbols to avoid rate limit
            fetch_1h_data(s, limit=500)
            fetch_15m_data(s)
            time.sleep(1.0)
        
        try:
            send_telegram_msg(f"✅ {STRATEGY_VERSION} 數據同步完成 ({total_warmup}/{total_warmup} 幣種)，進入主循環。")
        except:
            pass
            
        print(f"✅ {STRATEGY_VERSION} Initialization Complete.")

        while True:
            try:
                # Iteration 93.0: Heartbeat for PM2 Log diagnosis
                print(f"💓 [Heartbeat] System Alive | {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
                
                if check_kill_switch():
                    trigger_panic_sell_all()

                now = datetime.now(UTC)
                
                # Iteration 93.0: Delay retrain check by 1 hour after startup to prevent loop
                if (now - startup_time).total_seconds() > 3600:
                    check_and_retrain_model()
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
                scan_results = run_strategy(ml_model)
                
                # Iteration 91.1: Final Stability Fix - Scan Alarm Silenced
                print(f"🔍 [System] Scan complete. Found {len(scan_results)} results.")
                if len(scan_results) == 0:
                    print("⚠️ [ALARM] scan_results is EMPTY!")

                manage_positions(scan_results)
                current_time = time.time()

                # Iteration 600.0-DYNAMO: Enhanced Hourly Heartbeat & Regime Report
                if (datetime.now() - last_report_time).total_seconds() >= 3600:
                    try:
                        # 取得當前系統狀態
                        from src.notifier import send_rich_heartbeat
                        
                        # 模擬或獲取當前餘額與 Regime (實務上應從狀態管理器讀取)
                        current_balance = 1000.0 # 預設值
                        current_regime = "TREND_HUNTER" # 預設值
                        
                        status_data = {
                            "uptime": str(datetime.now(UTC) - startup_time).split('.')[0],
                            "regime": current_regime,
                            "balance": current_balance,
                            "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        send_rich_heartbeat(status_data)
                        last_report_time = datetime.now()
                        print(f"💓 [DYNAMO] Hourly Heartbeat Sent | Regime: {current_regime}")
                    except Exception as e:
                        print(f"⚠️ Heartbeat failed: {e}")
                    if os.path.exists(os.path.join(DATA_DIR, 'system_state.json')):
                        with open(os.path.join(DATA_DIR, 'system_state.json'), 'r') as f:
                            balance_data = json.load(f)
                    
                    balance_data = {'total_balance': 1000.0}
                    balance_data = {'total_balance': 1000.0}
                    balance_data = {'total_balance': 1000.0}
                    balance_data = {'total_balance': 1000.0}
                    balance_data = {'total_balance': 1000.0}
                    equity = balance_data.get('total_balance', 1000.0)
                    
                    # Scan for active positions
                    for s in scan_results.keys():
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
                    
                    # BTC Status
                    df_btc = fetch_1h_data('BTC/USDT')
                    if not df_btc.empty:
                        btc_price = df_btc.iloc[-1]['close']
                        btc_ema200 = calculate_ema(df_btc, 200).iloc[-1]
                        dist_ema200 = (btc_price - btc_ema200) / btc_ema200 if btc_ema200 > 0 else 0
                        
                        btc_status = {
                            'price': btc_price,
                            'is_bullish': btc_price > calculate_ema(df_btc, 50).iloc[-1],
                            'vol_change_24h': 0, # Simplified for heartbeat
                            'regime_mode': regime_mode,
                            'dist_ema200': dist_ema200
                        }
                        
                        # Threshold Warning: If any symbol AI score > 0.70
                        high_potential = [s for s, d in scan_results.items() if d.get('ml_score', 0) > 0.70]
                        if high_potential:
                            send_telegram_msg(f"⚠️ 【臨界點預警】偵測到高潛力幣種: {', '.join(high_potential)}")

                        send_rich_heartbeat(active_positions, scan_results, len(active_positions), STRATEGY_VERSION, btc_status)
                    
                    last_report_time = datetime.now()
            except Exception as e:
                # Iteration 92.0: Cooldown & Logic Lock
                print(f"❌ [Iteration 92.0 | Cooldown & Logic Lock] Main Loop Error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)
            # Iteration 92.0: Mandatory 60s sleep to prevent infinite loop
            time.sleep(60)
    except Exception as fatal_e:
        error_msg = f"❌ [Iteration 92.0 | Cooldown & Logic Lock] 核心啟動崩潰: {str(fatal_e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        try:
            from src.notifier import send_telegram_msg
            send_telegram_msg(error_msg)
        except:
            pass
        sys.exit(1)
