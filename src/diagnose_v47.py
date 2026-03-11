
import pandas as pd
import numpy as np
from src.backtest_v42 import fetch_backtest_data, run_backtest_v42
from src.market import calculate_rsi, calculate_ema, calculate_atr, calculate_bollinger_bands, calculate_macd, calculate_stoch_rsi, calculate_adx

def diagnose():
    symbol = 'ETH/USDT'
    days = 60
    print(f"Diagnosing {symbol} for {days} days...")
    df = fetch_backtest_data(symbol, days=days)
    btc_df = fetch_backtest_data('BTC/USDT', days=days)
    
    # Indicators
    df['rsi'] = calculate_rsi(df)
    df['atr'] = calculate_atr(df, 14)
    df['bb_upper'], df['bb_lower'], df['bandwidth'], _ = calculate_bollinger_bands(df, 20, 2)
    df['ema200_4h'] = calculate_ema(df, 200 * 16)
    df['ema200_1h'] = calculate_ema(df, 200 * 4)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['stoch_k'], df['stoch_d'] = calculate_stoch_rsi(df)
    df['adx'] = calculate_adx(df)
    
    df = df.dropna().reset_index(drop=True)
    
    reasons = {
        "trend_4h": 0,
        "trend_1h": 0,
        "hybrid_trigger": 0,
        "vol_exhaustion": 0,
        "rsi_hook_up": 0,
        "first_green": 0,
        "stoch_rsi_ok": 0,
        "rsi_oversold_45": 0,
        "no_entry_type": 0
    }
    
    total_rows = len(df)
    for i in range(100, total_rows):
        current_row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        trend_4h_strong = current_row['close'] > current_row['ema200_4h']
        trend_1h_strong = current_row['close'] > current_row['ema200_1h']
        
        # Hybrid Trigger
        extreme_mode = current_row['rsi'] < 35
        hybrid_trigger = extreme_mode
        
        avg_vol_5 = df['volume'].iloc[i-5:i].mean()
        vol_exhaustion = current_row['volume'] < (avg_vol_5 * 1.2)
        
        rsi_hook_up = current_row['rsi'] > prev_row['rsi']
        first_green = current_row['close'] > current_row['open']
        
        stoch_golden_cross = prev_row['stoch_k'] <= prev_row['stoch_d'] and current_row['stoch_k'] > current_row['stoch_d']
        stoch_rsi_ok = stoch_golden_cross
        
        rsi_oversold_45 = current_row['rsi'] < 38
        
        bandwidth_avg_100 = df['bandwidth'].iloc[i-100:i].mean()
        squeeze_index = current_row['bandwidth'] / bandwidth_avg_100 if bandwidth_avg_100 > 0 else 1.0
        squeeze_tier1 = squeeze_index < 0.8
        squeeze_tier2 = 0.8 <= squeeze_index < 1.0
        trend_decay_active = current_row['adx'] > 22 and current_row['rsi'] < 35
        momentum_flip = df['macd_hist'].iloc[i] > df['macd_hist'].iloc[i-1] > df['macd_hist'].iloc[i-2]
        
        # Iteration 47: Relaxed 4H Trend for Trend Decay
        trend_decay_active = current_row['adx'] > 22 and current_row['rsi'] < 35
        
        if not trend_decay_active and not trend_4h_strong: reasons["trend_4h"] += 1
        elif not trend_decay_active and not trend_1h_strong: reasons["trend_1h"] += 1
        elif not hybrid_trigger: reasons["hybrid_trigger"] += 1
        elif not vol_exhaustion: reasons["vol_exhaustion"] += 1
        elif not rsi_hook_up: reasons["rsi_hook_up"] += 1
        elif not first_green: reasons["first_green"] += 1
        elif not stoch_rsi_ok: reasons["stoch_rsi_ok"] += 1
        else:
            # Check entry types
            is_entry = False
            if trend_decay_active: is_entry = True
            elif momentum_flip and current_row['low'] <= current_row['bb_lower']:
                if rsi_oversold_45: is_entry = True
            else:
                if rsi_oversold_45 and (squeeze_tier1 or squeeze_tier2): is_entry = True
            
            if not is_entry: reasons["no_entry_type"] += 1

    print(f"Total checked: {total_rows - 100}")
    for k, v in reasons.items():
        print(f"Blocked by {k}: {v}")

if __name__ == "__main__":
    diagnose()
