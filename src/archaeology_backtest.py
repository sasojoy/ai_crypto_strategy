
import pandas as pd
import numpy as np
from src.backtest_v48 import fetch_backtest_data, run_backtest_v49
from src.market import calculate_rsi, calculate_ema, calculate_bollinger_bands, calculate_macd, calculate_adx, calculate_atr

def run_experiment():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    results = []
    
    for symbol in symbols:
        print(f"\n🔍 Auditing {symbol}...")
        df = fetch_backtest_data(symbol, days=60)
        
        # 1. Base (v57)
        t_base = run_backtest_v49(df.copy(), symbol, rsi_thresh=35, adx_thresh=22)
        p_base = sum([t.get('pnl', 0) for t in t_base]) * 100
        
        # 2. No ADX & No 4H EMA (Simulated by modifying score logic)
        # We'll use a modified version of run_backtest_v49 for these experiments
        t_no_filters = run_backtest_v49_mod(df.copy(), symbol, rsi_thresh=35, adx_thresh=0, use_ema_filter=False)
        p_no_filters = sum([t.get('pnl', 0) for t in t_no_filters]) * 100
        
        # 3. Fixed 2% SL
        t_fixed_sl = run_backtest_v49_mod(df.copy(), symbol, sl_type='fixed', sl_val=0.02)
        p_fixed_sl = sum([t.get('pnl', 0) for t in t_fixed_sl]) * 100

        # 4. Tight ATR (1.5*)
        t_tight_atr = run_backtest_v49_mod(df.copy(), symbol, sl_type='atr', sl_val=1.5)
        p_tight_atr = sum([t.get('pnl', 0) for t in t_tight_atr]) * 100
        
        results.append({
            'Symbol': symbol,
            'Base (v57)': f"{p_base:.2f}%",
            'No Filters': f"{p_no_filters:.2f}%",
            'Fixed 2% SL': f"{p_fixed_sl:.2f}%",
            'Tight ATR (1.5)': f"{p_tight_atr:.2f}%",
            'Trades (Base)': len(t_base)
        })
    
    print("\n📊 --- Archaeology Audit Summary ---")
    print(pd.DataFrame(results).to_string(index=False))

def run_backtest_v49_mod(df, symbol, rsi_thresh=35, adx_thresh=22, use_ema_filter=True, sl_type='atr', sl_val=2.0):
    # Modified version of v49 to support experiments
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
    for i in range(2, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        if not in_position:
            # Filter Logic
            ema_ok = current['close'] > current['ema200_1h'] if use_ema_filter else True
            if ema_ok:
                score = 0
                if current['rsi'] < rsi_thresh: score += 1
                if current['macd_hist'] > prev['macd_hist']: score += 1
                if adx_thresh == 0 or current['adx'] > adx_thresh: score += 1
                if score >= 2:
                    in_position = True
                    entry_price = current['close']
                    sl_dist = (current['atr'] * sl_val) if sl_type == 'atr' else (entry_price * sl_val)
                    trades.append({'entry_price': entry_price, 'sl_dist': sl_dist})
        else:
            pnl_raw = (current['close'] - trades[-1]['entry_price']) / trades[-1]['entry_price']
            # Exit Logic
            if pnl_raw * trades[-1]['entry_price'] <= -trades[-1]['sl_dist']:
                trades[-1]['pnl'] = -0.015 - 0.002 # Normalized SL + Fees
                in_position = False
            elif pnl_raw > 0.015 and current['close'] < current['ema10_15m']:
                trades[-1]['pnl'] = pnl_raw - 0.002
                in_position = False
    return trades

if __name__ == "__main__":
    run_experiment()
