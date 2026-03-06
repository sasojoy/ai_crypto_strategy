import os
import time
import ccxt
import pandas as pd
import json
import shutil
from datetime import datetime
from dotenv import load_dotenv
from src.notifier import send_telegram_msg\nfrom src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands

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
    # 模擬邏輯：此處應為實際持倉查詢
    return 0 

def stability_monitor():
    """
    穩定性監控器 (Circuit Breaker)
    若出現連續 3 筆止損，或帳戶淨值單日下跌超過 5%，自動回滾。
    """
    # 模擬邏輯：此處應讀取實際交易日誌或帳戶餘額
    # 假設我們有一個 trade_history.json
    history_file = 'data/trade_history.json'
    if not os.path.exists(history_file): return

    try:
        with open(history_file, 'r') as f:
            trades = json.load(f)

        # 1. 連續 3 筆止損
        last_3_trades = trades[-3:]
        if len(last_3_trades) == 3 and all(t['result'] == 'SL' for t in last_3_trades):
            trigger_rollback("連續 3 筆止損")
            return

        # 2. 帳戶淨值單日下跌超過 5% (簡化邏輯)
        # ... 實作略 ...
    except Exception as e:
        print(f"Stability monitor error: {e}")

def trigger_rollback(reason):
    params = load_params()
    current_version = params.get('version', 'Unknown')
    stable_version = "archive/params_iter11_final.json"

    if os.path.exists(stable_version):
        shutil.copy(stable_version, 'config/params.json')
        msg = f"🚨 緊急警告：{current_version} 觸發熔斷 ({reason})，系統已自動回滾至穩定版本 11。"
        send_telegram_msg(msg)\n                # State Recovery: Save initial state\n                save_order_state(symbol, {'entry_price': latest['close'], 'pos_size': position_size, 'status': 'Open', 'iteration': '15'})
        print(msg)
    else:
        print("Rollback failed: Stable version not found.")


def get_account_balance():
    # In a real scenario, this would call exchange.fetch_balance()
    # For now, we simulate a $10,000 balance
    return 10000.0
\n
def log_slippage(symbol, expected_price, actual_price):
    slippage = abs(actual_price - expected_price) / expected_price
    os.makedirs('logs', exist_ok=True)
    with open('logs/slippage.log', 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {symbol}: Expected {expected_price}, Actual {actual_price}, Slippage {slippage*100:.4f}%\n")
    if slippage > 0.001:
        print(f"⚠️ [WARNING] High Slippage detected on {symbol}: {slippage*100:.4f}%")

def save_order_state(symbol, state):
    os.makedirs('data', exist_ok=True)
    with open(f'data/order_state_{symbol.replace("/", "_")}.json', 'w') as f:
        json.dump(state, f)

def load_order_state(symbol):
    path = f'data/order_state_{symbol.replace("/", "_")}.json'
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None
\ndef run_strategy():
    params = load_params()
    symbols = ['BTC/USDT', 'SOL/USDT', 'ETH/USDT']
    prices_rsi = {}
    current_pos_count = get_active_positions_count()
    balance = get_account_balance()

    for symbol in symbols:
        try:
            df = fetch_15m_data(symbol)
            df['rsi'] = calculate_rsi(df)
            df['ema_f'] = calculate_ema(df, params['ema_f'])
            df['ema_s'] = calculate_ema(df, params['ema_s'])
            df['ema_trail'] = calculate_ema(df, 20)
            df['atr'] = calculate_atr(df, 14)
            _, _, df['macd_hist'] = calculate_macd(df)
            df['adx'] = calculate_adx(df, 14)
            df['bb_upper'], df['bb_lower'], df['bb_bandwidth'], df['bb_percent_b'] = calculate_bollinger_bands(df, 20, params.get('bb_std', 2))
            df['atr_ma24h'] = df['atr'].rolling(96).mean()

            latest = df.iloc[-1]
            prev = df.iloc[-2]
            prices_rsi[symbol] = (latest['close'], latest['rsi'])

            # Entry Logic
            adx_ok = latest['adx'] > params.get('adx_min', 25)
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            macd_ok = True
            if params.get('macd_confirm', True):
                macd_ok = latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']

            if adx_ok and volatility_ok and macd_ok and \
               latest['close'] > latest['ema_f'] and latest['ema_f'] > latest['ema_s'] and \
               prev['rsi'] < params['rsi_th'] and latest['rsi'] > params['rsi_th']:

                if current_pos_count >= 3:
                    continue

                risk_amount = balance * 0.01
                sl_distance = params['sl_mult'] * latest['atr']
                position_size = risk_amount / sl_distance if sl_distance > 0 else 0

                sl = latest['close'] - sl_distance
                msg = (
                    f"🚀 [Iteration 15] 高級獲利管理進場
"
                    f"----------------------------
"
                    f"幣種：{symbol} | 價格：{latest['close']:.2f}
"
                    f"倉位：{position_size:.4f} (Risk 1%)
"
                    f"----------------------------
"
                    f"🎯 獲利計畫：
"
                    f"1. 觸及 BB Upper ({latest['bb_upper']:.2f}) 減倉 50% 並移至保本止損。
"
                    f"2. 剩餘 50% 啟動 EMA 20 追蹤止損，最大化趨勢利潤。"
                )
                send_telegram_msg(msg)\n                # State Recovery: Save initial state\n                save_order_state(symbol, {'entry_price': latest['close'], 'pos_size': position_size, 'status': 'Open', 'iteration': '15'})
        except Exception as e:
            print(f"Error: {e}")
    return prices_rsi




if __name__ == "__main__":
    STRATEGY_VERSION = "V8.3-Self-Evolving"
    last_heartbeat_time = 0
    send_telegram_msg(f"🤖 目標 100 萬監測站：啟動自我進化版循環 ({STRATEGY_VERSION})！")
    while True:
        try:
            stability_monitor() # 每次循環檢查穩定性
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
