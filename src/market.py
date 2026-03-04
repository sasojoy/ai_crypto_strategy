
import ccxt
import pandas as pd

def fetch_15m_data():
    exchange = ccxt.binance()
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

def calculate_ema(df, period=20):
    return df['close'].ewm(span=period, adjust=False).mean()

def main():
    try:
        df = fetch_15m_data()
        df['rsi'] = calculate_rsi(df)
        df['ema20'] = calculate_ema(df, 20)
        
        latest_rsi = df['rsi'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        latest_ema20 = df['ema20'].iloc[-1]
        
        if latest_close > latest_ema20 and latest_rsi < 35:
            print(f"【強勢回調買入信號】當前價格 ({latest_close}) > EMA 20 ({latest_ema20:.2f}) 且 RSI ({latest_rsi:.2f}) < 35。")
        else:
            print(f"目前價格: {latest_close}, EMA 20: {latest_ema20:.2f}, RSI: {latest_rsi:.2f}")
            print("尚未符合強勢回調買入信號。")
            
    except Exception as e:
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    main()
