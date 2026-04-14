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

# 🚀 [PATH HACK] 
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

STRATEGY_VERSION = "[H16_PREDATOR_V133.9_STABLE]"

exchange = ccxt.binance({
    'enableRateLimit': True, 
    'timeout': 15000, 
    'options': {'defaultType': 'future'}
})

def fetch_1h_data(symbol, limit=500):
    print(f"📡 [Network] Fetching {symbol} (limit={limit})...")
    ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=limit)
    if not ohlcv: return pd.DataFrame()
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_strategy(ml_model):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    print(f"🔎 [Cycle] Scanning {len(symbols)} symbols...")
    
    # 增加獲取量到 500 根，確保指標計算完整
    df_btc = fetch_1h_data('BTC/USDT', limit=500)
    if df_btc.empty: return

    for s in symbols:
        try:
            df = fetch_1h_data(s, limit=500)
            if len(df) < 200:
                print(f"⏩ [Skip] {s} data too short.")
                continue
            
            # 特徵計算
            X = extract_features(df, df_btc)
            
            # 偵錯日誌：檢查最後一筆特徵是否有 NaN
            last_features = X.tail(1)
            if last_features.isnull().values.any():
                print(f"⚠️ [Data Check] {s} features contain NaNs! Filling with 0.")
                last_features = last_features.fillna(0)

            # 印出前 3 個特徵樣本，確認數據不是全 0
            sample = last_features.iloc[0].to_dict()
            sample_short = {k: round(v, 4) for k, v in list(sample.items())[:3]}
            print(f"📊 [Feature Sample] {s}: {sample_short}...")

            # 進行預測
            probs = ml_model.predict_proba(last_features)
            score = float(probs[0][1])
            print(f"🎯 [Result] {s} Score: {score:.4f}")
            
            if score > 0.88: # 稍微提高門檻
                send_telegram_msg(f"🎯 訊號觸發: {s} | Score: {score:.4f}")
                
        except Exception:
            print(f"💥 [Error] {s} failed:")
            traceback.print_exc()

if __name__ == "__main__":
    print(f"🔥 {STRATEGY_VERSION} Startup...")
    ml_model = CryptoMLModel()
    ml_model.load()
    
    while True:
        print(f"\n💓 [Heartbeat] {datetime.now(UTC)} UTC")
        run_strategy(ml_model)
        print(f"😴 [Sleep] Waiting for 60s...")
        time.sleep(60)
