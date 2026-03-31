





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

    def run_backtest(self, symbol='BTCUSDT', timeframe='15m'):
        """
        Run a full backtest cycle.
        """
        print(f"Starting backtest for {symbol} {timeframe}...")
        
        # 1. Fetch Data
        df_btc = self.fetcher.fetch_ohlcv('BTCUSDT', timeframe, limit=2000)
        df_eth = self.fetcher.fetch_ohlcv('ETHUSDT', timeframe, limit=2000)
        
        # 2. Feature Engineering
        df = self.trainer.feature_engineering(df_btc, df_eth)
        
        # 3. Generate ML Scores (using the latest model)
        # For backtest, we need scores for the entire period
        # Let's use the trainer's model if available
        model_path = '/workspace/ai_crypto_strategy/models/lgbm_model.joblib'
        if not os.path.exists(model_path):
            print("Model not found. Training a new one...")
            self.trainer.train(df)
            
        import joblib
        model = joblib.load(model_path)
        features = ['rsi_btc', 'atr_btc', 'macd_btc', 'btc_eth_ratio', 'ratio_sma']
        X = df[features]
        ml_scores = model.predict_proba(X)[:, 1]
        
        # 4. Run Backtest Engine
        engine = BacktestEngine(config_path=self.config_path)
        results = engine.run(df, ml_scores)
        
        # 5. Save Results
        report_path = '/workspace/ai_crypto_strategy/logs/backtest_report.json'
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=4)
            
        print(f"Backtest complete. Results saved to {report_path}")
        return results

    def dry_run(self, symbol='BTCUSDT', timeframe='15m'):
        """
        Run a single inference cycle (Dry Run).
        """
        print(f"Starting dry run for {symbol} {timeframe}...")
        
        # 1. Fetch latest data
        df_btc = self.fetcher.fetch_ohlcv('BTCUSDT', timeframe, limit=100)
        df_eth = self.fetcher.fetch_ohlcv('ETHUSDT', timeframe, limit=100)
        
        # 2. Feature Engineering
        df = self.trainer.feature_engineering(df_btc, df_eth)
        
        # 3. Get ML Score
        score = self.inference.get_ml_score(df)
        
        # 4. Get Position Size
        account_balance = self.executor.get_balance()
        size = self.risk_manager.get_position_size(score, account_balance)
        
        result = {
            "symbol": symbol,
            "ml_score": float(score),
            "position_size_usd": float(size),
            "status": "ready" if score >= 0.82 else "hold"
        }
        print(json.dumps(result, indent=4))
        
        if score >= 0.82:
            self.bot.send_trade_alert("buy", df['close_btc'].iloc[-1], size, f"ML_Score: {score:.4f}")
            self.executor.create_order(symbol, 'buy', size, price=df['close_btc'].iloc[-1])
            
        return result

    def live_loop(self, symbol='BTCUSDT', timeframe='15m'):
        """
        Main live execution loop.
        """
        print(f"🚀 Starting LIVE loop for {symbol} {timeframe}...")
        while True:
            try:
                self.dry_run(symbol, timeframe)
                # Wait for the next minute
                time.sleep(60)
            except KeyboardInterrupt:
                print("Stopping live loop...")
                break
            except Exception as e:
                print(f"Error in live loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else 'backtest'
    
    strategy = StrategyMain(dry_run=(mode != 'live'))
    if mode == 'backtest':
        strategy.run_backtest()
    elif mode == 'dry_run':
        strategy.dry_run()
    elif mode == 'live':
        strategy.live_loop()





