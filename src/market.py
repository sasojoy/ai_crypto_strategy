
import os
from dotenv import load_dotenv
import ccxt
import pandas as pd
from src.notifier import send_telegram_message

# Load environment variables from .env file
load_dotenv()

def fetch_15m_data():
    # Initialize exchange with API keys if available
    api_key = os.getenv('BINANCE_API_KEY')
    secret_key = os.getenv('BINANCE_SECRET_KEY')
    
    config = {}
    if api_key and secret_key:
        config['apiKey'] = api_key
        config['secret'] = secret_key
        
    exchange = ccxt.binance(config)
    symbol = 'BTC/USDT'
    timeframe = '15m'
    limit = 100
    
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

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def main():
    try:
        df = fetch_15m_data()
        df['rsi'] = calculate_rsi(df)
        df['ema20'] = calculate_ema(df, 20)
        df['ema50'] = calculate_ema(df, 50)
        
        latest_rsi = df['rsi'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        latest_ema20 = df['ema20'].iloc[-1]
        latest_ema50 = df['ema50'].iloc[-1]
        
        # 趨勢過濾邏輯：
        # 1. 價格 > EMA 20 (短期強勢)
        # 2. EMA 20 > EMA 50 (長期趨勢向上)
        # 3. RSI < 35 (回調超賣)
        if latest_close > latest_ema20 and latest_ema20 > latest_ema50 and latest_rsi < 35:
            msg = f"【強勢回調買入預警】\n價格: {latest_close}\nEMA20: {latest_ema20:.2f}\nEMA50: {latest_ema50:.2f}\nRSI: {latest_rsi:.2f}"
            print(msg)
            send_telegram_message(msg)
        else:
            print(f"目前價格: {latest_close}, RSI: {latest_rsi:.2f}, EMA20: {latest_ema20:.2f}, EMA50: {latest_ema50:.2f}")
            print("尚未符合強勢回調買入條件。")
            
    except Exception as e:
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    main()
