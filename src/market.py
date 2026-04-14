import os
import sys
import time
import certifi
import json
import shutil
import datetime
from datetime import datetime, timedelta, UTC

# 🚀 [PATH HACK] 確保專案根目錄在 sys.path 中，解決 ModuleNotFoundError: src
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import pandas_ta as ta
import ccxt
import numpy as np
from dotenv import load_dotenv

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
import json
import shutil
import datetime
from datetime import datetime, timedelta, UTC
import pandas as pd
import pandas_ta as ta
import ccxt
import numpy as np
from dotenv import load_dotenv

# 動態設定環境變數，解決 SSL 憑證 OSError
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# Load environment variables
load_dotenv()

# Path Definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
MODELS_DIR = os.path.join(BASE_DIR, 'models')

for d in [DATA_DIR, LOGS_DIR, CONFIG_DIR, MODELS_DIR]:
    os.makedirs(d, exist_ok=True)

# Notifier Imports (Moved down to ensure environment is set)
from src.notifier import send_telegram_msg, send_kill_switch_alert, send_rich_heartbeat, send_entry_notification, send_hourly_audit, send_daily_performance
from src.logger import log_trade
from src.indicators import calculate_bollinger_bands, calculate_ema
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel
from src.strategy.logic import DualTrackStrategy

STRATEGY_VERSION = "[H16_PREDATOR_V133.9_FINAL]"
IS_SIMULATION = False
WATCH_ONLY = False

# Initialize Exchange
exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
if os.getenv('BINANCE_API_KEY') and os.getenv('BINANCE_SECRET'):
    exchange.apiKey = os.getenv('BINANCE_API_KEY')
    exchange.secret = os.getenv('BINANCE_SECRET')
else:
    WATCH_ONLY = True

def safe_get_float(obj, index=-1):
    try:
        if hasattr(obj, 'iloc'): return float(obj.iloc[index])
        if hasattr(obj, 'values'): return float(obj.values[index])
        return float(obj)
    except: return 0.0

def fetch_1h_data(symbol='BTC/USDT', limit=500):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"❌ Error fetching {symbol}: {e}")
        return pd.DataFrame()

def execute_trade(symbol, side, qty, price, atr, params, ml_score=0, reason=""):
    fee_buffer = 0.002 if symbol == 'SOL/USDT' else 0.001
    tp_price = price * (1 + params.get('tp_pct', 0.05) + fee_buffer)
    sl_price = price * (1 - params.get('sl_pct', 0.02))
    
    msg = f"🚀 [{side.upper()}] {symbol} at {price:.2f}\nAI Score: {ml_score:.4f}\nReason: {reason}"
    send_telegram_msg(msg)
    return True

def run_strategy(ml_model):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT', 'FET/USDT', 'ARB/USDT']
    df_btc = fetch_1h_data('BTC/USDT')
    if df_btc.empty: return {}

    for s in symbols:
        try:
            df = fetch_1h_data(s)
            if df.empty or len(df) < 200: continue
            
            X = extract_features(df, df_btc)
            if X.empty: continue
            
            probs = ml_model.predict_proba(X.tail(1))
            score = float(probs[0][1])
            
            if score > 0.85:
                execute_trade(s, 'Long', 100, df['close'].iloc[-1], 0, {}, score, "AI High Confidence")
        except Exception as e:
            print(f"Error in {s}: {e}")
    return {"status": "scan_complete"}

if __name__ == "__main__":
    send_telegram_msg(f"🚀 {STRATEGY_VERSION} 寧靜重建完成，系統正式上線")
    ml_model = CryptoMLModel()
    ml_model.load()
    
    while True:
        try:
            print(f"💓 [Heartbeat] {datetime.now(UTC)} UTC")
            run_strategy(ml_model)
            time.sleep(60)
        except Exception as e:
            print(f"❌ Main Loop Error: {e}")
            time.sleep(60)
