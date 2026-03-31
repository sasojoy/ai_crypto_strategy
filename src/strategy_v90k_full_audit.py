


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

def run_predator_audit():
    INITIAL_BALANCE = 2000.0
    FRICTION = 0.0009 # 0.09% Total
    MAX_CONCURRENT_TRADES = 10
    
    ml_model = CryptoMLModel()
    ml_model.load()
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'FET/USDT', 'AVAX/USDT']
    data = {s: fetch_backtest_data(s, '1h') for s in symbols}
    btc_df = data['BTC/USDT']
    
    processed = {}
    all_timestamps = set()
    for s, df in data.items():
        atr = calculate_atr(df, 14)
        features = extract_features(df, btc_df)
        X = features.reindex(columns=ml_model.feature_names)
        probs = ml_model.model.predict_proba(X)[:, 1]
        scores = pd.Series(probs, index=features.index).reindex(df.index).ffill()
        processed[s] = {'df': df, 'atr': atr.reindex(df.index).ffill(), 'score': scores}
        all_timestamps.update(df.index.tolist())

    balance = INITIAL_BALANCE
    active_trades = {}
    history = []
    equity_curve = []
    
    for ts in sorted(list(all_timestamps)):
        # Exit
        to_close = []
        for s, t in active_trades.items():
            if ts not in processed[s]['df'].index: continue
            curr_p = processed[s]['df'].loc[ts, 'close']
            profit_pct = (curr_p - t['entry_p']) / t['entry_p'] if t['side'] == 'long' else (t['entry_p'] - curr_p) / t['entry_p']
            
            if curr_p <= t['sl'] if t['side'] == 'long' else curr_p >= t['sl']:
                pnl = (t['size'] * profit_pct) - (t['size'] * FRICTION)
                balance += (t['size'] + pnl)
                history.append({'symbol': s, 'pnl': pnl, 'win': pnl > 0})
                to_close.append(s)
            elif curr_p >= t['tp'] if t['side'] == 'long' else curr_p <= t['tp']:
                pnl = (t['size'] * profit_pct) - (t['size'] * FRICTION)
                balance += (t['size'] + pnl)
                history.append({'symbol': s, 'pnl': pnl, 'win': pnl > 0})
                to_close.append(s)
        for s in to_close: del active_trades[s]

        # Entry (Predator Logic)
        if len(active_trades) < MAX_CONCURRENT_TRADES:
            for s in symbols:
                if s in active_trades or ts not in processed[s]['score'].index: continue
                score = processed[s]['score'].loc[ts]
                
                side = 'long' if score > 0.75 else ('short' if score < 0.25 else None)
                if side:
                    curr_p = processed[s]['df'].loc[ts, 'close']
                    atr = processed[s]['atr'].loc[ts]
                    
                    # Resonance Sniper: 30% Risk if ML > 0.90
                    risk_weight = 0.30 if (score > 0.90 or score < 0.10) else 0.05
                    size = balance * risk_weight
                    
                    if balance >= size:
                        balance -= size
                        sl_dist = 3.0 * atr
                        active_trades[s] = {
                            'side': side, 'entry_p': curr_p, 'size': size,
                            'sl': curr_p - sl_dist if side == 'long' else curr_p + sl_dist,
                            'tp': curr_p + (6.0 * atr) if side == 'long' else curr_p - (6.0 * atr)
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
    print("全幣種淨利審計回測 (Predator V126 Reborn)")
    print("-" * 50)
    print(pd.DataFrame(audit).to_string(index=False))
    print("-" * 50)
    print(f"最終餘額: ${equity_curve[-1]:.2f}")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_predator_audit()


