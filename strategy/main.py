import argparse
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer
from backtest.engine import BacktestEngine

class StrategyMain:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        self.config_path = config_path
        self.fetcher = BinanceFetcher(config_path)
        self.trainer = ModelTrainer()
        self.ML_PROB_THRESHOLD = 0.0 # Bypass ML for 180.0

    def run_backtest(self, symbols=['BTCUSDT'], timeframe='1h', limit=4320, verbose=True):
        if verbose: print(f"🚀 Starting 180.0 {timeframe} Trend Breakout Backtest for {symbols}...")
        
        end_time = datetime.now()
        all_dfs = []
        
        for symbol in symbols:
            if verbose: print(f"Processing Symbol: {symbol} (Feature Engineering)...")
            df_raw = self.fetcher.fetch_ohlcv(symbol, timeframe, limit=limit, end_time=end_time)
            if df_raw.empty: continue
            
            df = self.trainer.feature_engineering(df_raw)
            df['symbol'] = symbol
            all_dfs.append(df)
            
        if not all_dfs:
            print("No data fetched.")
            return
            
        pooled_df = pd.concat(all_dfs, axis=0)
        self.trainer.train(pooled_df)
        
        all_trades = []
        for symbol in symbols:
            if verbose: print(f"Processing Symbol: {symbol} (Backtesting)...")
            test_df = pooled_df[pooled_df['symbol'] == symbol].copy()
            if test_df.empty: continue
            
            ml_scores = np.ones(len(test_df))
            engine = BacktestEngine(config_path=self.config_path)
            results = engine.run(test_df, ml_scores, threshold=self.ML_PROB_THRESHOLD)
            
            if 'all_trades' in results:
                all_trades.extend(results['all_trades'])
                
        if not all_trades:
            print("【180.0 審計】無交易執行")
            return
            
        trade_df = pd.DataFrame(all_trades)
        win_rate = (trade_df['pnl'] > 0).mean()
        expectancy = trade_df['return'].mean()
        
        trade_df['cum_balance'] = trade_df['pnl'].cumsum() + 10000
        balance_series = pd.Series([10000] + trade_df['cum_balance'].tolist())
        cum_max = balance_series.cummax()
        drawdowns = (balance_series - cum_max) / cum_max
        max_drawdown = float(drawdowns.min())
        
        wins = trade_df[trade_df['pnl'] > 0]
        losses = trade_df[trade_df['pnl'] <= 0]
        gross_profits = wins['pnl'].sum()
        gross_losses = abs(losses['pnl'].sum())
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else 0.0
        
        final_metrics = {
            'total_trades': len(all_trades),
            'win_rate': float(win_rate),
            'expectancy': float(expectancy),
            'max_drawdown': max_drawdown,
            'profit_factor': float(profit_factor),
            'exit_type_counts': trade_df['exit_type'].value_counts().to_dict()
        }
        
        os.makedirs('/workspace/ai_crypto_strategy/logs', exist_ok=True)
        with open('/workspace/ai_crypto_strategy/logs/backtest_report.json', 'w') as f:
            json.dump(final_metrics, f, indent=4)
            
        print("\n" + "="*40)
        print(f"【180.0 核心戰術 - 最終報表】")
        print("-" * 40)
        print(f"總交易次數 (N): {len(all_trades)}")
        print(f"勝率 (Win Rate): {win_rate*100:.2f}%")
        print(f"期望值 (Expectancy): {expectancy*100:.4f}%")
        print(f"最大回撤 (MaxDD): {max_drawdown*100:.2f}%")
        print(f"盈虧比 (PF): {profit_factor:.2f}")
        print(f"結束類型: {final_metrics['exit_type_counts']}")
        print("="*40)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='backtest')
    parser.add_argument('--symbols', type=str, default='BTCUSDT')
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--verbose', type=bool, default=True)
    args = parser.parse_args()
    
    strategy = StrategyMain()
    limit = args.days * 24
    strategy.run_backtest(symbols=args.symbols.split(','), timeframe='1h', limit=limit, verbose=args.verbose)
