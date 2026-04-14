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

# [PATH HACK]
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

STRATEGY_VERSION = "[H16_PREDATOR_V133.9_PRO]"

# 模型需要的精確特徵清單 (順序必須嚴格對齊訓練時期)
REQUIRED_FEATURES = [
    'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
    'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
    'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
    'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
    'dist_sr_low', 'dist_sr_high', 'price_momentum'
]

exchange = ccxt.binance({
    'enableRateLimit': True, 
    'timeout': 15000, 
    'options': {'defaultType': 'future'}
})

def fetch_1h_data(symbol, limit=500):
    ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=limit)
    if not ohlcv: return pd.DataFrame()
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_strategy(ml_model):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    print(f"🔎 [Cycle] Scanning {len(symbols)} symbols...")
    
    df_btc = fetch_1h_data('BTC/USDT', limit=500)
    if df_btc.empty: return

    for s in symbols:
        try:
            df = fetch_1h_data(s, limit=500)
            if len(df) < 200: continue
            
            # 1. 提取特徵
            X_all = extract_features(df, df_btc)
            
            # 2. 精確過濾模型需要的特徵並確保順序
            # 這是解決分數異常的關鍵：只餵 AI 認識的東西
            X_input = X_all[REQUIRED_FEATURES].tail(1)
            
            # 3. 診斷日誌：印出真正的技術指標
            indicator_sample = {
                'RSI': round(X_input['rsi'].iloc[0], 2),
                'MACD': round(X_input['macd_hist'].iloc[0], 4),
                'ADX': round(X_input['adx'].iloc[0], 2)
            }
            print(f"📊 [Metrics] {s}: {indicator_sample}")

            # 4. 預測
            probs = ml_model.predict_proba(X_input)
            score = float(probs[0][1])
            print(f"🎯 [Result] {s} AI Score: {score:.4f}")
            
            if score > 0.85:
                send_telegram_msg(f"🎯 訊號觸發: {s} | Score: {score:.4f}")
                
        except Exception:
            print(f"💥 [Error] {s} failed:")
            traceback.print_exc()

if __name__ == "__main__":
    print(f"🔥 {STRATEGY_VERSION} Operational")
    ml_model = CryptoMLModel()
    ml_model.load()
    
    while True:
        print(f"\n💓 [Heartbeat] {datetime.now(UTC)} UTC")
        run_strategy(ml_model)
        print(f"😴 [Sleep] Cycle complete.")
        time.sleep(60)
