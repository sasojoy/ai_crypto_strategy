
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.market import calculate_rsi, calculate_ema, calculate_macd, calculate_adx, calculate_atr

def fetch_backtest_data_range(symbol, start_date, end_date, timeframe='15m'):
    exchange = ccxt.binance()
    since = exchange.parse8601(start_date + "T00:00:00Z")
    end_ts = exchange.parse8601(end_date + "T23:59:59Z")
    
    all_ohlcv = []
    while since < end_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
        if not ohlcv:
            break
        since = ohlcv[-1][0] + 1
        all_ohlcv.extend(ohlcv)
        if since >= exchange.milliseconds():
            break
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def run_backtest_v50(df, symbol, rsi_thresh=40, adx_thresh=20):
    df = df.copy()
    df['rsi'] = calculate_rsi(df)
    df['ema200_1h'] = calculate_ema(df, 200 * 4)
    df['ema10_15m'] = calculate_ema(df, 10)
    df['atr'] = calculate_atr(df, 14)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['adx'] = calculate_adx(df)
    df = df.dropna().reset_index(drop=True)

    trades = []
    in_position = False
    entry_price = 0
    recent_trades = []
    initial_balance = 10000
    balance = initial_balance
    max_balance = initial_balance
    max_drawdown = 0
    
    for i in range(2, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Update Max Drawdown
        max_balance = max(max_balance, balance)
        drawdown = (max_balance - balance) / max_balance * 100
        max_drawdown = max(max_drawdown, drawdown)

        if not in_position:
            # Iteration 49: Dynamic Risk Calculation
            win_rate = 0.5
            losses = 0
            if len(recent_trades) >= 2:
                wins = len([t for t in recent_trades[-10:] if t.get('pnl_pct', 0) > 0])
                win_rate = wins / min(len(recent_trades), 10)
                losses = len([t for t in recent_trades[-2:] if t.get('pnl_pct', 0) < 0])
            
            risk_multiplier = 0.5 if win_rate > 0.5 else (0.2 if losses >= 2 else 0.3)

            # Iteration 48: Score-Based Entry
            if current['close'] > current['ema200_1h']:
                score = 0
                if current['rsi'] < rsi_thresh: score += 1
                if current['macd_hist'] > prev['macd_hist']: score += 1
                if current['adx'] > adx_thresh: score += 1
                
                # Iteration 50: Funding Rate Shield (Simulated: Block if RSI is extremely high or price pump)
                # In backtest, we don't have historical funding easily, so we use a proxy
                funding_shield_active = current['rsi'] > 75 
                
                # Iteration 50: Slippage Protection (Simulated: Block if volume is too low)
                avg_vol = df['volume'].iloc[max(0, i-20):i].mean()
                slippage_shield_active = current['volume'] < avg_vol * 0.5

                if score >= 2 and not funding_shield_active and not slippage_shield_active:
                    in_position = True
                    entry_price = current['close']
                    sl_distance = 1.5 * current['atr']
                    risk_amount = balance * 0.025 * risk_multiplier
                    pos_size = risk_amount / sl_distance if sl_distance > 0 else 0
                    
                    trades.append({
                        'entry_time': current['timestamp'], 
                        'entry_price': entry_price, 
                        'pos_size': pos_size,
                        'risk_multiplier': risk_multiplier
                    })
        else:
            # Iteration 49: Exit Logic
            pnl_pct = (current['close'] - entry_price) / entry_price
            
            # Trailing Stop: Close if price < EMA 10 and profit > 1.5%
            exit_triggered = False
            if pnl_pct > 0.015 and current['close'] < current['ema10_15m']:
                exit_triggered = True
                reason = 'EMA10_Trailing'
            elif pnl_pct <= -0.015:
                exit_triggered = True
                reason = 'SL'
            elif pnl_pct >= 0.05:
                exit_triggered = True
                reason = 'TP'

            if exit_triggered:
                pnl_amount = pnl_pct * entry_price * trades[-1]['pos_size']
                balance += pnl_amount
                trades[-1].update({
                    'exit_time': current['timestamp'],
                    'exit_price': current['close'],
                    'pnl_pct': pnl_pct,
                    'pnl_amount': pnl_amount,
                    'reason': reason
                })
                recent_trades.append(trades[-1])
                in_position = False

    return trades, max_drawdown, balance

if __name__ == "__main__":
    # Extreme Date: 2024-04-13 (Crypto Crash)
    start = "2024-04-01"
    end = "2024-04-20"
    symbol = "SOL/USDT"
    
    print(f"🔥 Starting Iteration 50 Extreme Backtest ({start} to {end})...")
    df = fetch_backtest_data_range(symbol, start, end)
    if df.empty:
        print("Failed to fetch data. Check dates or symbol.")
    else:
        trades, max_dd, final_balance = run_backtest_v50(df, symbol)
        print(f"\n📊 Results for {symbol}:")
        print(f"   • Total Trades: {len(trades)}")
        print(f"   • Final Balance: ${final_balance:.2f}")
        print(f"   • Max Drawdown: {max_dd:.2f}%")
        
        if max_dd < 15:
            print("✅ [Iteration 50] Survival Test PASSED! Drawdown < 15%.")
        else:
            print("❌ [Iteration 50] Survival Test FAILED! Drawdown > 15%.")
