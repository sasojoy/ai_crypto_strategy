
import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.indicators import calculate_atr

def get_top_10_volume_symbols():
    exchange = ccxt.binance()
    markets = exchange.fetch_tickers()
    # Filter for USDT perpetual futures (Binance uses symbol like 'BTC/USDT:USDT')
    # or just USDT pairs if futures not easily filtered. 
    # For simplicity and consistency with previous backtests, we use USDT pairs.
    usdt_pairs = [symbol for symbol in markets if symbol.endswith('/USDT')]
    sorted_pairs = sorted(usdt_pairs, key=lambda x: markets[x]['quoteVolume'], reverse=True)
    return sorted_pairs[:10]

def scan_symbol(symbol, days=30):
    exchange = ccxt.binance()
    print(f"  [Scanner] Fetching {symbol}...")
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    ohlcv = []
    while since < exchange.milliseconds():
        batch = exchange.fetch_ohlcv(symbol, '15m', since=since)
        if not batch: break
        since = batch[-1][0] + 1
        ohlcv.extend(batch)
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # 1. Gap Frequency (15m change > 2%)
    df['pct_change'] = df['close'].pct_change().abs()
    gap_count = (df['pct_change'] > 0.02).sum()
    
    # 2. Slippage Risk (Using 24h Volume as proxy)
    ticker = exchange.fetch_ticker(symbol)
    vol_24h = ticker['quoteVolume']
    
    # 3. Rebound Win Rate: "Touch 1.5*ATR after previous close, then rebound 1%"
    df['atr'] = calculate_atr(df, 14)
    wins = 0
    total_signals = 0
    
    for i in range(1, len(df) - 4):
        prev_close = df['close'].iloc[i-1]
        atr = df['atr'].iloc[i-1]
        if pd.isna(atr): continue
        
        entry_price = prev_close - 1.5 * atr
        if df['low'].iloc[i] <= entry_price:
            total_signals += 1
            # Check next 4 candles for 1% rebound
            target = entry_price * 1.01
            for j in range(i, i + 4):
                if df['high'].iloc[j] >= target:
                    wins += 1
                    break
                    
    rebound_wr = (wins / total_signals * 100) if total_signals > 0 else 0
    
    return {
        'symbol': symbol,
        'vol_24h': vol_24h,
        'gap_frequency': int(gap_count),
        'rebound_wr': round(rebound_wr, 2),
        'total_signals': total_signals
    }

if __name__ == "__main__":
    results_file = 'scanner_results.csv'
    if os.path.exists(results_file):
        os.remove(results_file)
        
    symbols = get_top_10_volume_symbols()
    print(f"Top 10 Volume Symbols: {symbols}")
    
    all_stats = []
    for symbol in symbols:
        try:
            stats = scan_symbol(symbol)
            all_stats.append(stats)
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            
    df_results = pd.DataFrame(all_stats)
    
    # Scoring: High WR, Low Gap Frequency, High Volume
    # Normalize and rank
    df_results['score'] = (df_results['rebound_wr'] * 0.5) - (df_results['gap_frequency'] * 0.3)
    df_results = df_results.sort_values(by='score', ascending=False)
    
    df_results.to_csv(results_file, index=False)
    print(f"\n✅ 掃描完成，結果已存入 {results_file}")
    
    print("\n--- 物理證據 (head -n 10) ---")
    os.system(f"head -n 10 {results_file}")
