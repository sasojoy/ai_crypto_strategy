import argparse
import pandas as pd
import numpy as np
import os
import json
import joblib
from strategy.metadata import *
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer
from backtest.engine import BacktestEngine

class Strategy:
    _last_trade_index = {}

    def __init__(self):
        self.name = f"Orbit-{VERSION}"

    def get_signal(self, df, symbol="UNKNOWN"):
        if len(df) < 100: return None, {}
        
        current_idx = len(df)
        if symbol in Strategy._last_trade_index:
            if current_idx - Strategy._last_trade_index[symbol] < COOLDOWN_BARS:
                return None, {}

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. 趨勢背景 (4H EMA 200)
        is_trend_up = latest['close'] > latest.get('ema_200_4h', latest['close'])
        
        # 2. 三重轉折確認 (ORBIT 核心)
        # A. 結構：收盤價重新站回 EMA 20
        back_above_ema20 = latest['close'] > latest['ema_20']
        # B. 價格行為：前低點獲支撐 (Low > Prev Low)
        is_support_held = latest['low'] > prev['low']
        # C. 動能：MACD 柱狀體翻紅 (Hist > 0)
        is_momentum_red = latest['hist'] > 0

        if is_trend_up and back_above_ema20 and is_support_held and is_momentum_red:
            Strategy._last_trade_index[symbol] = current_idx
            
            # 3. 結構化止損：前 3 根 K 線最低點 - 0.1% 緩衝
            recent_low = df['low'].iloc[-3:].min()
            sl_price = recent_low * 0.999
            
            risk = latest['close'] - sl_price
            if risk <= 0 or (risk / latest['close']) > 0.05:
                return None, {}
                
            tp_price = latest['close'] + (risk * RR_TARGET)
            
            return 'LONG', {
                'tp_price': tp_price,
                'sl_price': sl_price,
                'be_trigger_price': latest['close'] + (risk * BE_TRIGGER_RR),
                'timeout': 48
            }
        return None, {}

class StrategyMain:
    def __init__(self):
        self.fetcher = BinanceFetcher()
        self.trainer = ModelTrainer()
        self.strategy = Strategy()

    def run_backtest(self, symbols, days):
        print(f"🚀 Starting {VERSION} Backtest for {symbols}...")
        all_trades = []
        limit = days * 24
        Strategy._last_trade_index = {}
        
        for symbol in symbols:
            df_raw = self.fetcher.fetch_ohlcv(symbol, TIMEFRAME, limit=limit)
            if df_raw.empty: continue
            df = self.trainer.feature_engineering(df_raw)
            df['symbol'] = symbol
            engine = BacktestEngine()
            results = engine.run(df, self.strategy)
            all_trades.extend(results.get('all_trades', []))
            
        if not all_trades:
            print("No trades executed.")
            return

        trade_df = pd.DataFrame(all_trades)
        win_rate = (trade_df['pnl'] > 0).mean()
        trade_df['cum_balance'] = trade_df['pnl'].cumsum() + 10000
        max_drawdown = ((trade_df['cum_balance'].cummax() - trade_df['cum_balance']) / trade_df['cum_balance'].cummax()).max()
        pf = trade_df[trade_df['pnl']>0]['pnl'].sum() / abs(trade_df[trade_df['pnl']<=0]['pnl'].sum()) if (trade_df['pnl']<=0).any() else 999

        final_metrics = {
            'total_trades': len(all_trades),
            'win_rate': float(win_rate),
            'expectancy': float(trade_df['return'].mean()),
            'max_drawdown': float(max_drawdown),
            'profit_factor': float(pf),
            'exit_type_counts': trade_df['exit_type'].value_counts().to_dict()
        }
        
        os.makedirs('/workspace/ai_crypto_strategy/logs', exist_ok=True)
        with open('/workspace/ai_crypto_strategy/logs/backtest_report.json', 'w') as f:
            json.dump(final_metrics, f, indent=4)
            
        print(f"\n【{VERSION} 最終報表】\n" + "-"*40)
        for k, v in final_metrics.items(): print(f"{k}: {v}")
        print("-" * 40)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='backtest')
    parser.add_argument('--symbols', type=str, default='BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,LINKUSDT')
    parser.add_argument('--days', type=int, default=120)
    args = parser.parse_args()
    if args.mode == 'backtest':
        StrategyMain().run_backtest(args.symbols.split(','), args.days)
