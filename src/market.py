import os
import sys
import time
import json
import traceback
import datetime
from datetime import datetime, UTC
import pandas as pd
import pandas_ta as ta
import ccxt
import certifi
import numpy as np
from dotenv import load_dotenv

# 🚀 [PATH HACK] 絕對路徑掛載
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

load_dotenv()

from src.notifier import send_telegram_msg
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel

STRATEGY_VERSION = "[H16_PREDATOR_V133.9_TRUTH]"

# 交易所初始化 (不再隱藏連線錯誤)
exchange = ccxt.binance({
    'enableRateLimit': True, 
    'timeout': 15000, 
    'options': {'defaultType': 'future'}
})

def fetch_1h_data(symbol):
    print(f"📡 [Network] Requesting {symbol}...")
    # 這裡故意不放 try-except，讓報錯直接噴到 pm2 logs
    ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=200)
    if not ohlcv:
        print(f"⚠️ [Data] {symbol} returned empty OHLCV")
        return pd.DataFrame()
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def run_strategy(ml_model):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    print(f"🔎 [Cycle] Scanning symbols: {symbols}")
    
    # 獲取基準 BTC 數據
    df_btc = fetch_1h_data('BTC/USDT')
    if df_btc.empty:
        print("❌ [Critical] BTC baseline missing!")
        return

    for s in symbols:
        print(f"🛠️ [Process] Analyzing {s}...")
        try:
            df = fetch_1h_data(s)
            if df.empty or len(df) < 100:
                print(f"⏩ [Skip] {s} insufficient data ({len(df)})")
                continue
            
            print(f"📈 [Feature] Calculating for {s}...")
            X = extract_features(df, df_btc)
            
            print(f"🤖 [Model] Predicting for {s}...")
            probs = ml_model.predict_proba(X.tail(1))
            score = float(probs[0][1])
            print(f"🎯 [Result] {s} Score: {score:.4f}")
            
            if score > 0.85:
                send_telegram_msg(f"🎯 訊號觸發: {s} | Score: {score:.4f}")
        except Exception:
            print(f"💥 [Error] Failed during {s} analysis:")
            traceback.print_exc() # 這是妳要的「真相」，不准裝死

if __name__ == "__main__":
    print(f"🔥 {STRATEGY_VERSION} Startup...")
    ml_model = CryptoMLModel()
    
    try:
        ml_model.load()
        print("✅ Model weights loaded.")
    except Exception:
        print("💥 [Model Error] Failed to load weights:")
        traceback.print_exc()
        sys.exit(1)

    send_telegram_msg(f"🚀 {STRATEGY_VERSION} 上線。")
    
    while True:
        print(f"\n💓 [Heartbeat] {datetime.now(UTC)} UTC")
        try:
            run_strategy(ml_model)
        except Exception:
            print("💥 [Main Loop Error] Fatal error in strategy cycle:")
            traceback.print_exc()
        
        print(f"😴 [Sleep] Waiting for next minute...")
        time.sleep(60)
