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
    limit = 300  # Ensure enough data for EMA 200
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
    data = {
        'timestamp': [timestamp],
        'price': [price],
        'rsi': [rsi],
        'ema200': [ema200]
    }
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
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Analyzing {symbol}...")
            df = fetch_15m_data(symbol)
            df['rsi'] = calculate_rsi(df)
            df['ema200'] = calculate_ema(df, 200)
            df['atr'] = calculate_atr(df, 14)
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            if symbol == 'BTC/USDT':
                btc_price, btc_rsi = latest['close'], latest['rsi']
                log_data(latest['timestamp'], latest['close'], latest['rsi'], latest['ema200'])
            
            # Strategy Logic (Iteration 4: RSI Hook)
            if latest['close'] > latest['ema200'] and prev['rsi'] < 35 and latest['rsi'] > 40:
                sl = latest['close'] - (3 * latest['atr'])
                tp = latest['close'] + (6 * latest['atr'])
                
                msg = (
                    f"🚀 [目標 100 萬] 強勢回調買入訊號\n"
                    f"----------------------------\n"
                    f"幣種：{symbol}\n"
                    f"當前價格：{latest['close']:.2f}\n"
                    f"RSI 數值：{latest['rsi']:.2f} (勾頭確認)\n"
                    f"建議止損：{sl:.2f}\n"
                    f"建議止盈：{tp:.2f}\n"
                    f"----------------------------\n"
                    f"均線狀態：價格位於 EMA 200 之上，趨勢看漲。"
                )
                print(msg)
                send_telegram_msg(msg)
                
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    return btc_price, btc_rsi

if __name__ == "__main__":
    last_heartbeat_time = 0
    send_telegram_msg("🤖 目標 100 萬監測站：啟動循環監控！")
    
    while True:
        try:
            btc_price, btc_rsi = run_strategy()
            
            current_time = time.time()
            if current_time - last_heartbeat_time >= 900:
                if btc_price is not None:
                    heartbeat_msg = (
                        f"📊 [目標 100 萬] 定時狀態回報\n"
                        f"----------------------------\n"
                        f"幣種：BTC/SOL\n"
                        f"BTC 價格：{btc_price:.2f} (RSI: {btc_rsi:.2f})\n"
                        f"狀態：監控中 (24/7 循環已啟動)"
                    )
                    send_telegram_msg(heartbeat_msg)
                    last_heartbeat_time = current_time
                
        except Exception as e:
            print(f"Main loop error: {e}")
            
        time.sleep(60)
