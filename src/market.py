import os
import sys
import time
import json
import datetime
from datetime import datetime, UTC
import pandas as pd
import pandas_ta as ta
import ccxt
import certifi
import numpy as np
from dotenv import load_dotenv

# 🚀 [PATH HACK] 確保路徑正確
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

STRATEGY_VERSION = "[H16_PREDATOR_V133.9_VERBOSE]"

# 初始化交易所
exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})

def fetch_1h_data(symbol):
    try:
        print(f"⏳ [Data] 正在獲取 {symbol} K線...")
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=200)
        if not ohlcv:
            print(f"⚠️ [Data] {symbol} 回傳空數據")
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        print(f"✅ [Data] {symbol} 獲取成功: {len(df)} 筆")
        return df
    except Exception as e:
        print(f"❌ [Data Error] {symbol}: {e}")
        return pd.DataFrame()

def run_strategy(ml_model):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    print(f"🔍 [Strategy] 開始掃描循環，幣種: {symbols}")
    
    df_btc = fetch_1h_data('BTC/USDT')
    if df_btc.empty:
        print("🛑 [Strategy] BTC 核心數據缺失，跳過此循環")
        return {}

    for s in symbols:
        print(f"--- 處理 {s} ---")
        df = fetch_1h_data(s)
        if df.empty or len(df) < 100:
            print(f"⚠️ [Strategy] {s} 數據長度不足 ({len(df)})，跳過")
            continue
        
        print(f"🧠 [ML] 正在為 {s} 計算特徵...")
        try:
            X = extract_features(df, df_btc)
            if X.empty:
                print(f"⚠️ [ML] {s} 特徵計算結果為空")
                continue
            
            print(f"🔮 [ML] 正在進行 AI 預測...")
            probs = ml_model.predict_proba(X.tail(1))
            score = float(probs[0][1])
            print(f"📊 [ML] {s} 分數: {score:.4f}")
            
            if score > 0.85:
                print(f"🎯 [Signal] {s} 觸發進場訊號！")
                send_telegram_msg(f"🎯 偵測到 {s} 高分訊號: {score:.4f}")
        except Exception as e:
            print(f"❌ [Logic Error] 處理 {s} 時發生錯誤: {e}")
            
    return {"status": "finished"}

if __name__ == "__main__":
    print(f"🔥 {STRATEGY_VERSION} 啟動中...")
    ml_model = CryptoMLModel()
    ml_model.load()
    print("✅ 模型載入完成")
    
    send_telegram_msg(f"🚀 {STRATEGY_VERSION} 系統已就緒，開始獵殺。")
    
    while True:
        try:
            print(f"\n💓 [Heartbeat] {datetime.now(UTC)} UTC")
            run_strategy(ml_model)
            print("🏁 [Cycle] 循環結束，進入冷卻。")
            time.sleep(60)
        except Exception as e:
            print(f"🚨 [Fatal Error] 主循環崩潰: {e}")
            time.sleep(60)
