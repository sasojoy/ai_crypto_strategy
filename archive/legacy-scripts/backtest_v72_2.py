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

def run_backtest(symbols=['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT', 'FET/USDT', 'ARB/USDT'], days=30):
    print(f"🚀 Starting High-Frequency Backtest (Iteration 72.2) for {symbols}...")
    
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days+10)).isoformat())
    
    print("📥 Fetching BTC data for relative strength...")
    btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', since=since, limit=1000)
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'], unit='ms')
    btc_df.set_index('timestamp', inplace=True)

    all_trades = []
    model = joblib.load('models/rf_model.joblib')
    
    for symbol in symbols:
        try:
            print(f"\n🔍 Processing {symbol}...")
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', since=since, limit=1000)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 1. Indicators
            df['rsi'] = calculate_rsi(df)
            df['ema20'] = calculate_ema(df, 20)
            df['ema50'] = calculate_ema(df, 50)
            df['ema200'] = calculate_ema(df, 200)
            _, _, macd_hist = calculate_macd(df)
            df['macd_hist'] = macd_hist

            # 2. AI Scores
            features_df = extract_features(df.reset_index(), btc_df.reset_index())
            predictions = model.predict_proba(features_df)[:, 1]
            
            # Align
            df = df.iloc[-len(features_df):].copy()
            df['ai_score'] = predictions

            # 3. Trading Logic (High Frequency)
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
                    # ENTRY CONDITIONS (High Frequency)
                    cond_rsi = row['rsi'] < 45
                    cond_ema_cross = row['ema20'] > row['ema50']
                    cond_trend = row['close'] > row['ema200'] * 0.98 # Allow slightly below EMA200
                    cond_ai = row['ai_score'] >= 0.55
                    
                    if cond_rsi and cond_ema_cross and cond_trend and cond_ai:
                        position = 'LONG'
                        entry_price = curr_price
                        entry_time = curr_time
                        entry_score = row['ai_score']
                else:
                    # EXIT CONDITIONS (Tight Exit)
                    pnl = (curr_price - entry_price) / entry_price
                    
                    tp_hit = pnl >= 0.012
                    sl_hit = pnl <= -0.008
                    rsi_exit = row['rsi'] > 70
                    
                    if tp_hit or sl_hit or rsi_exit:
                        exit_reason = "TP" if tp_hit else ("SL" if sl_hit else "RSI")
                        all_trades.append({
                            'Symbol': symbol,
                            'Entry Time': entry_time.strftime('%Y-%m-%d %H:%M'),
                            'Exit Time': curr_time.strftime('%Y-%m-%d %H:%M'),
                            'Entry Price': entry_price,
                            'Exit Price': curr_price,
                            'AI Confidence': f"{entry_score:.2%}",
                            'PnL %': f"{pnl*100:.2f}%",
                            'Reason': exit_reason,
                            'raw_pnl': pnl * 100
                        })
                        position = None
        except Exception as e:
            print(f"⚠️ Error processing {symbol}: {e}")

    # 4. Summary
    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        total_pnl = trades_df['raw_pnl'].sum()
        win_rate = (trades_df['raw_pnl'] > 0).mean() * 100
        
        cumulative_pnl = (1 + trades_df['raw_pnl'] / 100).cumprod()
        peak = cumulative_pnl.cummax()
        max_dd = ((cumulative_pnl - peak) / peak).min() * 100
        
        print("\n" + "="*40)
        print(f"⚡ HIGH-FREQUENCY BACKTEST RESULTS")
        print("="*40)
        print(f"Total Trades: {len(trades_df)}")
        print(f"Total Return: {total_pnl:.2f}%")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Max Drawdown: {max_dd:.2f}%")
        print("="*40)
        
        print("\nFirst 5 Trades:")
        print(trades_df.head(5).drop(columns=['raw_pnl']).to_string(index=False))
        
        trades_df.to_csv('backtest_results_high_freq.csv', index=False)
        print(f"\n✅ Full trade list saved to backtest_results_high_freq.csv")
    else:
        print("\n❌ No trades met the High-Frequency criteria.")

if __name__ == "__main__":
    run_backtest()
