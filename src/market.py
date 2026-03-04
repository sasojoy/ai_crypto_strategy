
import os
from datetime import datetime
from dotenv import load_dotenv
import ccxt
import pandas as pd
from src.notifier import send_telegram_msg

# Load environment variables from .env file
load_dotenv()

def fetch_15m_data(symbol='BTC/USDT'):
    # 僅使用公共 API 獲取市場數據，移除下單相關邏輯
    exchange = ccxt.binance()
    timeframe = '15m'
    limit = 300 # 增加 limit 以確保 EMA 200 計算準確
    
    # Fetch OHLCV data
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    
    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi



def log_data(timestamp, price, rsi, ema20, ema50):
    log_file = 'data/history.csv'
    data = {
        'timestamp': [timestamp],
        'price': [price],
        'rsi': [rsi],
        'ema20': [ema20],
        'ema50': [ema50]
    }
    df = pd.DataFrame(data)
    
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)


def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def main():
    symbols = ['BTC/USDT', 'SOL/USDT']
    for symbol in symbols:
        try:
            print(f"正在分析 {symbol}...")
            df = fetch_15m_data(symbol)
            df['rsi'] = calculate_rsi(df)
            df['ema200'] = calculate_ema(df, 200)
            df['atr'] = calculate_atr(df, 14)
            
            latest_rsi = df['rsi'].iloc[-1]
            prev_rsi = df['rsi'].iloc[-2]
            latest_close = df['close'].iloc[-1]
            latest_ema200 = df['ema200'].iloc[-1]
            latest_atr = df['atr'].iloc[-1]
            latest_timestamp = df['timestamp'].iloc[-1]

            # 實作日誌存檔 (保留舊格式以相容)
            log_data(latest_timestamp, latest_close, latest_rsi, 0, 0)
            
            # 右側勾頭邏輯：
            # 1. 價格 > EMA 200 (大趨勢向上)
            # 2. 前一根 RSI < 35 (曾進入超賣)
            # 3. 當前 RSI 突破 40 (動能回升)
            if latest_close > latest_ema200 and prev_rsi < 35 and latest_rsi > 40:
                # 計算實戰點位
                sl_price = latest_close - (3 * latest_atr)
                tp_price = latest_close + (6 * latest_atr)
                
                msg = (
                    f"🚀 [目標 100 萬] 強勢回調買入訊號\n"
                    f"----------------------------\n"
                    f"幣種：{symbol}\n"
                    f"當前價格：{latest_close:.2f}\n"
                    f"RSI 數值：{latest_rsi:.2f} (勾頭確認)\n"
                    f"建議止損：{sl_price:.2f}\n"
                    f"建議止盈：{tp_price:.2f}\n"
                    f"----------------------------\n"
                    f"均線狀態：價格位於 EMA 200 之上，趨勢看漲。"
                )
                print(msg)
                send_telegram_msg(msg)
            else:
                print(f"{symbol} 目前價格: {latest_close:.2f}, RSI: {latest_rsi:.2f}, EMA200: {latest_ema200:.2f}")
                print("尚未符合右側勾頭買入條件。")
                
        except Exception as e:
            print(f"分析 {symbol} 時發生錯誤: {e}")

if __name__ == "__main__":
    main()
