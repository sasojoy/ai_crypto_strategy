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

from src.notifier import send_telegram_msg, send_rich_heartbeat
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel

STRATEGY_VERSION = "[H16_PREDATOR_V133.9_PRO]"
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
    cycle_results = {}
    
    df_btc = fetch_1h_data('BTC/USDT')
    if df_btc.empty: return {}

    for s in symbols:
        try:
            df = fetch_1h_data(s)
            if len(df) < 200: continue
            
            X_all = extract_features(df, df_btc)
            if X_all.empty: continue

            X_input = X_all.reindex(columns=REQUIRED_FEATURES).tail(1).fillna(0)
            score = float(ml_model.predict_proba(X_input)[0][1])
            
            # 記錄結果供儀表板使用
            cycle_results[s] = {
                'score': score,
                'rsi': float(X_input['rsi'].iloc[0])
            }
            
            print(f"🎯 [Result] {s} | RSI: {cycle_results[s]['rsi']:.2f} | Score: {score:.4f}")
            
            if score > 0.85:
                send_telegram_msg(f"🎯 【進場訊號】\n標的: {s}\nAI 分數: {score:.4f}\n版本: {STRATEGY_VERSION}")
        except Exception:
            print(f"💥 [Error] {s} Failed:")
            traceback.print_exc()
            
    return cycle_results

if __name__ == "__main__":
    print(f"🔥 {STRATEGY_VERSION} Operational")
    ml_model = CryptoMLModel()
    ml_model.load()
    
    startup_time = datetime.now(UTC)
    last_report_time = 0 # 初始為 0 確保啟動時先報一次
    
    while True:
        now_ts = time.time()
        print(f"\n💓 [Heartbeat] {datetime.now(UTC)} UTC")
        
        # 執行掃描並取得結果
        current_scores = run_strategy(ml_model)
        
        # --- 每小時儀表板回報邏輯 ---
        if now_ts - last_report_time >= 3600:
            try:
                # 找出目前最高分的幣種
                if current_scores:
                    top_symbol = max(current_scores, key=lambda x: current_scores[x]['score'])
                    top_score = current_scores[top_symbol]['score']
                    dist_to_target = max(0, 0.85 - top_score)
                    
                    report_msg = (
                        f"📊 【H16 戰情儀表板】\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"⏱ 運行時間: {str(datetime.now(UTC) - startup_time).split('.')[0]}\n"
                        f"🤖 系統狀態: 運作中 (Healthy)\n"
                        f"🏆 當前最高: {top_symbol}\n"
                        f"📈 AI 分數: {top_score:.4f}\n"
                        f"🎯 距開倉目標: {dist_to_target:.4f}\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"💡 提示: 分數達到 0.85 將自動執行。"
                    )
                    send_telegram_msg(report_msg)
                    last_report_time = now_ts
                    print("✅ [Dashboard] Hourly report sent to Telegram.")
            except Exception as e:
                print(f"❌ [Dashboard Error] {e}")

        time.sleep(60)
