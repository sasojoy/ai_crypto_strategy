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
    print(f"🚀 Starting Advanced Backtest (Iteration 73.0) for {symbols}...")
    
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
            df['atr'] = calculate_atr(df)
            df['adx'] = calculate_adx(df)

            # 2. AI Scores
            features_df = extract_features(df.reset_index(), btc_df.reset_index())
            predictions = model.predict_proba(features_df)[:, 1]
            
            # Align
            df = df.iloc[-len(features_df):].copy()
            df['ai_score'] = predictions

            # 3. Trading Logic (Iteration 73.0)
            position = None
            entry_price = 0
            entry_time = None
            entry_score = 0
            highest_price = 0
            trailing_stop = 0
            
            for i in range(1, len(df)):
                row = df.iloc[i]
                curr_time = df.index[i]
                curr_price = row['close']
                
                if position is None:
                    # ENTRY CONDITIONS
                    cond_rsi = row['rsi'] < 45
                    cond_ema_cross = row['ema20'] > row['ema50']
                    cond_trend = row['close'] > row['ema200'] * 0.98
                    cond_ai = row['ai_score'] >= 0.55
                    
                    if cond_rsi and cond_ema_cross and cond_trend and cond_ai:
                        position = 'LONG'
                        entry_price = curr_price
                        entry_time = curr_time
                        entry_score = row['ai_score']
                        highest_price = curr_price
                        
                        # Confidence Ladder Position Sizing (Multiplier)
                        if entry_score >= 0.70:
                            pos_size = 1.5
                        elif entry_score >= 0.60:
                            pos_size = 1.0
                        else:
                            pos_size = 0.5
                        
                        # Initial SL (0.8%)
                        trailing_stop = entry_price * 0.992
                else:
                    # Update Trailing Stop
                    if curr_price > highest_price:
                        highest_price = curr_price
                        # If profit > 1%, move SL to entry + 0.5%
                        if (highest_price - entry_price) / entry_price >= 0.01:
                            new_stop = entry_price * 1.005
                            trailing_stop = max(trailing_stop, new_stop)
                    
                    # EXIT CONDITIONS
                    pnl = (curr_price - entry_price) / entry_price
                    
                    tp_hit = pnl >= 0.012
                    sl_hit = curr_price <= trailing_stop
                    rsi_exit = row['rsi'] > 70
                    
                    if tp_hit or sl_hit or rsi_exit:
                        exit_reason = "TP" if tp_hit else ("TSL" if sl_hit else "RSI")
                        all_trades.append({
                            'Symbol': symbol,
                            'Entry Time': entry_time.strftime('%Y-%m-%d %H:%M'),
                            'Exit Time': curr_time.strftime('%Y-%m-%d %H:%M'),
                            'Entry Price': entry_price,
                            'Exit Price': curr_price,
                            'AI Confidence': f"{entry_score:.2%}",
                            'Pos Size': pos_size,
                            'PnL %': f"{pnl*100:.2f}%",
                            'Reason': exit_reason,
                            'raw_pnl': pnl * 100 * pos_size
                        })
                        position = None
        except Exception as e:
            print(f"⚠️ Error processing {symbol}: {e}")

    # 4. Summary
    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        total_pnl = trades_df['raw_pnl'].sum()
        win_rate = (trades_df['raw_pnl'] > 0).mean() * 100
        
        # Profit Factor
        gross_profit = trades_df[trades_df['raw_pnl'] > 0]['raw_pnl'].sum()
        gross_loss = abs(trades_df[trades_df['raw_pnl'] < 0]['raw_pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
        
        # Max Consecutive Losses
        trades_df['is_loss'] = trades_df['raw_pnl'] < 0
        loss_groups = (trades_df['is_loss'] != trades_df['is_loss'].shift()).cumsum()
        consecutive_losses = trades_df.groupby(loss_groups)['is_loss'].sum()
        max_consecutive_losses = consecutive_losses.max()

        print("\n" + "="*40)
        print(f"💎 ADVANCED BACKTEST RESULTS (73.0)")
        print("="*40)
        print(f"Total Trades: {len(trades_df)}")
        print(f"Total Return: {total_pnl:.2f}%")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Max Consecutive Losses: {max_consecutive_losses}")
        print("="*40)
        
        print("\nVolatility Period (3/10 - 3/15) Performance:")
        vol_trades = trades_df[(trades_df['Entry Time'] >= '2026-03-10') & (trades_df['Entry Time'] <= '2026-03-15')]
        if not vol_trades.empty:
            print(vol_trades.head(5).drop(columns=['raw_pnl', 'is_loss']).to_string(index=False))
        else:
            print("No trades during this period.")
            
        trades_df.to_csv('backtest_results_v73.csv', index=False)
    else:
        print("\n❌ No trades met the criteria.")

if __name__ == "__main__":
    run_backtest()
