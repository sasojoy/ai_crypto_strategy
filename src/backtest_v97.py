
import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.market import calculate_rsi, calculate_ema, calculate_atr
from src.features import extract_features
from src.ml_model import CryptoMLModel
from src.strategy.logic import DualTrackStrategy

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=180):
    # Try to load from local data first
    local_path = f"/workspace/ai_crypto_strategy/data/{symbol.replace('/', '_')}_{timeframe}.csv"
    if os.path.exists(local_path):
        df = pd.read_csv(local_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        # Filter for last 180 days
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff]
        if not df.empty:
            return df

    # Fallback to CCXT
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())

    all_ohlcv = []
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv:
                break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            break

    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def run_backtest_v97(symbol, df, btc_df, ml_model, initial_balance=2000):
    # 嚴格摩擦係數設定
    friction_map = {
        'BTC/USDT': 0.0015,  # 0.15%
        'ETH/USDT': 0.0015,  # 0.15%
        'SOL/USDT': 0.0025,  # 0.25%
        'FET/USDT': 0.0055,  # 0.55%
        'AVAX/USDT': 0.0055  # 0.55%
    }
    friction = friction_map.get(symbol, 0.0055)
    
    # 雙軌邏輯設定
    is_1h_track = symbol in ['BTC/USDT', 'ETH/USDT']
    
    if is_1h_track:
        # Resample to 1H if it's BTC/ETH
        df = df.resample('1H').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

    # Feature Extraction
    features = extract_features(df, btc_df)
    df = df.loc[features.index]

    trades = []
    in_position = False
    entry_price = 0
    balance = initial_balance
    
    # Strategy parameters
    tp_pct = 0.05 if is_1h_track else 0.03
    sl_pct = 0.02 if is_1h_track else 0.015
    threshold = 0.85 if is_1h_track else 0.75

    for i in range(50, len(df)):
        current_time = df.index[i]
        current_price = df['close'].iloc[i]

        if not in_position:
            # AI Score
            X = features.iloc[i:i+1]
            try:
                probs = ml_model.predict_proba(X)
                ml_score = float(probs[0][1])
            except:
                continue

            if ml_score >= threshold:
                in_position = True
                entry_price = current_price
                entry_time = current_time
                pos_size = balance * 0.2 # Fixed 20% allocation per trade for backtest

        elif in_position:
            # Check TP or SL
            price_change = (current_price - entry_price) / entry_price
            
            if price_change >= tp_pct or price_change <= -sl_pct:
                exit_price = current_price
                
                # Apply friction
                net_pnl_pct = price_change - friction
                profit_amount = pos_size * net_pnl_pct
                balance += profit_amount

                trades.append({
                    'symbol': symbol,
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'pnl_pct': net_pnl_pct * 100,
                    'profit_amount': profit_amount,
                    'balance': balance
                })
                in_position = False

    return trades

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'FET/USDT', 'AVAX/USDT']
    initial_balance = 2000
    all_trades = []

    ml_model = CryptoMLModel()
    if not ml_model.load():
        print("❌ Model not found.")
        exit(1)

    print("Fetching BTC data for reference...")
    btc_df_raw = fetch_backtest_data('BTC/USDT', timeframe='15m', days=180)
    
    results = []

    for symbol in symbols:
        print(f"Backtesting {symbol}...")
        df_raw = fetch_backtest_data(symbol, timeframe='15m', days=180)
        
        # Ensure btc_df matches df_raw index for feature extraction
        btc_df = btc_df_raw.reindex(df_raw.index).ffill()
        
        trades = run_backtest_v97(symbol, df_raw, btc_df, ml_model, initial_balance)
        all_trades.extend(trades)
        
        if trades:
            trades_df = pd.DataFrame(trades)
            win_rate = (trades_df['pnl_pct'] > 0).sum() / len(trades_df) * 100
            net_pnl = trades_df['profit_amount'].sum()
            results.append({
                '幣種': symbol,
                '交易次數': len(trades_df),
                '勝率': f"{win_rate:.2f}%",
                '淨 PnL': f"${net_pnl:.2f}"
            })
        else:
            results.append({
                '幣種': symbol,
                '交易次數': 0,
                '勝率': "0.00%",
                '淨 PnL': "$0.00"
            })

    print("\n" + "="*50)
    print("Iteration 97.0 全幣種淨利審計回測報告 (180天)")
    print("="*50)
    report_df = pd.DataFrame(results)
    print(report_df.to_string(index=False))
    print("="*50)
