




import pandas as pd
import numpy as np
import os
import json
from risk.risk_manager import RiskManager

class BacktestEngine:
    def __init__(self, initial_balance=10000, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.risk_manager = RiskManager(config_path)
        self.friction = self.risk_manager.friction # 0.0009
        self.trades = []

    def run(self, df, ml_scores):
        """
        Vectorized backtest with dynamic sizing.
        df: DataFrame with 'close' and 'timestamp'
        ml_scores: Series of ML_Scores aligned with df
        """
        df = df.copy()
        df['ml_score'] = ml_scores
        
        # Simple strategy: Long if ml_score > 0.82, exit after 4 bars (1 hour)
        # This matches the training target
        
        for i in range(len(df) - 4):
            ml_score = df['ml_score'].iloc[i]
            if ml_score >= 0.82:
                entry_price = df['close_btc'].iloc[i]
                exit_price = df['close_btc'].iloc[i+4]
                
                # Dynamic position sizing
                position_size_usd = self.risk_manager.get_position_size(ml_score, self.balance)
                
                # Apply friction (entry + exit)
                gross_return = (exit_price / entry_price) - 1
                net_return = gross_return - (self.friction * 2)
                
                pnl = position_size_usd * net_return
                self.balance += pnl
                
                self.trades.append({
                    'timestamp': df['timestamp'].iloc[i],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'ml_score': ml_score,
                    'pnl': pnl,
                    'return': net_return,
                    'balance': self.balance
                })

        return self.calculate_metrics()

    def calculate_metrics(self):
        if not self.trades:
            return {"error": "No trades executed"}
            
        trade_df = pd.DataFrame(self.trades)
        total_return = (self.balance / self.initial_balance) - 1
        win_rate = (trade_df['pnl'] > 0).mean()
        
        # Max Drawdown
        trade_df['cum_balance'] = trade_df['balance']
        trade_df['cum_max'] = trade_df['cum_balance'].cummax()
        trade_df['drawdown'] = (trade_df['cum_balance'] - trade_df['cum_max']) / trade_df['cum_max']
        max_drawdown = trade_df['drawdown'].min()
        
        # Sharpe Ratio (assuming 0 risk-free rate for simplicity)
        returns = trade_df['return']
        sharpe_ratio = np.sqrt(252 * 24 * 4) * returns.mean() / returns.std() if returns.std() != 0 else 0
        
        metrics = {
            "total_return": float(total_return),
            "win_rate": float(win_rate),
            "max_drawdown": float(max_drawdown),
            "sharpe_ratio": float(sharpe_ratio),
            "total_trades": len(self.trades),
            "final_balance": float(self.balance),
            "avg_win": float(trade_df[trade_df['pnl'] > 0]['return'].mean()) if any(trade_df['pnl'] > 0) else 0,
            "avg_loss": float(trade_df[trade_df['pnl'] <= 0]['return'].mean()) if any(trade_df['pnl'] <= 0) else 0
        }
        return metrics

if __name__ == "__main__":
    # Example usage
    engine = BacktestEngine()
    # Dummy data for testing
    df = pd.DataFrame({
        'timestamp': pd.date_range(start='2026-01-01', periods=100, freq='15min'),
        'close': np.random.normal(50000, 100, 100)
    })
    ml_scores = np.random.uniform(0.5, 0.95, 100)
    results = engine.run(df, ml_scores)
    print(json.dumps(results, indent=4))




