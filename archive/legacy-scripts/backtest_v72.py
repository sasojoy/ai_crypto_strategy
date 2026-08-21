import pandas as pd
import numpy as np
import joblib
import os
import sys
from datetime import datetime, timedelta
import ccxt

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.indicators import *
from src.features import extract_features

def run_backtest(symbols=['BTC/USDT', 'ETH/USDT', 'SOL/USDT'], days=180):
    print(f"🚀 Starting Backtest Scheme C for {symbols} (Last {days} days)...")
    
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days+20)).isoformat())
    
    print("📥 Fetching BTC data...")
    btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', since=since, limit=4500)
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'], unit='ms')
    btc_df.set_index('timestamp', inplace=True)

    all_trades = []
    model = joblib.load('models/rf_model.joblib')
    
    for symbol in symbols:
        print(f"\n🔍 Processing {symbol}...")
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', since=since, limit=4500)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        df['rsi'] = calculate_rsi(df)
        df['ema200'] = calculate_ema(df, 200)
        df['macd_div'] = calculate_macd_divergence(df)
        _, _, macd_hist = calculate_macd(df)
        df['macd_hist'] = macd_hist

        features_df = extract_features(df.reset_index(), btc_df.reset_index())
        predictions = model.predict_proba(features_df)[:, 1]
        
        df = df.iloc[-len(features_df):].copy()
        df['ai_score'] = predictions

        position = None
        entry_price = 0
        entry_time = None
        entry_score = 0
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            curr_time = df.index[i]
            curr_price = row['close']
            
            if position is None:
                # SCHEME C ENTRY
                cond_rsi = row['rsi'] < 40 # Slightly relaxed from 35 to find entries
                cond_div = row['macd_div'] > 0
                dist_ema200 = (row['close'] - row['ema200']) / row['ema200']
                cond_ema = (row['close'] < row['ema200']) and (abs(dist_ema200) < 0.07)
                cond_squeeze = (row['macd_hist'] > prev_row['macd_hist'])
                cond_ai = row['ai_score'] >= 0.60 # Slightly relaxed from 0.62
                
                if cond_rsi and cond_div and cond_ema and cond_squeeze and cond_ai:
                    position = 'LONG'
                    entry_price = curr_price
                    entry_time = curr_time
                    entry_score = row['ai_score']
            else:
                # SCHEME C EXIT
                pnl = (curr_price - entry_price) / entry_price
                if pnl >= 0.025 or pnl <= -0.015 or row['rsi'] > 65:
                    all_trades.append({
                        'Symbol': symbol,
                        'Entry Time': entry_time.strftime('%Y-%m-%d %H:%M'),
                        'Exit Time': curr_time.strftime('%Y-%m-%d %H:%M'),
                        'Entry Price': entry_price,
                        'Exit Price': curr_price,
                        'AI Confidence': f"{entry_score:.2%}",
                        'PnL %': f"{pnl*100:.2f}%",
                        'raw_pnl': pnl * 100
                    })
                    position = None

    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        print("\n" + "="*40)
        print(f"🏆 BACKTEST RESULTS - SCHEME C (180 DAYS)")
        print("="*40)
        print(f"Total Trades: {len(trades_df)}")
        print(f"Win Rate: {(trades_df['raw_pnl'] > 0).mean():.2%}")
        print(f"Total Return: {trades_df['raw_pnl'].sum():.2f}%")
        print("="*40)
        print("\nFirst 5 Trades:")
        print(trades_df.head(5).drop(columns=['raw_pnl']).to_string(index=False))
        trades_df.to_csv('backtest_results_scheme_c.csv', index=False)
    else:
        print("\n❌ No trades found even with relaxed Scheme C.")

if __name__ == "__main__":
    run_backtest()
