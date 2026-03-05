import os
import time
import ccxt
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from src.notifier import send_telegram_msg

# Load environment variables
load_dotenv()

def fetch_15m_data(symbol='BTC/USDT'):
    exchange = ccxt.binance()
    timeframe = '15m'
    limit = 300
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def log_data(timestamp, price, rsi, ema200):
    log_file = 'data/history.csv'
    os.makedirs('data', exist_ok=True)
    data = {'timestamp': [timestamp], 'price': [price], 'rsi': [rsi], 'ema200': [ema200]}
    df = pd.DataFrame(data)
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)

def run_strategy():
    symbols = ['BTC/USDT', 'SOL/USDT']
    now = datetime.now()
    btc_price, btc_rsi = None, None
    
    for symbol in symbols:
        try:
            df = fetch_15m_data(symbol)
            df['rsi'] = calculate_rsi(df)
            df['ema50'] = calculate_ema(df, 50)
            df['ema200'] = calculate_ema(df, 200)
            df['atr'] = calculate_atr(df, 14)
            
            # Volatility Warning: 24h (96 candles of 15m) Avg ATR
            df['atr_ma24h'] = df['atr'].rolling(96).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            if symbol == 'BTC/USDT':
                btc_price, btc_rsi = latest['close'], latest['rsi']
                log_data(latest['timestamp'], latest['close'], latest['rsi'], latest['ema200'])
            
            # Volatility Filter: ATR must not exceed 2x of 24h average
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            
            # Optimized Strategy Logic (Iteration 8)
            # 1. Dual Trend Filter: Price > EMA 50 AND EMA 50 > EMA 200
            # 2. RSI Hook: Prev < 30 AND Current > 30
            if volatility_ok and \
               latest['close'] > latest['ema50'] and latest['ema50'] > latest['ema200'] and \
               prev['rsi'] < 30 and latest['rsi'] > 30:
                
                sl = latest['close'] - (2 * latest['atr'])
                tp = latest['close'] + (4 * latest['atr'])
                
                msg = (
                    f"🚀 [目標 100 萬] 優化版買入訊號 (V8)\n"
                    f"----------------------------\n"
                    f"幣種：{symbol}\n"
                    f"價格：{latest['close']:.2f}\n"
                    f"RSI：{latest['rsi']:.2f}\n"
                    f"止損：{sl:.2f} | 止盈：{tp:.2f}\n"
                    f"----------------------------\n"
                    f"趨勢：雙均線多頭排列，強勢回調確認。"
                )
                send_telegram_msg(msg)
                
        except Exception as e:
            print(f"Error: {e}")
    return btc_price, btc_rsi

if __name__ == "__main__":
    last_heartbeat_time = 0
    send_telegram_msg("🤖 目標 100 萬監測站：啟動優化版循環 (V8)！")
    while True:
        try:
            btc_price, btc_rsi = run_strategy()
            current_time = time.time()
            if current_time - last_heartbeat_time >= 900:
                if btc_price:
                    send_telegram_msg(f"📊 定時回報\nBTC: {btc_price:.2f} | RSI: {btc_rsi:.2f}\n狀態: 運行中")
                    last_heartbeat_time = current_time
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)
