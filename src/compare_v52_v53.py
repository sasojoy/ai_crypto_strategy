
import pandas as pd
import numpy as np
from src.backtest_v48 import fetch_backtest_data
from src.indicators import calculate_rsi, calculate_macd, calculate_ema, calculate_atr, calculate_bollinger_bands, calculate_squeeze_index, calculate_macd_divergence, calculate_adx
from datetime import datetime

def run_backtest(df, btc_df, version='v53'):
    df = df.copy()
    df['rsi'] = calculate_rsi(df)
    df['ema200'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['squeeze'] = calculate_squeeze_index(df)
    df['macd_div'] = calculate_macd_divergence(df)
    
    # Join BTC 24h change
    btc_df = btc_df.copy()
    btc_df['btc_change_24h'] = btc_df['close'].pct_change(96) # 15m * 96 = 24h
    df = df.join(btc_df[['btc_change_24h']], how='left')
    df['coin_change_24h'] = df['close'].pct_change(96)
    
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    entry_price = 0
    partial_tp_done = False
    pos_size = 1.0
    
    for i in range(10, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        
        if not in_position:
            # Entry Logic (Iteration 52/53)
            trend_mode = curr['close'] > curr['ema200']
            rel_strength = curr['coin_change_24h'] > curr['btc_change_24h']
            
            trend_entry = trend_mode and curr['rsi'] < 45 and curr['macd_hist'] > prev['macd_hist'] and rel_strength
            bottom_entry = (not trend_mode) and curr['rsi'] < 32 and curr['macd_div']
            squeeze_entry = curr['squeeze'] < 0.3 and curr['close'] > (curr['ema200'] + 2 * curr['atr']) # Simplified squeeze
            
            if trend_entry or bottom_entry or squeeze_entry:
                in_position = True
                entry_price = curr['close']
                partial_tp_done = False
                pos_size = 1.0
                trades.append({'entry_time': curr['timestamp'], 'entry_price': entry_price, 'type': 'LONG'})
        else:
            # Exit Logic
            pnl = (curr['close'] - entry_price) / entry_price
            atr_val = curr['atr']
            sl_price = entry_price - 1.5 * atr_val
            tp_price_1_2 = entry_price + 1.2 * (1.5 * atr_val)
            
            if version == 'v52':
                # Fixed 1.2 RR TP
                if curr['close'] >= tp_price_1_2:
                    trades[-1]['exit_price'] = curr['close']
                    trades[-1]['pnl'] = (curr['close'] - entry_price) / entry_price
                    trades[-1]['exit_reason'] = 'TP 1.2RR'
                    in_position = False
                elif curr['close'] <= sl_price:
                    trades[-1]['exit_price'] = curr['close']
                    trades[-1]['pnl'] = (curr['close'] - entry_price) / entry_price
                    trades[-1]['exit_reason'] = 'SL'
                    in_position = False
            else:
                # Iteration 53: Partial TP + EMA 10 Trailing
                if not partial_tp_done:
                    if curr['close'] >= tp_price_1_2:
                        partial_tp_done = True
                        # We simulate partial TP by adjusting the effective PnL later
                        # or just tracking it here. For simplicity in comparison:
                        trades[-1]['partial_tp_price'] = curr['close']
                        trades[-1]['partial_tp_time'] = curr['timestamp']
                    elif curr['close'] <= sl_price:
                        trades[-1]['exit_price'] = curr['close']
                        trades[-1]['pnl'] = (curr['close'] - entry_price) / entry_price
                        trades[-1]['exit_reason'] = 'SL'
                        in_position = False
                else:
                    # Trailing with EMA 10
                    ema10 = calculate_ema(df.iloc[:i+1], 10).iloc[-1]
                    if curr['close'] < ema10:
                        trades[-1]['exit_price'] = curr['close']
                        # PnL = 50% * 1.2RR + 50% * (EMA10 - Entry)/Entry
                        p1 = (trades[-1]['partial_tp_price'] - entry_price) / entry_price
                        p2 = (curr['close'] - entry_price) / entry_price
                        trades[-1]['pnl'] = 0.5 * p1 + 0.5 * p2
                        trades[-1]['exit_reason'] = 'EMA10 Trailing'
                        trades[-1]['is_homerun'] = p2 > p1
                        in_position = False

    return trades

def analyze():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    results = []
    
    btc_df = fetch_backtest_data('BTC/USDT', days=60)
    
    for symbol in symbols:
        df = fetch_backtest_data(symbol, days=60)
        trades_v52 = run_backtest(df, btc_df, version='v52')
        trades_v53 = run_backtest(df, btc_df, version='v53')
        
        pnl_v52 = sum([t['pnl'] for t in trades_v52 if 'pnl' in t])
        pnl_v53 = sum([t['pnl'] for t in trades_v53 if 'pnl' in t])
        
        max_win_v52 = max([t['pnl'] for t in trades_v52 if 'pnl' in t]) if trades_v52 else 0
        max_win_v53 = max([t['pnl'] for t in trades_v53 if 'pnl' in t]) if trades_v53 else 0
        
        homeruns = [t for t in trades_v53 if t.get('is_homerun')]
        best_homerun = max(homeruns, key=lambda x: x['pnl']) if homeruns else None
        
        results.append({
            'symbol': symbol,
            'v52_pnl': pnl_v52,
            'v53_pnl': pnl_v53,
            'v52_max_win': max_win_v52,
            'v53_max_win': max_win_v53,
            'best_homerun': best_homerun
        })

    print("\n📊 --- Iteration 52 vs 53 Comparison ---")
    total_v52 = 0
    total_v53 = 0
    for r in results:
        print(f"\n🪙 {r['symbol']}:")
        print(f"   v52 PnL: {r['v52_pnl']*100:.2f}% | Max Win: {r['v52_max_win']*100:.2f}%")
        print(f"   v53 PnL: {r['v53_pnl']*100:.2f}% | Max Win: {r['v53_max_win']*100:.2f}%")
        if r['best_homerun']:
            print(f"   🏆 Home Run: {r['best_homerun']['entry_time']} | PnL: {r['best_homerun']['pnl']*100:.2f}%")
        total_v52 += r['v52_pnl']
        total_v53 += r['v53_pnl']
    
    print(f"\n📈 Total PnL Comparison:")
    print(f"   Iteration 52: {total_v52*100:.2f}%")
    print(f"   Iteration 53: {total_v53*100:.2f}%")
    print(f"   Improvement: {(total_v53 - total_v52)*100:.2f}%")

if __name__ == "__main__":
    analyze()
