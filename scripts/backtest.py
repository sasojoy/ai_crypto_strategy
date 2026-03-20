import pandas as pd
import numpy as np
import joblib
import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.indicators import *
from src.features import extract_features
import ccxt

def run_backtest(symbol='SOL/USDT', days=30):
    print(f"🚀 Starting Backtest for {symbol} (Last {days} days)...")
    
    # 1. Load Data
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days+10)).isoformat())
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', since=since, limit=1000)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # BTC Data for relative strength
    btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', since=since, limit=1000)
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'], unit='ms')
    btc_df.set_index('timestamp', inplace=True)

    # 2. Extract Features
    print("📊 Extracting features...")
    features_df = extract_features(df.reset_index(), btc_df.reset_index())
    
    # 3. Load Model
    model_path = 'models/rf_model.joblib'
    if not os.path.exists(model_path):
        # Try relative path if absolute fails
        model_path = os.path.join(os.path.dirname(__file__), '../models/rf_model.joblib')
    
    print(f"🤖 Loading model from {model_path}...")
    model = joblib.load(model_path)
    
    # 4. Generate Predictions
    # Align features with original df
    df = df.iloc[-len(features_df):].copy()
    predictions = model.predict_proba(features_df)[:, 1]
    df['ai_score'] = predictions

    # 5. Trading Logic (Simple)
    trades = []
    position = None
    entry_price = 0
    entry_time = None
    entry_score = 0
    
    threshold = 0.55 # Entry threshold
    exit_threshold = 0.48 # Exit threshold
    
    for i in range(len(df)):
        current_row = df.iloc[i]
        current_time = df.index[i]
        current_price = current_row['close']
        score = current_row['ai_score']
        
        if position is None:
            if score > threshold:
                position = 'LONG'
                entry_price = current_price
                entry_time = current_time
                entry_score = score
        else:
            if score < exit_threshold:
                pnl = (current_price - entry_price) / entry_price * 100
                trades.append({
                    'Entry Time': entry_time.strftime('%Y-%m-%d %H:%M'),
                    'Exit Time': current_time.strftime('%Y-%m-%d %H:%M'),
                    'Entry Price': entry_price,
                    'Exit Price': current_price,
                    'AI Confidence': f"{entry_score:.2%}",
                    'PnL %': f"{pnl:.2f}%",
                    'raw_pnl': pnl
                })
                position = None

    # 6. Results Summary
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        total_pnl = trades_df['raw_pnl'].sum()
        win_rate = (trades_df['raw_pnl'] > 0).mean() * 100
        
        # Max Drawdown calculation
        cumulative_pnl = (1 + trades_df['raw_pnl'] / 100).cumprod()
        peak = cumulative_pnl.cummax()
        drawdown = (cumulative_pnl - peak) / peak
        max_dd = drawdown.min() * 100
        
        print("\n" + "="*40)
        print(f"📈 BACKTEST RESULTS - {symbol}")
        print("="*40)
        print(f"Total Trades: {len(trades_df)}")
        print(f"Total Return: {total_pnl:.2f}%")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Max Drawdown: {max_dd:.2f}%")
        print("="*40)
        
        print("\nFirst 5 Trades:")
        print(trades_df.head(5).drop(columns=['raw_pnl']).to_string(index=False))
        
        trades_df.to_csv('backtest_results_v72.csv', index=False)
        print(f"\n✅ Full trade list saved to backtest_results_v72.csv")
        
        # Iteration 74.0: Output results.json for CI/CD
        import json
        results = {
            'total_trades': len(trades_df),
            'total_return': float(total_pnl),
            'win_rate': float(win_rate),
            'max_drawdown': float(max_dd),
            'profit_factor': float(trades_df[trades_df['raw_pnl'] > 0]['raw_pnl'].sum() / abs(trades_df[trades_df['raw_pnl'] < 0]['raw_pnl'].sum())) if any(trades_df['raw_pnl'] < 0) else 10.0
        }
        with open('results.json', 'w') as f:
            json.dump(results, f)
        print(f"✅ CI/CD Results saved to results.json")
    else:
        print("❌ No trades executed during backtest period.")
        # Create empty results for CI
        with open('results.json', 'w') as f:
            json.dump({'win_rate': 0, 'profit_factor': 0}, f)

if __name__ == "__main__":
    run_backtest()
