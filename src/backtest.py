
import ccxt
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from src.indicators import calculate_rsi, calculate_ema, calculate_atr
from src.features import calculate_features as extract_features
from src.ml_model import CryptoMLModel
from src.core.engine import TradingAccount, MarketEnvironment
from src.core.strategy import H16Strategy
from src.core.audit_manager import AuditManager

def fetch_backtest_data(symbol='BTC/USDT', timeframe='15m', days=30):
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
    df.set_index('timestamp', inplace=True)
    return df

def run_unified_backtest(symbols, ml_model, account):
    strategy = H16Strategy()
    market = MarketEnvironment()
    
    print("Fetching data for all symbols...")
    btc_df = fetch_backtest_data('BTC/USDT', '15m', 30)
    
    symbol_data = {}
    for symbol in symbols:
        df = fetch_backtest_data(symbol, '15m', 30)
        features = extract_features(df, btc_df)
        df = df.loc[features.index]
        df_1h = df.resample('1h').last().ffill()
        symbol_data[symbol] = {
            'df': df,
            'features': features,
            'df_1h': df_1h,
            'in_position': False,
            'entry_price': 0,
            'entry_time': None,
            'entry_index': 0,
            'breakeven_active': False,
            'pos_size': 0,
            'tp_price': 0,
            'sl_price': 0,
            'last_trade_time': datetime(2000, 1, 1)
        }

    # Get all unique timestamps across all symbols and sort them
    all_timestamps = sorted(pd.concat([data['df'].index.to_series() for data in symbol_data.values()]).unique())
    
    print(f"Starting unified backtest across {len(all_timestamps)} timestamps...")
    
    for current_time in all_timestamps:
        for symbol in symbols:
            data = symbol_data[symbol]
            df = data['df']
            
            if current_time not in df.index:
                continue
                
            current_price = df.at[current_time, 'close']
            i = df.index.get_loc(current_time)
            
            if i < 200: continue # Warmup

            if not data['in_position']:
                # 1. Cooldown Check (4h)
                if (current_time - data['last_trade_time']).total_seconds() < 14400:
                    continue
                    
                # 2. AI Score
                X = data['features'].iloc[i:i+1]
                probs = ml_model.predict_proba(X)
                ml_score = float(probs[0][1]) if hasattr(probs, "ndim") and probs.ndim == 2 else float(probs)
                
                # 3. H16 Integrated Signal Logic
                current_1h_time = current_time.replace(minute=0, second=0, microsecond=0)
                df_1h_slice = data['df_1h'].loc[:current_1h_time].tail(100)
                df_15m_slice = df.iloc[:i+1].tail(100)
                
                is_signal, reason = strategy.get_signal(symbol, ml_score, df_1h_slice, df_15m_slice)
                
                if is_signal:
                    vol_level, vol_val = market.get_volatility_level(df_15m_slice)
                    pos_size = strategy.calculate_size(account.balance, ml_score, vol_val)
                    
                    data['in_position'] = True
                    data['entry_price'] = current_price
                    data['entry_time'] = current_time
                    data['entry_index'] = i
                    data['breakeven_active'] = False
                    data['pos_size'] = pos_size
                    
                    data['sl_price'] = current_price * 0.985
                    data['tp_price'] = current_price * 1.03
            
            elif data['in_position']:
                df_15m_slice = df.iloc[:i+1].tail(100)
                time_exit, breakeven_active, new_sl = strategy.get_exit_logic(
                    data['entry_price'], current_price, i, data['entry_index'], df_15m_slice, data['breakeven_active']
                )
                data['breakeven_active'] = breakeven_active
                if new_sl: data['sl_price'] = new_sl

                if current_price >= data['tp_price'] or current_price <= data['sl_price'] or time_exit:
                    reason = "TP/SL" if not time_exit else "Time Exit"
                    account.execute_trade(symbol, data['entry_time'], current_time, data['entry_price'], current_price, data['pos_size'], reason)
                    data['in_position'] = False
                    data['last_trade_time'] = current_time

if __name__ == "__main__":
    # 1. Strategy Manifest Audit (MANDATORY FIRST STEP)
    auditor = AuditManager(
        strategy_path='src/core/strategy.py',
        engine_path='src/core/engine.py'
    )
    auditor.print_manifest_table()

    results_file = 'backtest_results.csv'
    if os.path.exists(results_file):
        os.remove(results_file)
        print(f"已物理刪除舊的 {results_file}")

    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    initial_balance = 10000
    account = TradingAccount(initial_balance)
    
    ml_model = CryptoMLModel()
    if not ml_model.load():
        print("❌ Model not found.")
        exit()

    run_unified_backtest(symbols, ml_model, account)

    trades_df = account.get_equity_curve()
    if not trades_df.empty:
        trades_df.to_csv(results_file, index=False)
        print(f"\n✅ 所有回測結果已存入 {results_file}")
        
        # Summary
        total_trades = len(trades_df)
        win_rate = (trades_df['profit_pct'] > 0).sum() / total_trades * 100
        net_profit = account.balance - initial_balance
        
        print(f"\n--- H16 PREDATOR 統一錢包回測報告 ---")
        print(f"起始資金: ${initial_balance}")
        print(f"最終餘額: ${account.balance:.2f}")
        print(f"淨獲利: ${net_profit:.2f}")
        print(f"總交易次數: {total_trades}")
        print(f"總勝率: {win_rate:.2f}%")
        
        print("\n--- 物理證據 (head -n 15) ---")
        os.system(f"head -n 15 {results_file}")
