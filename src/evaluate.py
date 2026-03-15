import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import joblib
import json
from src.indicators import calculate_rsi, calculate_ema, calculate_atr, calculate_macd, calculate_adx, calculate_bollinger_bands, calculate_heikin_ashi, calculate_sr_levels, calculate_rsi_slope
from src.features import extract_features

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=14):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv: break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
        except Exception as e:
            print(f"Error fetching data: {e}")
            break
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_evaluation(df, initial_balance=10000, ml_threshold=0.69):
    if df.empty: return {"score": 0, "profit": 0, "win_rate": 0, "max_dd": 0, "trades": 0}

    # Load Model
    model_path = 'models/rf_model.joblib'
    if not os.path.exists(model_path):
        print("Model not found!")
        return None
    model = joblib.load(model_path)

    # Indicators for logic
    df['atr'] = calculate_atr(df, 14)
    df['ema200'] = calculate_ema(df, 200)
    
    # Feature extraction for ML
    df_features = extract_features(df)
    
    # Align features with model
    feature_cols = model.feature_names_in_
    X = df_features[feature_cols].fillna(0)
    
    # ML Predictions
    probs = model.predict_proba(X)[:, 1]
    df['ml_prob'] = 0.0
    df.loc[df_features.index, 'ml_prob'] = probs

    balance = initial_balance
    trades = []
    in_position = False
    entry_price = 0
    sl_price = 0
    tp_price = 0
    pos_size = 0
    side = None

    for i in range(50, len(df)):
        latest = df.iloc[i]
        
        if not in_position:
            # Iteration 61.3 Logic: ML Threshold + Trend Filter
            if latest['ml_prob'] >= ml_threshold and latest['close'] > latest['ema200']:
                in_position = True
                side = 'LONG'
                entry_price = latest['close']
                
                sl_dist = 2 * latest['atr']
                sl_price = entry_price - sl_dist
                tp_price = entry_price + (sl_dist * 1.3) # RR 1.8
                
                risk_amount = balance * 0.015
                pos_size = risk_amount / sl_dist if sl_dist > 0 else 0
                
                trades.append({'entry_time': latest['timestamp'], 'entry_price': entry_price, 'side': side, 'profit': 0})
        else:
            if side == 'LONG':
                if latest['low'] <= sl_price:
                    exit_price = sl_price
                    profit = (exit_price - entry_price) * pos_size
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit})
                    in_position = False
                elif latest['high'] >= tp_price:
                    exit_price = tp_price
                    profit = (exit_price - entry_price) * pos_size
                    balance += profit
                    trades[-1].update({'exit_time': latest['timestamp'], 'exit_price': exit_price, 'profit': profit})
                    in_position = False

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df[trades_df['profit'] != 0])
    win_rate = (trades_df["profit"] > 0).sum() / total_trades if total_trades > 0 else 0
    net_profit = balance - initial_balance
    
    if total_trades > 0:
        trades_df["cum_profit"] = trades_df["profit"].cumsum() + initial_balance
        peak = trades_df["cum_profit"].cummax()
        max_dd = abs(((trades_df["cum_profit"] - peak) / peak).min())
    else:
        max_dd = 0
        
    return {"profit": net_profit, "win_rate": win_rate, "max_dd": max_dd, "trades": total_trades}

if __name__ == "__main__":
    symbol = 'BTC/USDT'
    print(f"🚀 Running Local Evaluation for {symbol} (Last 14 days)...")
    df = fetch_backtest_data(symbol, days=14)
    if not df.empty:
        res = run_evaluation(df, ml_threshold=0.69)
        print("\n" + "="*30)
        print("📊 REAL-WORLD BACKTEST RESULTS")
        print("="*30)
        print(f"勝率: {res['win_rate']*100:.2f}%")
        print(f"總盈虧: ${res['profit']:.2f}")
        print(f"回撤: {res['max_dd']*100:.2f}%")
        print(f"交易次數: {res['trades']}")
        print("="*30)
    else:
        print("No data.")
