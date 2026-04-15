import os, sys, time, json, traceback, certifi
from datetime import datetime, UTC
import pandas as pd
import ccxt
from dotenv import load_dotenv

# 🚀 2026 GCE 環境鎖定
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
load_dotenv()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.notifier import send_telegram_msg
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel
from src.indicators import calculate_ema, calculate_atr

STRATEGY_VERSION = "[H16_PREDATOR_V1.3.0_ADAPTIVE_GUARD]"

REQUIRED_FEATURES = [
    'rsi', 'macd_hist', 'adx', 'atr_pct', 'vol_change_24h', 
    'volatility_24h', 'relative_strength_btc', 'btc_volatility_24h', 
    'dist_ema200', 'dist_ema20', 'bb_width', 'bb_percent_b', 
    'stoch_k', 'stoch_d', 'squeeze_index', 'macd_div', 
    'dist_sr_low', 'dist_sr_high', 'price_momentum'
]

exchange = ccxt.binance({'enableRateLimit': True, 'timeout': 15000, 'options': {'defaultType': 'future'}})
last_scores = {}
active_positions = {} # 追蹤持倉以實現 Adaptive Trailing

def get_ai_limit_price(side, current_price, score, atr, vol_24h, is_sqz):
    """🧠 AI 自適應掛單算法"""
    base_k = max(0.05, (1.0 - score) * 1.2)
    vol_adj = 1.0 + (vol_24h * 10)
    sqz_adj = 0.4 if is_sqz else 1.0
    final_k = base_k * vol_adj * sqz_adj
    offset = atr * final_k
    return current_price - offset if side == "LONG" else current_price + offset

def run_strategy(ml_model):
    global last_scores, active_positions
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    df_btc = fetch_data('BTC/USDT', '1h')
    if df_btc.empty: return

    for s in symbols:
        try:
            # 1. 獲取 1H 與 4H 數據 (Trend Confluence)
            df_1h = fetch_data(s, '1h')
            df_4h = fetch_data(s, '4h')
            if len(df_1h) < 200 or len(df_4h) < 200: continue
            
            current_price = df_1h['close'].iloc[-1]
            ema200_1h = calculate_ema(df_1h, 200).iloc[-1]
            ema200_4h = calculate_ema(df_4h, 200).iloc[-1]
            atr = calculate_atr(df_1h, 14).iloc[-1]
            
            # 2. Adaptive Trailing 邏輯 (主動鎖利)
            if s in active_positions:
                pos = active_positions[s]
                entry_price = pos['entry_price']
                side = pos['side']
                highest_price = max(pos.get('highest_price', current_price), current_price)
                pos['highest_price'] = highest_price
                
                # 漲幅達 1*ATR -> 移動至保本
                if side == "LONG" and (current_price - entry_price) >= pos['initial_atr']:
                    pos['stop_loss'] = max(pos['stop_loss'], entry_price)
                
                # 創新高 -> 跟隨止損 (1.5*ATR)
                if side == "LONG":
                    new_sl = highest_price - (1.5 * atr)
                    if new_sl > pos['stop_loss']:
                        pos['stop_loss'] = new_sl
                        send_telegram_msg(f"🛡️ 【Adaptive Guard】{s} 止損上移至 {new_sl:.2f}")
                
                # 檢查是否觸發止損
                if (side == "LONG" and current_price <= pos['stop_loss']) or \
                   (side == "SHORT" and current_price >= pos['stop_loss']):
                    pnl = (current_price / entry_price - 1) if side == "LONG" else (entry_price / current_price - 1)
                    send_telegram_msg(f"🚪 【出場】{s} 觸發移動止損\n收益: {pnl:.2%}")
                    del active_positions[s]
                    continue

            # 3. 特徵提取與 AI 評分
            X_all = extract_features(df_1h, df_btc)
            vol_24h = X_all['volatility_24h'].iloc[-1]
            bb_w = X_all['bb_width'].iloc[-1]
            bb_w_avg = X_all['bb_width'].rolling(50).mean().iloc[-1]
            is_squeezed = bb_w < (bb_w_avg * 0.8)
            
            X_input = X_all[REQUIRED_FEATURES].reindex(columns=REQUIRED_FEATURES).tail(1).fillna(0)
            base_score = float(ml_model.predict_proba(X_input)[0][1])
            ml_score = base_score - 0.15 if (df_1h['close'].diff(3).iloc[-1] > 0 and df_1h['volume'].diff(3).iloc[-1] < 0) else base_score
            
            # 4. 門檻與進場判定 (Trend Confluence)
            std_threshold = 0.82 if s in ['BTC/USDT', 'ETH/USDT'] else 0.88
            adj_threshold = std_threshold - 0.05 if is_squeezed else std_threshold
            
            side = None
            # 僅在 1H 與 4H 趨勢一致時進場
            if current_price > ema200_1h and current_price > ema200_4h and ml_score >= adj_threshold:
                side = "LONG"
            elif current_price < ema200_1h and current_price < ema200_4h and (1 - ml_score) >= adj_threshold:
                side = "SHORT"
            
            if side and s not in active_positions:
                limit_price = get_ai_limit_price(side, current_price, ml_score, atr, vol_24h, is_squeezed)
                discount_pct = abs(limit_price - current_price) / current_price
                # 模擬進場 (實戰中應等待成交)
                active_positions[s] = {
                    'side': side,
                    'entry_price': limit_price,
                    'stop_loss': limit_price - (2 * atr) if side == "LONG" else limit_price + (2 * atr),
                    'initial_atr': atr,
                    'highest_price': limit_price
                }
                send_telegram_msg(
                    f"🕵️ 【AI 狙擊進場】{STRATEGY_VERSION}\n標的: {s} | 方向: {side}\n埋伏價: {limit_price:.2f}\n趨勢: 1H/4H 共振 ✅"
                )
            print(f"📊 [{s}] Score: {ml_score:.4f} | 1H/4H Confluence: {current_price > ema200_1h and current_price > ema200_4h}")
        except Exception:
            traceback.print_exc()

def fetch_data(symbol, timeframe='1h'):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=500)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except: return pd.DataFrame()

if __name__ == "__main__":
    ml_model = CryptoMLModel()
    ml_model.load()
    while True:
        run_strategy(ml_model)
        time.sleep(60)
