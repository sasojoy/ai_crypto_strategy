

import pandas as pd
from src.evaluate import fetch_backtest_data, run_evaluation
from src.report import create_github_issue
import os
import subprocess

def verify_and_deploy():
    top_3 = pd.read_csv('data/grid_search_results.csv')
    symbol = 'BTC/USDT'
    df_all = fetch_backtest_data(symbol, days=90)
    mid_point = len(df_all) // 2
    df_test = df_all.iloc[mid_point:].copy()
    
    best_combination = None
    max_test_score = -9999
    
    print("\n--- Starting OOS Verification ---")
    for idx, row in top_3.iterrows():
        # Run on Test data
        score, profit, wr, mdd, count = run_evaluation(
            df_test, 
            rsi_th=row['rsi_th'], 
            ema_f=row['ema_f'], 
            ema_s=row['ema_s'], 
            sl_mult=row['sl_mult'],
            macd_confirm=row['macd_confirm']
        )
        
        print(f"Combo {idx+1}: RSI={row['rsi_th']}, EMA_F={row['ema_f']}, EMA_S={row['ema_s']}, SL={row['sl_mult']}, MACD={row['macd_confirm']}")
        print(f"Test Score: {score:.2f} | Profit: ${profit:.2f}")
        
        if profit > 0 and score > max_test_score:
            max_test_score = score
            best_combination = row
            
    if best_combination is not None:
        print(f"\n✅ Best OOS Combination Found: {best_combination.to_dict()}")
        
        # Step 3: Create Report
        create_github_issue(
            rsi_th=best_combination['rsi_th'],
            ema_f=best_combination['ema_f'],
            ema_s=best_combination['ema_s'],
            sl_mult=best_combination['sl_mult'],
            oos_passed=True,
            macd_confirm=best_combination['macd_confirm']
        )
        
        # Step 4: Check for 20% improvement over Iteration 8
        # Iteration 8 Score was ~1817.50
        current_score = 1817.50
        if max_test_score > (current_score * 1.2):
            print(f"🚀 Score improvement > 20% ({max_test_score:.2f} vs {current_score:.2f}). Updating market.py...")
            update_market_py(best_combination)
            deploy_and_notify(max_test_score)
        else:
            print(f"ℹ️ Improvement ({max_test_score:.2f}) not enough for auto-deployment (> {current_score * 1.2:.2f} required).")
    else:
        print("❌ No combination passed OOS test with positive profit. Reporting failure...")
        # Report the best one from grid search even if it failed OOS
        best_gs = top_3.iloc[0]
        create_github_issue(
            rsi_th=best_gs['rsi_th'],
            ema_f=best_gs['ema_f'],
            ema_s=best_gs['ema_s'],
            sl_mult=best_gs['sl_mult'],
            oos_passed=False,
            macd_confirm=best_gs['macd_confirm']
        )

def update_market_py(combo):
    path = 'src/market.py'
    rsi = int(combo['rsi_th'])
    ema_f = int(combo['ema_f'])
    ema_s = int(combo['ema_s'])
    sl_mult = combo['sl_mult']
    macd_confirm = combo['macd_confirm']
    tp_mult = sl_mult * 2
    
    version_name = "Iteration 9 (MACD Enhanced)" if macd_confirm else "Iteration 9 (Optimized)"
    
    content = f"""import os
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

def log_data(timestamp, price, rsi, ema_s):
    log_file = 'data/history.csv'
    os.makedirs('data', exist_ok=True)
    data = {{'timestamp': [timestamp], 'price': [price], 'rsi': [rsi], 'ema_s': [ema_s]}}
    df = pd.DataFrame(data)
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)

def run_strategy():
    symbols = ['BTC/USDT', 'SOL/USDT']
    btc_price, btc_rsi = None, None
    
    for symbol in symbols:
        try:
            df = fetch_15m_data(symbol)
            df['rsi'] = calculate_rsi(df)
            df['ema_f'] = calculate_ema(df, {ema_f})
            df['ema_s'] = calculate_ema(df, {ema_s})
            df['atr'] = calculate_atr(df, 14)
            _, _, df['macd_hist'] = calculate_macd(df)
            df['atr_ma24h'] = df['atr'].rolling(96).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            if symbol == 'BTC/USDT':
                btc_price, btc_rsi = latest['close'], latest['rsi']
                log_data(latest['timestamp'], latest['close'], latest['rsi'], latest['ema_s'])
            
            volatility_ok = latest['atr'] <= (latest['atr_ma24h'] * 2)
            
            # MACD Confirmation
            macd_ok = True
            if {macd_confirm}:
                macd_ok = latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']
            
            # Optimized Strategy Logic (Auto-Iterated)
            if volatility_ok and macd_ok and \\
               latest['close'] > latest['ema_f'] and latest['ema_f'] > latest['ema_s'] and \\
               prev['rsi'] < {rsi} and latest['rsi'] > {rsi}:
                
                sl = latest['close'] - ({sl_mult} * latest['atr'])
                tp = latest['close'] + ({tp_mult} * latest['atr'])
                
                msg = (
                    f"🚀 [目標 100 萬] 自動疊代買入訊號 ({version_name})\\n"
                    f"----------------------------\\n"
                    f"幣種：{{symbol}}\\n"
                    f"價格：{{latest['close']:.2f}}\\n"
                    f"RSI：{{latest['rsi']:.2f}}\\n"
                    f"MACD Hist：{{latest['macd_hist']:.4f}}\\n"
                    f"止損：{{sl:.2f}} | 止盈：{{tp:.2f}}\\n"
                    f"----------------------------\\n"
                    f"參數：RSI={rsi}, EMA_F={ema_f}, EMA_S={ema_s}, SL={sl_mult}, MACD={macd_confirm}"
                )
                send_telegram_msg(msg)
                
        except Exception as e:
            print(f"Error: {{e}}")
    return btc_price, btc_rsi

if __name__ == "__main__":
    STRATEGY_VERSION = "{version_name}"
    last_heartbeat_time = 0
    send_telegram_msg(f"🤖 目標 100 萬監測站：啟動自動疊代版本 ({{STRATEGY_VERSION}})！")
    while True:
        try:
            btc_price, btc_rsi = run_strategy()
            current_time = time.time()
            if current_time - last_heartbeat_time >= 900:
                if btc_price:
                    send_telegram_msg(f"📊 定時回報\\nBTC: {{btc_price:.2f}} | RSI: {{btc_rsi:.2f}}\\n版本: {{STRATEGY_VERSION}}\\n狀態: 運行中")
                    last_heartbeat_time = current_time
        except Exception as e:
            print(f"Loop error: {{e}}")
        time.sleep(60)
"""
    with open(path, 'w') as f:
        f.write(content)

def deploy_and_notify(score):
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", f"Auto-upgrade strategy: Score {score:.2f}"])
    subprocess.run(["git", "push", "origin", "main"])
    print("✅ Deployment pushed to main.")

if __name__ == "__main__":
    verify_and_deploy()

