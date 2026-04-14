import os
import sys
import time
import json
import traceback
import datetime
from datetime import datetime, UTC
import pandas as pd
import ccxt
import certifi
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


STRATEGY_VERSION = "[H16_PREDATOR_V133.9_FINAL]"


# 19 項標準特徵
REQUIRED_FEATURES = [
    'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
    'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
    'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
    'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
    'dist_sr_low', 'dist_sr_high', 'price_momentum'
]


exchange = ccxt.binance({'enableRateLimit': True, 'timeout': 15000, 'options': {'defaultType': 'future'}})


def fetch_1h_data(symbol, limit=500):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=limit)
        if not ohlcv: return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except: return pd.DataFrame()


def run_strategy(ml_model):
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    df_btc = fetch_1h_data('BTC/USDT')
    if df_btc.empty: return


    for s in symbols:
        try:
            df = fetch_1h_data(s)
            if len(df) < 200: continue
            
            X_all = extract_features(df, df_btc)
            if X_all.empty: continue


            # 防禦性取列：確保只取存在的列，且順序正確
            X_input = X_all.reindex(columns=REQUIRED_FEATURES).tail(1).fillna(0)
            
            # 偵錯輸出
            score = float(ml_model.predict_proba(X_input)[0][1])
            print(f"🎯 [Result] {s} | RSI: {X_input['rsi'].iloc[0]:.2f} | Score: {score:.4f}")
            
            if score > 0.85:
                send_telegram_msg(f"🎯 訊號: {s} | AI: {score:.4f}")
        except Exception:
            print(f"💥 [Error] {s} Failed:")
            traceback.print_exc()


if __name__ == "__main__":
    print(f"🔥 {STRATEGY_VERSION} Online")
    ml_model = CryptoMLModel()
    ml_model.load()
    
    while True:
        print(f"\n💓 [Heartbeat] {datetime.now(UTC)} UTC")
        run_strategy(ml_model)
        time.sleep(60)
