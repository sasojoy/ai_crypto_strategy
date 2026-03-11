
import pandas as pd
import numpy as np
from src.backtest_v42 import fetch_backtest_data
from src.market import calculate_rsi, calculate_ema, calculate_bollinger_bands, calculate_macd, calculate_adx

def run_backtest_v49(df, symbol, rsi_thresh=40, adx_thresh=20):
    df = df.copy()
    df['rsi'] = calculate_rsi(df)
    df['ema200_1h'] = calculate_ema(df, 200 * 4)
    df['ema10_15m'] = calculate_ema(df, 10)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['adx'] = calculate_adx(df)
    df = df.dropna().reset_index(drop=True)

    trades = []
    in_position = False
    entry_price = 0
    
    # Dynamic Risk Tracking
    recent_trades = []
    
    for i in range(2, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        if not in_position:
            # Dynamic Risk Calculation
            win_rate = 0.5
            losses = 0
            if len(recent_trades) >= 2:
                wins = len([t for t in recent_trades[-10:] if t.get('pnl', 0) > 0])
                win_rate = wins / min(len(recent_trades), 10)
                losses = len([t for t in recent_trades[-2:] if t.get('pnl', 0) < 0])
            
            risk_multiplier = 0.5 if win_rate > 0.5 else (0.2 if losses >= 2 else 0.3)

            # Core Filter: 1H EMA 200
            if current['close'] > current['ema200_1h']:
                score = 0
                if current['rsi'] < rsi_thresh: score += 1
                if current['macd_hist'] > prev['macd_hist']: score += 1
                if current['adx'] > adx_thresh: score += 1
                
                if score >= 2:
                    in_position = True
                    entry_price = current['close']
                    trades.append({
                        'entry_time': current['timestamp'], 
                        'entry_price': entry_price, 
                        'rsi': current['rsi'], 
                        'adx': current['adx'], 
                        'score': score,
                        'risk_multiplier': risk_multiplier
                    })
        else:
            # Iteration 49 Exit: 15m EMA 10 Trailing or 1.5% SL
            pnl = (current['close'] - entry_price) / entry_price
            
            # Trailing Stop: Close if price < EMA 10 and profit > 1.5%
            if pnl > 0.015 and current['close'] < current['ema10_15m']:
                trades[-1]['exit_price'] = current['close']
                trades[-1]['pnl'] = pnl * trades[-1]['risk_multiplier'] * 3.3 # Normalized to base risk
                recent_trades.append(trades[-1])
                in_position = False
            elif pnl <= -0.015:
                trades[-1]['exit_price'] = current['close']
                trades[-1]['pnl'] = pnl * trades[-1]['risk_multiplier'] * 3.3
                recent_trades.append(trades[-1])
                in_position = False
            elif pnl >= 0.05: # Hard TP
                trades[-1]['exit_price'] = current['close']
                trades[-1]['pnl'] = pnl * trades[-1]['risk_multiplier'] * 3.3
                recent_trades.append(trades[-1])
                in_position = False

    return trades

def optimize():
    rsi = 40
    adx = 20
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
    
    print("🚀 Starting Iteration 49 Auto-Optimization...")
    
    while True:
        all_trades = []
        for symbol in symbols:
            df = fetch_backtest_data(symbol, days=60)
            trades = run_backtest_v49(df, symbol, rsi, adx)
            all_trades.extend(trades)
        
        print(f"Testing RSI < {rsi}, ADX > {adx} | Total Trades: {len(all_trades)}")
        
        if len(all_trades) >= 10 or rsi > 60:
            break
        
        rsi += 2
        adx -= 2
        if adx < 5: adx = 5

    print(f"\n✅ Optimization Complete!")
    print(f"Optimal Parameters: RSI < {rsi}, ADX > {adx}")
    
    if all_trades:
        profitable = [t for t in all_trades if t.get('pnl', 0) > 0]
        if profitable:
            first = profitable[0]
            print(f"\n💰 First Profitable Trade:")
            print(f"   Time: {first['entry_time']}")
            print(f"   RSI: {first['rsi']:.2f}, ADX: {first['adx']:.2f}, Score: {first['score']}")
            print(f"   PnL: {first['pnl']*100:.2f}%")
    
    return rsi, adx

if __name__ == "__main__":
    optimize()
