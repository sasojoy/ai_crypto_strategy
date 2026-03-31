
import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel
from src.indicators import calculate_atr, calculate_rsi

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

def run_legend_backtest(friction_fee=0.0, friction_slippage=0.0):
    INITIAL_BALANCE = 2000.0
    RISK_PER_TRADE = 0.10  # 10% Risk as requested
    MAX_CONCURRENT_TRADES = 10
    
    ml_model = CryptoMLModel()
    ml_model.load()
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    data = {s: fetch_backtest_data(s, '1h') for s in symbols}
    btc_df = data['BTC/USDT']
    
    # Iteration 146.0: BTC Dominance Proxy
    btc_eth_ratio = data['BTC/USDT']['close'] / data['ETH/USDT']['close']
    btcd_ema = btc_eth_ratio.rolling(20).mean()
    btc_dominant = (btc_eth_ratio > btcd_ema)

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
        # Exit Logic
        to_close = []
        for s, t in active_trades.items():
            if ts not in processed[s]['df'].index: continue
            curr_p = processed[s]['df'].loc[ts, 'close']
            profit_pct = (curr_p - t['entry_p']) / t['entry_p'] if t['side'] == 'long' else (t['entry_p'] - curr_p) / t['entry_p']
            
            exit_triggered = False
            if curr_p <= t['sl'] if t['side'] == 'long' else curr_p >= t['sl']: exit_triggered = True
            elif curr_p >= t['tp'] if t['side'] == 'long' else curr_p <= t['tp']: exit_triggered = True
            
            if exit_triggered:
                pnl = (t['size'] * profit_pct) - (t['size'] * (friction_fee + friction_slippage))
                balance += (t['size'] + pnl)
                history.append({'symbol': s, 'pnl': pnl, 'profit_pct': profit_pct})
                to_close.append(s)
        for s in to_close: del active_trades[s]

        # Entry Logic (146.0 Core)
        if len(active_trades) < MAX_CONCURRENT_TRADES:
            is_btc_dom = btc_dominant.get(ts, False)
            for s in symbols:
                if s in active_trades or ts not in processed[s]['score'].index: continue
                
                # 146.0 Filter: Trade BTC if dominant, else trade Alts
                if is_btc_dom and s != 'BTC/USDT': continue
                if not is_btc_dom and s == 'BTC/USDT': continue
                
                score = processed[s]['score'].loc[ts]
                side = 'long' if score > 0.75 else ('short' if score < 0.25 else None)
                
                if side:
                    curr_p = processed[s]['df'].loc[ts, 'close']
                    atr = processed[s]['atr'].loc[ts]
                    sl_dist = 3.0 * atr
                    sl = curr_p - sl_dist if side == 'long' else curr_p + sl_dist
                    tp = curr_p + (6.0 * atr) if side == 'long' else curr_p - (6.0 * atr)
                    
                    # 10% Risk Position Sizing
                    size = (balance * RISK_PER_TRADE) / (sl_dist / curr_p)
                    size = min(size, balance * 0.5) # Cap at 50% for sanity
                    
                    if balance >= size:
                        balance -= size
                        active_trades[s] = {'side': side, 'entry_p': curr_p, 'size': size, 'sl': sl, 'tp': tp}
        
        equity_curve.append(balance + sum([t['size'] for t in active_trades.values()]))

    final_b = equity_curve[-1]
    print(f"Final Balance (Fee={friction_fee}, Slip={friction_slippage}): ${final_b:.2f}")
    return final_b

if __name__ == "__main__":
    print("--- Running Zero Friction Test ---")
    run_legend_backtest(0.0, 0.0)
    print("\n--- Running Sensitivity Analysis ---")
    run_legend_backtest(0.0004, 0.0005)
