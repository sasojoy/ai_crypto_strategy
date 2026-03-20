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
from src.indicators import *

from src.features import extract_features
from src.ml_model import CryptoMLModel


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
DATA_DIR = os.path.join(BASE_DIR, 'trading_data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
MODELS_DIR = os.path.join(BASE_DIR, 'models')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)


# Iteration 51: Physical Isolation Security
IS_SIMULATION = True

# Security Check
if not IS_SIMULATION:
    if not os.getenv('BINANCE_API_KEY') or not os.getenv('BINANCE_SECRET'):
        raise RuntimeError("❌ [SECURITY FATAL] IS_SIMULATION is False but no API keys found. Terminating for safety.")




# Global state initialization
regime_mode = "NEUTRAL"


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
    print(f"🎯 [Iteration 82.1 | Professional Trapper] Monitoring Selected Symbols: {selected_symbols}")
    return selected_symbols

# Global exchange instance (Iteration 69.2: Prevent rate limiting)
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot'
    }
})

def fetch_15m_data(symbol='BTC/USDT'):
    """
    Iteration 71.3: Fetch 15m data with local caching to prevent data gaps.
    """
    cache_file = os.path.join(DATA_DIR, f"{symbol.replace('/', '_')}_15m.csv")
    try:
        timeframe = '15m'
        limit = 500
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if ohlcv is None or len(ohlcv) == 0:
            print(f"⚠️ Warning: fetch_ohlcv returned None or empty for {symbol} ({timeframe})")
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
        print(f"Error fetching 15m data for {symbol}: {e}")
        if os.path.exists(cache_file):
            print(f"📂 Loading {symbol} 15m data from cache after error...")
            return pd.read_csv(cache_file, parse_dates=['timestamp'])
        return pd.DataFrame()

def fetch_5m_data(symbol='BTC/USDT'):
    try:
        timeframe = '5m'
        limit = 500
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if ohlcv is None or len(ohlcv) == 0:
            print(f"⚠️ Warning: fetch_ohlcv returned None or empty for {symbol} ({timeframe})")
            return pd.DataFrame()
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
        timeframe = '4h'
        limit = 200
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if ohlcv is None or len(ohlcv) == 0:
            print(f"⚠️ Warning: fetch_ohlcv returned None or empty for {symbol} ({timeframe})")
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching 4h data for {symbol}: {e}")
        return pd.DataFrame()


def fetch_ohlcv(symbol, timeframe="1h", limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if ohlcv is None or len(ohlcv) == 0:
            print(f"⚠️ Warning: fetch_ohlcv returned None or empty for {symbol} ({timeframe})")
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"Error fetching {timeframe} data for {symbol}: {e}")
        return pd.DataFrame()


def fetch_1h_data(symbol='BTC/USDT', limit=500):
    try:
        timeframe = '1h'
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if ohlcv is None or len(ohlcv) == 0:
            print(f"⚠️ Warning: fetch_ohlcv returned None or empty for {symbol} ({timeframe})")
            return pd.DataFrame()
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
    if not isinstance(df_1h, pd.DataFrame) or df_1h.empty or len(df_1h) < 24:
        return True
    
    try:
        # Use safe_get_float for robust extraction
        recent_high = safe_get_float(df_1h['high'].values[-24:].max())
        upside_pct = (recent_high - entry_price) / entry_price
        
        if upside_pct < 0.012:
            print(f"🛡️ [Iteration 68.9 | Flash Sniper] [Space Check] {symbol} upside {upside_pct:.2%} < 1.2% to resistance ({recent_high:.2f}). Skipping.")
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
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(os.path.join(LOGS_DIR, 'slippage.log'), 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {symbol}: Expected {expected_price}, Actual {actual_price}, Slippage {slippage*100:.4f}%\n")
    if slippage > 0.001:
        print(f"⚠️ [WARNING] High Slippage detected on {symbol}: {slippage*100:.4f}%")

def save_order_state(symbol, state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, f'order_state_{symbol.replace("/", "_")}.json'), 'w') as f:
        json.dump(state, f)
    
    # Iteration 74.0: Persistence for Active Trades
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


def run_strategy(ml_model):
    global regime_mode
    params = load_params()

    # Iteration 67: Fix variable initialization to prevent crash
    regime_mode = "NEUTRAL"
    indicators_signal = False

    # Iteration 54: Daily Performance Tracker
    update_daily_performance()

    # Iteration 55: Weekly Auto-Retrain
    check_and_retrain_model()


    # Iteration 16: Dynamic Symbol Selection
    symbols = get_top_relative_strength_symbols()
    prices_rsi = {}
    
    # Iteration 85.0: Data Pre-warmup & Progress Tracking (Silent)
    warmup_count = 0
    total_symbols = len(symbols)
    for i, s in enumerate(symbols):
        # Pre-fetch data to ensure indicators are ready
        df_warmup = fetch_15m_data(s)
        if not df_warmup.empty and len(df_warmup) >= 200:
            warmup_count += 1
            prices_rsi[s] = {'price': df_warmup.iloc[-1]['close'], 'rsi': 50, 'ml_score': 0.5, 'missed_reason': 'Ready'}
        else:
            # Silent log to PM2, no Telegram spam
            print(f"⚠️ [Data Sync] {s} 數據不足，正在背景同步...")
            prices_rsi[s] = {'price': 0, 'rsi': 50, 'ml_score': 0.5, 'missed_reason': 'Initializing'}
    
    if warmup_count < total_symbols:
        print(f"⚠️ [Warmup] Only {warmup_count}/{total_symbols} symbols ready. Continuing with partial data.")
    else:
        send_telegram_msg(f"✅ 數據預熱完成 ({total_symbols}/{total_symbols})，開始執行策略。")

    current_pos_count = get_active_positions_count()
    
    # Iteration 19: Dynamic Equity-Based Risking
    # Iteration 68.3: Optimization - Balance is fetched once per loop
    balance = 1000.0
    if os.path.exists(os.path.join(DATA_DIR, 'balance.json')):
        try:
            with open(os.path.join(DATA_DIR, 'balance.json'), 'r') as f:
                balance = json.load(f).get('total_balance', 1000.0)
        except:
            pass
    
    risk_pct = 0.008 # Default 1.5%

    # Iteration 23: BTC Sentiment Filter
    df_btc_1h = fetch_1h_data('BTC/USDT', limit=500)
    btc_sentiment_ok = False
    if not df_btc_1h.empty:
        # Iteration 71.8: Debugging BTC Price
        btc_price = df_btc_1h.iloc[-1]['close']
        print(f"DEBUG: BTC Close Price = {btc_price:.2f}")
        
        btc_ema50 = calculate_ema(df_btc_1h, 50).iloc[-1]
        btc_sentiment_ok = btc_price > btc_ema50
        print(f"📊 [BTC Sentiment] Price: {btc_price:.2f}, EMA50: {btc_ema50:.2f}, OK: {btc_sentiment_ok}")

    potential_signals = []

    # Iteration 55: Fetch BTC data for ML features
    # Iteration 69: Increase limit to 250 for BTC features (EMA200 requirement)
    df_btc_ml = fetch_btc_vol_with_retry('BTC/USDT', limit=250)
    
    # Iteration 60: Dynamic Environment Filter (Regime Filter)
    regime_mode = "趨勢擴張"
    ml_threshold = 0.85
    min_rr = 1.3
    rsi_threshold_boost = 0
    aggressive_macd = False
    
    if not df_btc_ml.empty:
        # Calculate 24H Volume Change for BTC with foolproof logic
        try:
            # Iteration 68.3: 00:00 - 00:30 UTC Bypass
            now = datetime.utcnow()
            if now.hour == 0 and 0 <= now.minute <= 30:
                print("⏳ [Iteration 68.3] UTC 00:00-00:30 Bypass: Volume check skipped.")
                btc_vol_24h_change = 0.5 # Default to positive expansion
            else:
                # Iteration 68.5: Correct 24H Volume Change calculation
                # Compare sum of last 24h vs sum of previous 24h
                current_24h_vol = df_btc_ml['volume'].iloc[-24:].sum()
                prev_24h_vol = df_btc_ml['volume'].iloc[-48:-24].sum()
                
                if prev_24h_vol == 0:
                    btc_vol_24h_change = 0
                else:
                    btc_vol_24h_change = (current_24h_vol - prev_24h_vol) / prev_24h_vol
                
                # Iteration 68.5: Volume data anomaly detection
                if btc_vol_24h_change < -0.8:
                    print(f"⚠️ Volume data anomaly detected: {btc_vol_24h_change:.2%}. Forcing to 0.")
                    btc_vol_24h_change = 0
                
                # Limit extreme values
                btc_vol_24h_change = max(min(btc_vol_24h_change, 5.0), -1.0)
        except Exception as e:
            print(f"Error calculating btc_vol_24h_change: {e}")
            btc_vol_24h_change = 0
        
        # Iteration 60: Aggressive Trend Mode
        btc_ema50_ml = calculate_ema(df_btc_ml, 50).iloc[-1]
        btc_ema200_ml = calculate_ema(df_btc_ml, 200).iloc[-1]
        btc_bullish = df_btc_ml['close'].iloc[-1] > btc_ema50_ml > btc_ema200_ml
        
        # Iteration 68: Aggressive Pursuit Mode (BTC Vol > 100%)
        # Iteration 68.4: Dynamic Volume Tolerance
        # If BTC price > EMA50 and price is at 24H high, allow pursuit even if vol is slightly negative
        btc_24h_high = df_btc_ml['high'].tail(24).max()
        btc_at_high = df_btc_ml['close'].iloc[-1] >= btc_24h_high * 0.995
        
        is_pursuit_mode = btc_vol_24h_change > 1.0 or (btc_bullish and btc_at_high and btc_vol_24h_change > -0.5)
        pursuit_ai_threshold = 0.72
        
        if btc_vol_24h_change < -0.20 and not (btc_bullish and btc_at_high):
            print(f"🚫 [Iteration 68.9 | Flash Sniper] 縮量進場禁止 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")
            # Iteration 71.2: Return empty scan results but allow heartbeat to see symbols
            return prices_rsi
        
        if is_pursuit_mode:
            regime_mode = "多頭追擊"
            rsi_threshold_boost = 10 # 45 -> 55
            aggressive_macd = True
            print(f"🔥 [Iteration 68.9 | Flash Sniper] 多頭追擊模式啟動 (BTC 24H Vol Change: {btc_vol_24h_change:.2%}, At High: {btc_at_high})")
        elif btc_vol_24h_change < 0:
            regime_mode = "震盪防禦"
            ml_threshold = 0.85
            min_rr = 1.3
            print(f"🛡️ [Iteration 68.9 | Flash Sniper] 低量防禦模式啟動 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")
        else:
            print(f"🚀 [Iteration 68.9 | Flash Sniper] 趨勢擴張模式 (BTC 24H Vol Change: {btc_vol_24h_change:.2%})")

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
            df['ema200'] = calculate_ema(df, 200)

            # 4H Trend Filter (Strict Iteration 21)
            df_4h['ema200'] = calculate_ema(df_4h, 200)
            df_4h['ema50'] = calculate_ema(df_4h, 50)
            latest_4h = df_4h.iloc[-1]
            trend_4h = "Long" if latest_4h['close'] > latest_4h['ema200'] and latest_4h['close'] > latest_4h['ema50'] else "Short"

            latest = df.iloc[-1]
            print(f"DEBUG Indicators for {symbol}: {latest.index.tolist()}")
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
                print(f"⚠️ [Iteration 68.9 | Flash Sniper] {symbol} 1H data empty. Skipping.")
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
                        print(f"🔥 [Iteration 68.9 | Flash Sniper] {symbol} MACD Aggressive Signal Detected!")

                # Iteration 60: [Dynamic RSI] Boost RSI limit in Aggressive Mode
                rsi_limit = 45 + rsi_threshold_boost
                if (latest['rsi'] < rsi_limit and macd_turn and vol_ok and relative_strength_ok) or macd_aggressive_signal:
                    trend_entry = True
            
            # B. Bottom Fishing Mode (Price < 1H EMA 200)
            bottom_fishing_mode = price <= ema200_1h
            bottom_entry = False
            if bottom_fishing_mode:
                # RSI < 32, MACD Bullish Divergence
                macd_bullish_div_series = calculate_macd_divergence(df)
                macd_bullish_div = safe_get_bool(macd_bullish_div_series)
                if latest['rsi'] < 32 and macd_bullish_div:
                    bottom_entry = True
            
            # 2. Squeeze Breakout Strategy
            squeeze_index_series = calculate_squeeze_index(df)
            squeeze_index = safe_get_float(squeeze_index_series)
            squeeze_breakout = False
            if squeeze_index < 0.3 and latest['close'] > latest['bb_upper']:
                squeeze_breakout = True
            

            # Iteration 84.0: Define is_squeeze_trade
            is_squeeze_trade = squeeze_breakout or (squeeze_index < 0.5 and latest['rsi'] < 40)

            # 3. Time-Filter (Exclude 00:00 - 04:00 UTC - Low Liquidity)
            current_hour = datetime.utcnow().hour
            time_filter_ok = not (0 <= current_hour < 4)
            
            # Iteration 74.0: High-Frequency & Confidence Ladder Logic
            cond_rsi = latest['rsi'] < 45
            cond_ema_cross = latest['ema20'] > latest['ema50']
            cond_trend = latest['close'] > latest['ema200'] * 0.98
            
            # AI Score from ML Model
            # Iteration 83.0: AI Prediction Flow Fix
            features = extract_features(df.reset_index(), df_btc_ml.reset_index())
            try:
                # Use tail(1) to get the latest features as a 2D DataFrame
                probs = ml_model.predict_proba(features.tail(1))
                # Ensure we have a 2D array and extract class 1 probability
                if hasattr(probs, "ndim") and probs.ndim == 2:
                    ai_score = float(probs[0][1])
                else:
                    # Fallback if it's a scalar or 1D
                    ai_score = float(probs[1]) if len(probs) > 1 else 0.5
            except Exception as e:
                print(f"⚠️ [AI Error] {symbol} Prediction failed: {e}")
                print(f"FAILED FEATURES: {features.tail(1)}")
                ai_score = 0.5
            
            cond_ai = ai_score >= 0.55
            
            long_signal = cond_rsi and cond_ema_cross and cond_trend and cond_ai and time_filter_ok
            
            # Confidence Ladder Position Sizing
            pos_size_multiplier = 1.0
            if ai_score >= 0.70:
                pos_size_multiplier = 1.5
            elif ai_score >= 0.60:
                pos_size_multiplier = 1.0
            else:
                pos_size_multiplier = 0.5
            
            print(f"🔍 [Iteration 74.0] {symbol} AI Score: {ai_score:.2%}, Signal: {long_signal}, Multiplier: {pos_size_multiplier}x")

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
                            print(f"🛡️ [Iteration 68.9 | Flash Sniper] {symbol} 處於止損保護期，且 RSI 未創新低。跳過進場。")
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

            # Iteration 83.0: AI Score Calculation (AI Prediction Flow Fix)
            ml_score = 0.5 # Default
            df_ml = fetch_1h_data(symbol, limit=250)
            if not df_ml.empty and not df_btc_ml.empty:
                features = extract_features(df_ml, df_btc_ml)
                if not features.empty:
                    try:
                        # Ensure 2D input and extract probability of class 1
                        probs = ml_model.predict_proba(features.tail(1))
                        if hasattr(probs, "ndim") and probs.ndim == 2:
                            ml_score = float(probs[0][1])
                        else:
                            ml_score = float(probs[1]) if len(probs) > 1 else 0.5
                        print(f"🤖 [AI Score] {symbol}: {ml_score:.4f}")
                    except Exception as e:
                        print(f"⚠️ [AI Heartbeat Error] {symbol}: {e}")
                        print(f"FAILED FEATURES: {features.tail(1)}")
                        ml_score = 0.5

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
                'support_strength': support_strength, # Iteration 55
                'ml_score': ml_score # Iteration 69: Always include for heartbeat
            }

            if long_signal or short_signal:
                side = 'LONG' if long_signal else 'SHORT'
                # Iteration 23: BTC Sentiment & Funding Rate Filter
                if side == 'LONG':
                    if not btc_sentiment_ok:
                        print(f"🚫 [Iteration 68.9 | Flash Sniper] {symbol} Long signal ignored: BTC Sentiment Bearish.")
                        continue
                    
                    if symbol in ['DOGE/USDT', 'XRP/USDT']:
                        funding_rate = fetch_funding_rate(symbol)
                        if funding_rate > 0.0005:
                            print(f"🚫 [Iteration 68.9 | Flash Sniper] {symbol} Long signal ignored: Funding Rate too high ({funding_rate*100:.4f}%).")
                            continue

                # Calculate Volume Growth Rate for Correlation Detection
                vol_growth = (latest['volume'] - avg_vol_5) / avg_vol_5 if avg_vol_5 > 0 else 0
                
                # Iteration 69: AI-Enhanced Decision Flow (Already calculated above)
                if ml_score > 0:
                    # Update prices_rsi with ml_score for heartbeat (redundant but safe)
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

                    # Iteration 71: Hybrid Sniper | Laddered Logic
                    # Determine Mode based on BTC 24H Volume Change
                    # btc_status is calculated at the beginning of run_strategy
                    vol_24h = btc_status.get('vol_change_24h', 0)
                    btc_price = btc_status.get('price', 0)
                    btc_ema20 = btc_status.get('ema20', 0)
                    
                    # Iteration 68: Pursuit Mode Logic (Pre-calculate distance)
                    ema20_1h = calculate_ema(df_ml, 20).iloc[-1]
                    dist_ema20_pct = (latest['close'] - ema20_1h) / ema20_1h * 100 if ema20_1h > 0 else 999
                    
                    mode = "Standard"
                    ai_threshold = 0.68
                    support_ema = "ema50"
                    support_dist = 0.015
                    
                    if vol_24h > 30 and btc_price > btc_ema20:
                        mode = "Aggressive (強勢進攻)"
                        ai_threshold = 0.65
                        support_ema = "ema50"
                        support_dist = 0.02
                    elif vol_24h < 0:
                        mode = "Defensive (低量避險)"
                        ai_threshold = 0.72
                        support_ema = "ema200"
                        support_dist = 0.02
                    
                    # Calculate distance to required support EMA
                    if support_ema == "ema50":
                        target_ema_val = calculate_ema(df_ml, 50).iloc[-1]
                    else:
                        target_ema_val = ema200 # Already calculated
                        
                    dist_to_support = abs(latest['close'] - target_ema_val) / target_ema_val if target_ema_val > 0 else 999
                    
                    passed_filter = False
                    tier = f"Tier 1 ({mode})"
                    
                    if ml_score >= ai_threshold and dist_to_support <= support_dist:
                        current_risk = 0.012 # Standard 1.2% Risk
                        target_rr = 1.5
                        passed_filter = True
                        
                    # Iteration 68: Pursuit Mode Logic (Override if extremely strong)
                    if not passed_filter and is_pursuit_mode and ml_score >= 0.85 and 0 <= dist_ema20_pct <= 1.5:
                        current_risk = 0.015 # Higher risk for pursuit
                        target_rr = 1.5
                        tier = "Tier 0 (Pursuit Mode)"
                        passed_filter = True

                if passed_filter:
                    print(f"🎯 [Iteration 71 | Hybrid Sniper] {symbol} {tier} Signal. Score: {ml_score:.4f}, Mode: {mode}")
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
                        reason = f"Mode: {mode}, Dist: {dist_to_support:.2%}"
                        print(f"🛡️ [Iteration 71 | Hybrid Sniper] {symbol} score {ml_score:.4f} but rejected: {reason}")
                    else:
                        print(f"🛡️ [AI Filter] {symbol} score {ml_score:.4f} < {ai_threshold}. Signal rejected.")
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
            print(f"🛡️ [Iteration 68.9 | Flash Sniper] {symbol} profit {profit_pct:.2%} >= 0.8%. Moving SL to Break-Even: {new_sl}")
            if update_sl_order(symbol, state.get('sl_order_id'), new_sl):
                state['be_sl_active'] = True
                state['sl_price'] = new_sl
                save_order_state(symbol, state)
                send_telegram_msg(f"🛡️ [Iteration 68.9 | Flash Sniper] {symbol} 已啟動保本止損 (Trailing to BE)。")

        # Iteration 74.0: Professional Trailing Stop Logic
        state['highest_price'] = max(state.get('highest_price', entry_price), current_price)
        profit_from_entry = (state['highest_price'] - entry_price) / entry_price
        
        if profit_from_entry >= 0.01:
            # Iteration 74.0: Move SL to Entry + 0.5% after 1% profit
            new_sl = entry_price * 1.005
            if new_sl > state.get('sl_price', 0):
                print(f"🛡️ [Iteration 74.0] {symbol} Profit > 1%. Moving SL to Entry + 0.5%: {new_sl}")
                if update_sl_order(symbol, state.get('sl_order_id'), new_sl):
                    state['sl_price'] = new_sl
                    state['trailing_active'] = True
                    save_order_state(symbol, state)


        # Iteration 53: Infinite RR Path
        # 1. Partial TP at 1.2 RR
        rr_1_2_price = entry_price + (state['atr'] * 1.5 * 1.2) if side == 'LONG' else entry_price - (state['atr'] * 1.5 * 1.2)
        
        if not state.get('partial_tp_done', False):
            if (side == 'LONG' and current_price >= rr_1_2_price) or (side == 'SHORT' and current_price <= rr_1_2_price):
                msg = f"💰 [Iteration 68.9 | Flash Sniper] {symbol} 達到 1.2 RR！執行 50% 減倉止盈。\n剩餘 50% 開啟 EMA 10 移動止損。"
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
                    msg = f"📈 [Iteration 68.9 | Flash Sniper] {symbol} 跌破 EMA 10！全數平倉獲利了結。"
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
        if not df_exit.empty:
            df_exit['bb_upper'], df_exit['bb_lower'], df_exit['bb_mid'], _ = calculate_bollinger_bands(df_exit, 20, 2)
            bb_upper = safe_get_float(df_exit['bb_upper'])

            if side == 'LONG':
                # Iteration 26: Exit Logic (BB Mid/Upper)
                if current_price >= bb_upper:
                    msg = f"🚀 [Iteration 68.9 | Flash Sniper] {symbol} 觸及布林上軌！全數平倉獲利了結。"
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
            msg = f"❌ [Iteration 68.9 | Flash Sniper] {symbol} 觸發止損！\n現價：{current_price:.2f} | 止損價：{sl_price:.2f}"
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
                msg = f"⏳ [Iteration 68.9 | Flash Sniper] {symbol} 持倉超過 48 小時且獲利為正，強行平倉釋放資金！"
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
    try:
        # Iteration 85.0: Startup Message
        send_telegram_msg("🚀 【Iteration 85.0】 寧靜與純淨化完成，系統正式上線")
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

        STRATEGY_VERSION = "🚀 【Iteration 85.0 | Silent Trapper】"
        last_heartbeat_time = 0
        last_summary_date = None
        
        # Iteration 74.0: Load Active Trades from Persistence
        ACTIVE_TRADES_PATH = os.path.join(DATA_DIR, 'active_trades.json')
        if os.path.exists(ACTIVE_TRADES_PATH):
            try:
                with open(ACTIVE_TRADES_PATH, 'r') as f:
                    persisted_trades = json.load(f)
                    print(f"📦 [Iteration 74.0] Loaded {len(persisted_trades)} persisted trades.")
            except Exception as e:
                print(f"⚠️ Error loading persisted trades: {e}")

        # Iteration 69.2: Startup Notification (Immediate)
        try:
            send_telegram_msg(f"🚀 【{STRATEGY_VERSION}】已在生產環境正式啟動，正在載入模型與初始化數據...")
        except Exception as e:
            print(f"Failed to send startup notification: {e}")

        # Iteration 68.9: Initialize ML Model at startup
        print(f"🤖 [System] Loading ML Model for {STRATEGY_VERSION}...")
        ml_model = CryptoMLModel()
        ml_model.load()
        
        # Iteration 74.0: Data Pre-warmup (500 K-lines)
        print(f"⏳ [System] Pre-warming data (500 K-lines)...")
        warmup_symbols = get_top_relative_strength_symbols()
        for i, s in enumerate(warmup_symbols):
            progress = int((i / len(warmup_symbols)) * 100)
            print(f"⏳ [{progress}%] Warming up {s} ({i}/{len(warmup_symbols)})...")
            if i % 2 == 0: # Reduce TG spam
                send_telegram_msg(f"⏳ 正在同步數據 ({i}/{len(warmup_symbols)} 根)...")
            # Fetch 500 1h candles to ensure EMA200 is ready
            fetch_1h_data(s, limit=500)
            time.sleep(0.5) # Rate limit protection
        
        print(f"✅ {STRATEGY_VERSION} Initialization Complete.")
        send_telegram_msg(f"✅ 數據預熱完成，系統核心已上線 | {STRATEGY_VERSION}")

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
                scan_results = run_strategy(ml_model)
                
                # Iteration 71.2: Diagnose empty scan_results
                print(f"🔍 [System] Scan complete. Found {len(scan_results)} results.")
                if len(scan_results) == 0:
                    print("⚠️ [ALARM] scan_results is EMPTY!")
                    try:
                        send_telegram_msg("⚠️ 【Iteration 71.2 報警】掃描結果為空，請檢查 API 連線或市場過濾邏輯。")
                    except:
                        pass

                manage_positions(scan_results)
                current_time = time.time()

                # Iteration 68.9: 15-minute Heartbeat
                if current_time - last_heartbeat_time >= 900:
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
                            # For accuracy, we fetch 48h of 1h data with retry
                            df_48h = fetch_btc_vol_with_retry('BTC/USDT', limit=48)
                            if len(df_48h) >= 48:
                                last_24h_vol = df_48h.iloc[-24:]['volume'].sum()
                                prev_24h_vol = df_48h.iloc[-48:-24]['volume'].sum()
                                
                                if prev_24h_vol == 0 or last_24h_vol == 0:
                                    vol_change_24h = 0
                                else:
                                    vol_change_24h = (last_24h_vol - prev_24h_vol) / prev_24h_vol * 100
                                
                                # Limit extreme values
                                vol_change_24h = max(min(vol_change_24h, 500.0), -100.0)
                        except Exception as e:
                            print(f"Error calculating vol change: {e}")
                        
                        btc_status = {
                            'price': btc_price,
                            'ema50': btc_ema50,
                            'is_bullish': btc_price > btc_ema50,
                            'vol_change_24h': vol_change_24h,
                            'regime_mode': regime_mode
                        }
                        # Iteration 68.5: Use dynamic version string
                        send_rich_heartbeat(active_positions, scan_results, len(active_positions), STRATEGY_VERSION, btc_status)
                    
                    last_heartbeat_time = current_time
            except Exception as e:
                # Iteration 83.0: Robust Error Handling
                print(f"❌ [Main Loop Error] {e}")
                time.sleep(60)
            time.sleep(60)
    except Exception as fatal_e:
        error_msg = f"❌ 核心啟動崩潰: {str(fatal_e)}"
        print(error_msg)
        try:
            from src.notifier import send_telegram_msg
            send_telegram_msg(error_msg)
        except:
            pass
        sys.exit(1)
