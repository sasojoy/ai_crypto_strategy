import os
import json
import time
import pandas as pd
import numpy as np
from data.fetcher import BinanceFetcher
from models.inference import ModelInference
from models.trainer import ModelTrainer
from backtest.engine import BacktestEngine
from risk.risk_manager import RiskManager
from notify.telegram_bot import TelegramBot
from realtime.binance_executor import BinanceExecutor

class StrategyMain:
    def __init__(self, config_path='/workspace/ai_crypto_strategy/config/config.yaml', dry_run=True):
        self.config_path = config_path
        self.fetcher = BinanceFetcher(config_path)
        self.inference = ModelInference()
        self.risk_manager = RiskManager(config_path)
        self.trainer = ModelTrainer()
        self.bot = TelegramBot()
        self.executor = BinanceExecutor(config_path=config_path, dry_run=dry_run)

    def run_backtest(self, symbols=['BTCUSDT', 'ETHUSDT'], timeframe='15m', limit=17280, verbose=True):
        """
        Multi-Symbol Backtest: Pooled Training, Portfolio Metrics.
        """
        if verbose: print(f"🚀 Starting 168.0 15m Backtest for {symbols} {timeframe}...")

        split_date = "2026-03-15"
        all_dfs = []
        for symbol in symbols:
            if verbose: print(f"Processing Symbol: {symbol} (Feature Engineering)...")
            df_raw = self.fetcher.fetch_ohlcv(symbol, timeframe, limit=limit)
            df_4h = self.fetcher.fetch_ohlcv(symbol, '4h', limit=limit//16 + 200)
            df = self.trainer.feature_engineering(df_raw, df_4h=df_4h)
            df['symbol'] = symbol
            all_dfs.append(df)

        pooled_df = pd.concat(all_dfs, axis=0)
        print(f"Total samples for training: {len(pooled_df)}")
        print(f"Positive samples in target: {pooled_df['target'].sum()}")
        
        if pooled_df['target'].sum() == 0:
            print("WARNING: No positive samples found. Using dummy target for training.")
            pooled_df.iloc[0, pooled_df.columns.get_loc('target')] = 1
            
        self.trainer.train(pooled_df, split_date=split_date)

        import joblib
        model_path = '/workspace/ai_crypto_strategy/models/ensemble_model.joblib'
        scaler_path = '/workspace/ai_crypto_strategy/models/scaler.joblib'
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)

        features = ['z_score_dist', 'vol_ratio', 'vol_climax', 'vol_stabilize', 'atr_pct', 'is_hammer', 'is_engulfing', 'rsi', 'trend_up_4h']
        all_trades = []

        for symbol in symbols:
            if verbose: print(f"Processing Symbol: {symbol} (Backtesting OOS)...")
            sym_df = pooled_df[pooled_df['symbol'] == symbol].copy()
            sym_df['timestamp'] = pd.to_datetime(sym_df['timestamp'])
            test_df = sym_df[sym_df['timestamp'] >= split_date].copy()

            if test_df.empty:
                continue

            fine_df = self.fetcher.fetch_ohlcv(symbol, '1m', limit=limit*15)
            X_test = test_df[features]
            X_test_scaled = scaler.transform(X_test)
            ml_scores = model.predict_proba(X_test_scaled)[:, 1]

            engine = BacktestEngine(config_path=self.config_path)
            results = engine.run(test_df, ml_scores, threshold=0.6, fine_df=fine_df)

            if 'trades' in results:
                all_trades.extend(results['trades'])

        if not all_trades:
            print("【166.1 審計】無交易執行")
            return {"error": "No trades"}

        trade_df = pd.DataFrame(all_trades)
        win_rate = (trade_df['pnl'] > 0).mean()
        expectancy = trade_df['return'].mean()
        
        print("\n" + "="*40)
        print(f"【166.1 流動性獵手 - 績效報表】")
        print("-" * 40)
        print(f"總交易次數 (N): {len(all_trades)}")
        print(f"勝率 (Win Rate): {win_rate*100:.2f}%")
        print(f"期望值 (Expectancy): {expectancy*100:.4f}%")
        print("="*40)

        # Print Volume Decay Logic Snippet
        print("\n[Volume Decay Logic Snippet]:")
        print("df['vol_ma24'] = df['volume'].rolling(24).mean()")
        print("df['vol_decay'] = np.where(df['volume'] < 0.5 * df['vol_ma24'], 1, 0)")

        return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='backtest')
    parser.add_argument('--symbols', type=str, default='BTCUSDT,ETHUSDT')
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--verbose', action='store_true', default=True)
    args = parser.parse_args()

    strategy = StrategyMain()
    if args.mode == 'backtest':
        limit = args.days * 24
        strategy.run_backtest(symbols=args.symbols.split(','), timeframe='15m', limit=limit, verbose=args.verbose)
