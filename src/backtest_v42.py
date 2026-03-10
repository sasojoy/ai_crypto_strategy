






import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from src.market import calculate_rsi, calculate_ema, calculate_atr, calculate_bollinger_bands, calculate_macd, calculate_stoch_rsi

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=60):
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
    return df

def run_backtest_v42(df, symbol, btc_df, initial_balance=1000, mode='v42'):
    # Indicators
    df['rsi'] = calculate_rsi(df)
    df['ema20'] = calculate_ema(df, 20)
    df['ema50'] = calculate_ema(df, 50)
    df['ema200_15m'] = calculate_ema(df, 200)
    df['atr'] = calculate_atr(df, 14)
    df['bb_upper'], df['bb_lower'], df['bandwidth'], _ = calculate_bollinger_bands(df, 20, 2)
    df['ema200_4h'] = calculate_ema(df, 200 * 16)
    df['ema200_1h'] = calculate_ema(df, 200 * 4)
    _, _, df['macd_hist'] = calculate_macd(df)
    df['stoch_k'], df['stoch_d'] = calculate_stoch_rsi(df)
    
    df = df.dropna().reset_index(drop=True)
    
    trades = []
    in_position = False
    entry_price = 0
    balance = initial_balance
    sl_price = 0
    tp_price = 0
    highest_price = 0
    partial_tp_hit = False
    
    last_exit_time = None
    last_exit_reason = None
    last_entry_rsi = 0
    waterfall_pause_until = None

    asset_weights = {
        'BTC/USDT': 1.0,
        'ETH/USDT': 1.2,
        'SOL/USDT': 1.0,
        'NEAR/USDT': 0.3,
        'AVAX/USDT': 0.3,
        'FET/USDT': 0.3,
        'ARB/USDT': 0.3
    }
    asset_weight = asset_weights.get(symbol, 0.3)

    for i in range(10, len(df)):
        current_row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        # Waterfall Guard Check
        btc_row = btc_df[btc_df['timestamp'] == current_row['timestamp']]
        if not btc_row.empty:
            btc_idx = btc_row.index[0]
            if btc_idx > 0:
                btc_prev = btc_df.iloc[btc_idx-1]
                btc_change = (btc_row.iloc[0]['close'] - btc_prev['close']) / btc_prev['close'] * 100
                if btc_change < -1.2:
                    waterfall_pause_until = current_row['timestamp'] + timedelta(hours=2)

        if not in_position:
            # Waterfall Guard Active?
            if waterfall_pause_until and current_row['timestamp'] < waterfall_pause_until:
                continue

            # Entry Logic
            trend_4h_strong = current_row['close'] > current_row['ema200_4h']
            trend_1h_strong = current_row['close'] > current_row['ema200_1h']
            
            # MACD Divergence
            price_down = current_row['close'] < df['close'].iloc[i-5]
            macd_up = current_row['macd_hist'] > df['macd_hist'].iloc[i-5]
            macd_bullish_div = price_down and macd_up
            
            # RSI Divergence
            rsi_up = current_row['rsi'] > df['rsi'].iloc[i-5]
            rsi_bullish_div = price_down and rsi_up
            
            double_div = macd_bullish_div and rsi_bullish_div

            if mode == 'v45':
                # Iteration 45: Squeeze Filter
                bandwidth_avg_100 = df['bandwidth'].iloc[i-100:i].mean()
                squeeze_active = current_row['bandwidth'] < (bandwidth_avg_100 * 0.8) if bandwidth_avg_100 > 0 else False
                
                # Iteration 45: StochRSI Confirmation
                stoch_oversold = current_row['stoch_k'] < 20 and current_row['stoch_d'] < 20
                stoch_golden_cross = prev_row['stoch_k'] <= prev_row['stoch_d'] and current_row['stoch_k'] > current_row['stoch_d']
                stoch_rsi_ok = stoch_oversold and stoch_golden_cross
                rsi_oversold_45 = current_row['rsi'] < 38
                
                # Hybrid Trigger from v42
                extreme_mode = current_row['rsi'] < 30
                structural_mode = current_row['rsi'] < 38 and double_div
                hybrid_trigger = extreme_mode or structural_mode
                
                # Volume Exhaustion from v42
                avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                vol_exhaustion = current_row['volume'] < (avg_vol_5 * 1.2)
                
                entry_allowed = trend_4h_strong and trend_1h_strong and hybrid_trigger and squeeze_active and stoch_rsi_ok and rsi_oversold_45
            elif mode == 'v42':
                extreme_mode = current_row['rsi'] < 30
                structural_mode = current_row['rsi'] < 38 and double_div
                hybrid_trigger = extreme_mode or structural_mode
                
                if symbol in ['SOL/USDT', 'BTC/USDT', 'ETH/USDT']:
                    vol_buffer = 1.2
                    avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                    vol_exhaustion = current_row['volume'] < (avg_vol_5 * vol_buffer)
                else:
                    if current_row['rsi'] < 30:
                        vol_exhaustion = True
                    else:
                        avg_vol_5 = df['volume'].iloc[i-5:i].mean()
                        vol_exhaustion = current_row['volume'] < (avg_vol_5 * 1.1)
                
                entry_allowed = trend_4h_strong and trend_1h_strong and hybrid_trigger
            else: # v41
                extreme_mode = current_row['rsi'] < 30
                structural_mode = current_row['rsi'] < 38 and macd_bullish_div
                hybrid_trigger = extreme_mode or structural_mode
                vol_exhaustion = True # Simplified for comparison
                entry_allowed = trend_4h_strong and trend_1h_strong and hybrid_trigger
                
            price_at_bb_lower = current_row['low'] <= current_row['bb_lower']
            ema_golden_cross = current_row['ema20'] > current_row['ema50'] and prev_row['ema20'] <= prev_row['ema50']
            rsi_hook_up = current_row['rsi'] > prev_row['rsi']
            first_green = current_row['close'] > current_row['open']
            
            long_signal = entry_allowed and vol_exhaustion and (price_at_bb_lower or ema_golden_cross) and rsi_hook_up and first_green
            
            if long_signal:
                in_position = True
                entry_price = current_row['close']
                entry_time = current_row['timestamp']
                highest_price = entry_price
                partial_tp_hit = False
                
                # Sizing
                dist_ema200_pct = abs(entry_price - current_row['ema200_4h']) / current_row['ema200_4h'] * 100
                base_risk = 0.025 * asset_weight
                risk_pct = base_risk * 1.2 if dist_ema200_pct < 1.5 else (base_risk * 0.6 if dist_ema200_pct > 5.0 else base_risk)
                
                sl_distance = 1.5 * current_row['atr']
                risk_amount = balance * risk_pct
                pos_size = risk_amount / sl_distance
                if pos_size * entry_price > balance * 0.95:
                    pos_size = (balance * 0.95) / entry_price
                
                sl_price = entry_price - sl_distance
                tp_price_atr = entry_price + (3.0 * current_row['atr'])
                tp_price = min(tp_price_atr, current_row['bb_upper'])
        
        else:
            current_price = current_row['close']
            highest_price = max(highest_price, current_price)
            profit_pct = (current_price - entry_price) / entry_price * 100
            
            exit_triggered = False
            exit_reason = ""
            
            highest_pnl = (highest_price - entry_price) / entry_price * 100
            
            if highest_pnl >= 2.0:
                chandelier_sl = highest_price * 0.995
                if current_price <= chandelier_sl:
                    exit_triggered = True
                    exit_reason = "Chandelier_Exit"
            
            if not exit_triggered and highest_pnl >= 3.0:
                retracement = (highest_pnl - profit_pct) / highest_pnl
                if retracement >= 0.20:
                    exit_triggered = True
                    exit_reason = "Profit Protection"
            
            if not exit_triggered and current_price <= sl_price:
                exit_triggered = True
                exit_reason = "SL"
            
            if not exit_triggered and not partial_tp_hit:
                if mode == 'v45':
                    if profit_pct >= 1.5:
                        sl_price = entry_price * 1.001
                        partial_tp_hit = True
                else:
                    if current_price >= tp_price:
                        sl_price = max(sl_price, entry_price)
                        partial_tp_hit = True
            
            if partial_tp_hit:
                trailing_sl = highest_price * 0.985
                sl_price = max(sl_price, trailing_sl)
            
            if exit_triggered:
                pnl_amount = (current_price - entry_price) * pos_size
                balance += pnl_amount
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_row['timestamp'],
                    'profit_pct': profit_pct,
                    'pnl': pnl_amount,
                    'balance': balance,
                    'reason': exit_reason
                })
                in_position = False

    if not trades:
        return {"net_profit_pct": 0, "win_rate": 0, "total_trades": 0, "final_balance": balance}

    trades_df = pd.DataFrame(trades)
    net_profit_pct = (balance - initial_balance) / initial_balance * 100
    win_rate = (trades_df['pnl'] > 0).sum() / len(trades_df) * 100
    
    return {
        "net_profit_pct": net_profit_pct,
        "win_rate": win_rate,
        "total_trades": len(trades_df),
        "final_balance": balance
    }

if __name__ == "__main__":
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT', 'FET/USDT', 'ARB/USDT']
    results = {}
    
    print("Fetching BTC data for Waterfall Guard...")
    btc_df = fetch_backtest_data('BTC/USDT', days=60)

    for symbol in symbols:
        print(f"Fetching data for {symbol} (60 days)...")
        try:
            df = fetch_backtest_data(symbol, days=60)
            
            res_v41 = run_backtest_v42(df.copy(), symbol, btc_df, mode='v41')
            res_v42 = run_backtest_v42(df.copy(), symbol, btc_df, mode='v42')
            
            results[symbol] = {
                "v41": res_v41,
                "v42": res_v42
            }
        except Exception as e:
            print(f"Error backtesting {symbol}: {e}")
    
    print("\n" + "="*60)
    print("FINAL COMPARISON: Iteration 42 vs Iteration 41 (60 Days)")
    print("="*60)
    
    total_trades_v41 = 0
    total_trades_v42 = 0
    total_profit_v41 = 0
    total_profit_v42 = 0
    
    for symbol, data in results.items():
        v41 = data['v41']
        v42 = data['v42']
        print(f"\n[{symbol}]")
        print(f"  V41: Profit {v41['net_profit_pct']:.2f}%, WinRate {v41['win_rate']:.2f}%, Trades {v41['total_trades']}")
        print(f"  V42: Profit {v42['net_profit_pct']:.2f}%, WinRate {v42['win_rate']:.2f}%, Trades {v42['total_trades']}")
        
        total_trades_v41 += v41['total_trades']
        total_trades_v42 += v42['total_trades']
        total_profit_v41 += v41['net_profit_pct']
        total_profit_v42 += v42['net_profit_pct']

    print("\n" + "="*60)
    print(f"OVERALL SUMMARY (60 Days):")
    print(f"  V41: Total Profit {total_profit_v41:.2f}%, Total Trades {total_trades_v41}")
    print(f"  V42: Total Profit {total_profit_v42:.2f}%, Total Trades {total_trades_v42}")
    print("="*60)

    with open('data/backtest_results_v42.json', 'w') as f:
        json.dump(results, f, indent=4)






