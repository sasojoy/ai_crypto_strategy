import os
import time
import ccxt
import pandas as pd
import json
from datetime import datetime
from dotenv import load_dotenv
from src.notifier import send_telegram_msg

# Load environment variables
load_dotenv()

def load_params():
    with open('config/params.json', 'r') as f:
        return json.load(f)

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

def calculate_macd(df, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

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

def get_active_positions_count():
    """
    獲取當前活躍持倉數量。
    在實際生產環境中，這應該對接交易所 API。
    """
    # 模擬邏輯：此處應為實際持倉查詢
    return 0 

def run_strategy():
    params = load_params()
    symbols = ['BTC/USDT', 'SOL/USDT', 'ETH/USDT']
    now = datetime.now()
    prices_rsi = {}

    # 獲取當前總持倉數
    current_pos_count = get_active_positions_count()

    for symbol in symbols:
        try:
            df = fetch_15m_data(symbol)
            df['rsi'] = calculate_rsi(df)
            df['ema_f'] = calculate_ema(df, params['ema_f'])
            df['ema_s'] = calculate_ema(df, params['ema_s'])
            df['atr'] = calculate_atr(df, 14)
            _, _, df['macd_hist'] = calculate_macd(df)

            df['atr_ma24h'] = df['atr'].rolling(96).mean()
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            prices_rsi[symbol] = (latest['close'], latest['rsi'])

            if symbol == 'BTC/USDT':
                log_data(latest['timestamp'], latest['close'], latest['rsi'], latest['ema_s'])

            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            macd_ok = True
            if params.get('macd_confirm', True):
                macd_ok = latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']

            # 策略開倉邏輯
            if volatility_ok and macd_ok and                latest['close'] > latest['ema_f'] and latest['ema_f'] > latest['ema_s'] and                prev['rsi'] < params['rsi_th'] and latest['rsi'] > params['rsi_th']:

                # 🛡️ 總倉位風控攔截
                if current_pos_count >= 3:
                    print(f"[Global Risk] Max exposure reached ({current_pos_count}/3). Order for {symbol} suppressed.")
                    continue

                sl = latest['close'] - (params['sl_mult'] * latest['atr'])
                tp = latest['close'] + (params['tp_mult'] * latest['atr'])

                msg = (
                    f"🚀 [目標 100 萬] 自動化買入訊號 ({params['version']})\n"
                    f"----------------------------\n"
                    f"幣種：{symbol}\n"
                    f"價格：{latest['close']:.2f}\n"
                    f"RSI：{latest['rsi']:.2f}\n"
                    f"MACD Hist：{latest['macd_hist']:.4f}\n"
                    f"止損：{sl:.2f} | 止盈：{tp:.2f}\n"
                    f"----------------------------\n"
                    f"趨勢：雙均線多頭 + MACD 動能確認。"
                )
                send_telegram_msg(msg)

        except Exception as e:
            print(f"Error: {e}")
    return prices_rsi

if __name__ == "__main__":
    STRATEGY_VERSION = "V8.2-Risk-Controlled"
    last_heartbeat_time = 0
    send_telegram_msg(f"🤖 目標 100 萬監測站：啟動優化版循環 ({STRATEGY_VERSION})！")
    while True:
        try:
            prices_rsi = run_strategy()
            current_time = time.time()
            if current_time - last_heartbeat_time >= 900:
                if prices_rsi:
                    report = "📊 定時回報\n"
                    for symbol, (price, rsi) in prices_rsi.items():
                        report += f"{symbol}: {price:.2f} | RSI: {rsi:.2f}\n"
                    report += f"版本: {STRATEGY_VERSION}\n狀態: 運行中"
                    send_telegram_msg(report)
                    last_heartbeat_time = current_time
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)
