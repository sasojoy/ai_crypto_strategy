
import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.market import calculate_rsi, calculate_ema, calculate_atr
from src.features import extract_features
from src.ml_model import CryptoMLModel
from src.strategy.logic import DualTrackStrategy

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=30):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    while since < exchange.milliseconds():
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
        if not ohlcv:
            break
        since = ohlcv[-1][0] + 1
        all_ohlcv.extend(ohlcv)
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def run_backtest(symbol, df, btc_df, ml_model, initial_balance=2000):
    strategy = DualTrackStrategy()
    timeframe = strategy.get_timeframe(symbol)
    trade_params = strategy.get_trade_params(symbol)
    weight = strategy.get_weight(symbol)
    
    # Feature Extraction
    features = extract_features(df, btc_df)
    
    # Indicators for 1H Trend Filter
    df_1h = df.resample('1h').last().ffill()
    df_1h['ema50'] = calculate_ema(df_1h, 50)
    
    # Align features with original df
    df = df.loc[features.index]
    
    trades = []
    in_position = False
    entry_price = 0
    balance = initial_balance
    last_trade_time = datetime.min
    
    for i in range(200, len(df)):
        current_time = df.index[i]
        current_price = df['close'].iloc[i]
        
        if not in_position:
            # 1. 4H Cooldown
            if (current_time - last_trade_time).total_seconds() < 14400:
                continue
                
            # 2. 1H Trend Filter
            current_1h_time = current_time.replace(minute=0, second=0, microsecond=0)
            if current_1h_time not in df_1h.index or df['close'].iloc[i] <= df_1h.loc[current_1h_time, 'ema50']:
                continue
            
            # 3. AI Score
            X = features.iloc[i:i+1]
            probs = ml_model.predict_proba(X)
            ml_score = float(probs[0][1]) if hasattr(probs, "ndim") and probs.ndim == 2 else float(probs)
            
            threshold = strategy.get_threshold(symbol)
            if ml_score >= threshold:
                in_position = True
                entry_price = current_price
                entry_time = current_time
                kelly = 1.5 if ml_score >= 0.90 else (1.0 if ml_score >= 0.80 else 0.5)
                pos_size = balance * weight * kelly
                
                sl_price = entry_price * (1 - trade_params['sl_pct'])
                tp_price = entry_price * (1 + trade_params['tp_pct'])
        
        elif in_position:
            # Check TP or SL
            if current_price >= tp_price or current_price <= sl_price:
                exit_price = current_price
                price_change = (exit_price - entry_price) / entry_price
                
                # Tiered Slippage & Fee (0.1% base fee + tiered slippage)
                friction = 0.001 + trade_params['slippage_comp']
                profit_amount = (pos_size * price_change) - (pos_size * friction)
                balance += profit_amount
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'profit_pct': (profit_amount / pos_size) * 100,
                    'balance': balance
                })
                in_position = False
                last_trade_time = current_time
                
    if not trades:
        return 0, 0, 0, 0, pd.DataFrame()
    
    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df['profit_pct'] > 0).sum() / total_trades * 100
    net_profit = balance - initial_balance
    
    # Calculate Max Drawdown
    trades_df['cumulative_balance'] = trades_df['balance']
    peak = trades_df['cumulative_balance'].cummax()
    drawdown = (trades_df['cumulative_balance'] - peak) / peak
    max_drawdown = drawdown.min() * 100
    
    return total_trades, win_rate, net_profit, max_drawdown, trades_df

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'FET/USDT', 'NEAR/USDT']
    initial_balance = 2000
    
    ml_model = CryptoMLModel()
    if not ml_model.load():
        print("❌ Model not found. Please train the model first.")
        exit(1)
        
    print("Fetching BTC data for relative strength...")
    btc_df = fetch_backtest_data('BTC/USDT', timeframe='15m', days=30)
    
    for symbol in symbols:
        print(f"\n正在獲取 {symbol} 過去 30 天的數據...")
        df = fetch_backtest_data(symbol=symbol, timeframe='15m', days=30)
        print(f"獲取到 {len(df)} 條數據。")
        
        total_trades, win_rate, net_profit, max_drawdown, trades_df = run_backtest(symbol, df, btc_df, ml_model, initial_balance=initial_balance)
        
        print(f"\n--- {symbol} 回測報告 (Iteration 116.0 Soul) ---")
        print(f"起始資金: ${initial_balance}")
        print(f"總交易次數: {total_trades}")
        print(f"勝率: {win_rate:.2f}%")
        print(f"淨獲利: ${net_profit:.2f}")
        print(f"最大回撤: {max_drawdown:.2f}%")
        if not trades_df.empty:
            print(f"最終餘額: ${trades_df['balance'].iloc[-1]:.2f}")
            print("\n--- 交易明細 (前 5 筆) ---")
            print(trades_df[['entry_time', 'exit_time', 'profit_pct', 'balance']].head())
