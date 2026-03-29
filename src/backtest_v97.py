
import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel
from src.strategy.logic import DualTrackStrategy


# Iteration 130.0: Read-only Watcher Mode for Backtest
if not os.getenv('BINANCE_API_KEY') or not os.getenv('BINANCE_SECRET'):
    print("⚠️ [SIMULATION ONLY] No API keys found. Using Public API for data fetching.")
else:
    print("🚀 [AUTHENTICATED] API keys found. Backtest running in high-fidelity mode.")


def fetch_backtest_data(symbol, timeframe, days=180):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    print(f"正在獲取 {symbol} ({timeframe}) 過去 {days} 天的數據...")
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv:
                break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
            if len(ohlcv) < 500: # Binance default limit
                break
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            break
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    print(f"獲取到 {len(df)} 條數據。")
    return df

def run_backtest_v97(symbol, df, btc_df, ml_model, initial_balance=2000):
    if symbol in ['BTC/USDT', 'ETH/USDT']:
        friction = 0.0015
        vol_threshold = 2.0
    elif symbol == 'SOL/USDT':
        friction = 0.0025
        vol_threshold = 3.0
    elif symbol in ['FET/USDT', 'AVAX/USDT']:
        friction = 0.0055
        vol_threshold = 3.0
    else:
        return None
        
    from src.market import calculate_ema, calculate_rsi, calculate_atr
    import pandas_ta as ta
    
    # 1H Indicators
    coin_ema20 = calculate_ema(df, 20)
    coin_atr = calculate_atr(df, 14)
    btc_ema200 = calculate_ema(btc_df, 200).reindex(df.index).ffill()
    btc_price_series = btc_df['close'].reindex(df.index).ffill()
    vol_24h_avg = df['volume'].rolling(24).mean()
    rsi_1h = calculate_rsi(df, 14)
    
    # ADX Trend Confirmation
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    adx_series = adx_df['ADX_14']
    adx_rising = adx_series.diff() > 0
    
    # AI Score (Secondary Guard)
    features = extract_features(df, btc_df)
    X_all = features.reindex(columns=list(getattr(ml_model.model, 'feature_names_in_', ml_model.feature_names)))
    all_probs = ml_model.model.predict_proba(X_all)
    score_series = pd.Series(all_probs[:, 1], index=features.index)
    
    trades = []
    position = None
    balance = initial_balance
    equity_curve = [balance]
    weight = 0.2
    
    for i in range(100, len(df)):
        current_time = df.index[i]
        current_price = df['close'].iloc[i]
        
        if position is None:
            if current_time not in score_series.index: 
                equity_curve.append(balance)
                continue
            
            ml_score = score_series.loc[current_time]
            
            # Iteration 126.1: Consistency Logging
            feature_vals = X_all.loc[current_time].tolist()
            if i == len(df) - 1: # Only log the latest for comparison
                print(f"DEBUG [Consistency] symbol: {symbol} | features: {feature_vals}")
            
            curr_vol = df['volume'].iloc[i]
            avg_vol = vol_24h_avg.iloc[i]
            curr_btc_price = btc_price_series.iloc[i]
            curr_btc_ema = btc_ema200.iloc[i]
            curr_coin_ema20 = coin_ema20.iloc[i]
            curr_rsi = rsi_1h.iloc[i]
            curr_atr = coin_atr.iloc[i]
            curr_adx = adx_series.iloc[i]
            is_adx_rising = adx_rising.iloc[i]
            
            # Momentum Conditions
            is_volume_burst = curr_vol > (avg_vol * vol_threshold)
            is_trend_confirmed = curr_adx > 25 and is_adx_rising
            
            # Long Entry: Momentum + Trend + AI Guard
            if (curr_btc_price > curr_btc_ema and 
                current_price > curr_coin_ema20 and 
                is_volume_burst and 
                is_trend_confirmed and
                curr_rsi > 50 and
                ml_score > 0.55):
                
                position = 'long'
                entry_price = current_price
                entry_time = current_time
                pos_size = balance * weight
                # Iteration 125.0: Wider ATR Dynamic SL/TP
                sl_price = entry_price - (1.8 * curr_atr)
                tp_price = entry_price + (4.0 * curr_atr)
            
            # Short Entry: Momentum + Trend + AI Guard
            elif (curr_btc_price < curr_btc_ema and 
                  current_price < curr_coin_ema20 and 
                  is_volume_burst and 
                  is_trend_confirmed and
                  curr_rsi < 50 and
                  ml_score < 0.45):
                
                position = 'short'
                entry_price = current_price
                entry_time = current_time
                pos_size = balance * weight
                # Iteration 125.0: Wider ATR Dynamic SL/TP
                sl_price = entry_price + (1.8 * curr_atr)
                tp_price = entry_price - (4.0 * curr_atr)
        else:
            # Exit logic
            exit_triggered = False
            if position == 'long':
                if current_price >= tp_price or current_price <= sl_price:
                    profit_pct = (current_price - entry_price) / entry_price
                    exit_triggered = True
            else:
                if current_price <= tp_price or current_price >= sl_price:
                    profit_pct = (entry_price - current_price) / entry_price
                    exit_triggered = True
                
            if exit_triggered:
                profit_amount = (pos_size * profit_pct) - (pos_size * friction)
                balance += profit_amount
                trades.append({
                    'symbol': symbol,
                    'type': position,
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'profit_pct': (profit_amount / pos_size) * 100,
                    'profit_abs': profit_amount,
                    'balance': balance
                })
                position = None
        equity_curve.append(balance)
        
    if not trades:
        return 0, 0, 0, 0, equity_curve, []
    
    trades_df = pd.DataFrame(trades)
    win_rate = (trades_df['profit_pct'] > 0).sum() / len(trades_df) * 100
    net_pnl = balance - initial_balance
    
    gross_profit = trades_df[trades_df['profit_abs'] > 0]['profit_abs'].sum()
    gross_loss = abs(trades_df[trades_df['profit_abs'] < 0]['profit_abs'].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    return len(trades_df), win_rate, net_pnl, pf, equity_curve, trades

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'FET/USDT', 'AVAX/USDT']
    ml_model = CryptoMLModel()
    if not ml_model.load():
        print("❌ Model not found.")
        exit(1)
        
    btc_df_1h = fetch_backtest_data('BTC/USDT', '1h', days=180)
    
    all_results = []
    all_trades = []
    total_equity_curve = None
    
    for symbol in symbols:
        df = btc_df_1h if symbol == 'BTC/USDT' else fetch_backtest_data(symbol, '1h', days=180)
        if df.empty: continue
        
        count, wr, pnl, pf, curve, trades = run_backtest_v97(symbol, df, btc_df_1h, ml_model)
        all_results.append({
            'symbol': symbol,
            'count': count,
            'wr': wr,
            'pnl': pnl,
            'pf': pf
        })
        all_trades.extend(trades)
        
        if total_equity_curve is None:
            total_equity_curve = np.array(curve)
        else:
            # Align curves if necessary, here we assume same length for simplicity
            min_len = min(len(total_equity_curve), len(curve))
            total_equity_curve = total_equity_curve[:min_len] + np.array(curve[:min_len]) - 2000 # Adjust for initial balance

    # Reporting
    print("\n" + "="*75)
    print(f"{'幣種':<10} | {'交易次數':<10} | {'勝率':<10} | {'PF':<10} | {'淨 PnL':<10}")
    print("-" * 75)
    for res in all_results:
        print(f"{res['symbol']:<10} | {res['count']:<10} | {res['wr']:>8.2f}% | {res['pf']:>8.2f} | ${res['pnl']:>8.2f}")
    print("="*75)
    
    if total_equity_curve is not None:
        print(f"資產曲線最高點: ${np.max(total_equity_curve):.2f}")
        print(f"資產曲線最終點: ${total_equity_curve[-1]:.2f}")
        
    # Save Audit CSV
    if all_trades:
        os.makedirs('data', exist_ok=True)
        trades_df = pd.DataFrame(all_trades)
        trades_df.to_csv('data/final_audit_v122.csv', index=False)
        print("\nTop 10 多/空成交紀錄 (data/final_audit_v122.csv):")
        print(trades_df.head(10).to_string())
