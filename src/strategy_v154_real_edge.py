



import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel
from src.indicators import *

def fetch_backtest_data(symbol, timeframe, days=180):
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    print(f"Fetching {symbol} ({timeframe})...")
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv: break
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
            if len(ohlcv) < 500: break
        except: break
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def run_real_edge_audit():
    INITIAL_BALANCE = 2000.0
    FRICTION = 0.0009 # 0.04% Fee + 0.05% Slippage
    MAX_CONCURRENT_TRADES = 10
    
    ml_model = CryptoMLModel()
    ml_model.load()
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'FET/USDT', 'AVAX/USDT']
    # Multi-timeframe data
    data_1h = {s: fetch_backtest_data(s, '1h') for s in symbols}
    data_15m = {s: fetch_backtest_data(s, '15m') for s in symbols}
    
    processed = {}
    all_timestamps = set()
    for s in symbols:
        df_1h = data_1h[s]
        df_15m = data_15m[s]
        
        # 1H Trend (EMA200)
        ema200_1h = df_1h['close'].ewm(span=200, adjust=False).mean()
        
        # 15m Oversold (RSI)
        rsi_15m = calculate_rsi(df_15m)
        
        # ML Scores (1H based)
        features = extract_features(df_1h, data_1h['BTC/USDT'])
        X = features.reindex(columns=ml_model.feature_names)
        probs = ml_model.model.predict_proba(X)[:, 1]
        scores = pd.Series(probs, index=features.index).reindex(df_15m.index).ffill()
        
        processed[s] = {
            'df_15m': df_15m,
            'atr_15m': calculate_atr(df_15m, 14).reindex(df_15m.index).ffill(),
            'ema200_1h': ema200_1h.reindex(df_15m.index).ffill(),
            'rsi_15m': rsi_15m.reindex(df_15m.index).ffill(),
            'score': scores
        }
        all_timestamps.update(df_15m.index.tolist())

    balance = INITIAL_BALANCE
    active_trades = {}
    history = []
    equity_curve = []
    
    for ts in sorted(list(all_timestamps)):
        # 1. Manage Positions
        to_close = []
        for s, t in active_trades.items():
            if ts not in processed[s]['df_15m'].index: continue
            curr_p = processed[s]['df_15m'].loc[ts, 'close']
            profit_pct = (curr_p - t['entry_p']) / t['entry_p'] if t['side'] == 'long' else (t['entry_p'] - curr_p) / t['entry_p']
            
            # Break-even Mechanism (1.5 * ATR)
            if not t['be_active'] and profit_pct >= (1.5 * t['entry_atr'] / t['entry_p']):
                t['sl'] = t['entry_p'] * (1.0005 if t['side'] == 'long' else 0.9995)
                t['be_active'] = True
            
            # Exit
            exit_triggered = False
            if t['side'] == 'long' and curr_p <= t['sl']: exit_triggered = True
            elif t['side'] == 'short' and curr_p >= t['sl']: exit_triggered = True
            elif t['side'] == 'long' and curr_p >= t['tp']: exit_triggered = True
            elif t['side'] == 'short' and curr_p <= t['tp']: exit_triggered = True
            
            if exit_triggered:
                pnl = (t['size'] * profit_pct) - (t['size'] * FRICTION)
                balance += (t['size'] + pnl)
                history.append({'symbol': s, 'pnl': pnl, 'win': pnl > 0})
                to_close.append(s)
        for s in to_close: del active_trades[s]

        # 2. Entry (Real-Edge Logic)
        if len(active_trades) < MAX_CONCURRENT_TRADES:
            for s in symbols:
                if s in active_trades or ts not in processed[s]['score'].index: continue
                
                score = processed[s]['score'].loc[ts]
                ema200 = processed[s]['ema200_1h'].loc[ts]
                rsi = processed[s]['rsi_15m'].loc[ts]
                curr_p = processed[s]['df_15m'].loc[ts, 'close']
                
                side = None
                # Filter: 1H Trend + 15m RSI + ML Score
                if score > 0.75 and curr_p > ema200 and rsi < 40: # Long: Trend Up + 15m Oversold
                    side = 'long'
                elif score < 0.25 and curr_p < ema200 and rsi > 60: # Short: Trend Down + 15m Overbought
                    side = 'short'
                
                if side:
                    # Normalized Risk (8% max / 2% std)
                    risk_weight = 0.08 if (score > 0.92 or score < 0.08) else 0.02
                    size = balance * risk_weight
                    
                    if balance >= size:
                        balance -= size
                        atr = processed[s]['atr_15m'].loc[ts]
                        active_trades[s] = {
                            'side': side, 'entry_p': curr_p, 'size': size,
                            'entry_atr': atr, 'be_active': False,
                            'sl': curr_p - (3.0 * atr) if side == 'long' else curr_p + (3.0 * atr),
                            'tp': curr_p + (5.0 * atr) if side == 'long' else curr_p - (5.0 * atr)
                        }
        
        equity_curve.append(balance + sum([t['size'] for t in active_trades.values()]))

    # Final Audit Table
    trades_df = pd.DataFrame(history)
    audit = []
    for s in symbols:
        s_trades = trades_df[trades_df['symbol'] == s]
        count = len(s_trades)
        win_rate = (s_trades['win'].sum() / count * 100) if count > 0 else 0
        pnl = s_trades['pnl'].sum() if count > 0 else 0
        audit.append({'幣種': s, '交易次數': count, '勝率': f"{win_rate:.2f}%", '淨 PnL': f"${pnl:.2f}"})
    
    print("\n" + "="*50)
    print("全幣種淨利審計回測 (Predator V154 Real-Edge)")
    print("-" * 50)
    print(pd.DataFrame(audit).to_string(index=False))
    print("-" * 50)
    print(f"最終餘額: ${equity_curve[-1]:.2f}")
    print(f"最大回撤 (MDD): {(pd.Series(equity_curve).cummax() - pd.Series(equity_curve)).max() / pd.Series(equity_curve).cummax().max() * 100:.2f}%")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_real_edge_audit()



