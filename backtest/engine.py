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
        self.friction = self.risk_manager.friction_rate
        self.trades = []

    def run(self, df, ml_scores, threshold=0.3, fine_df=None):
        df = df.copy()
        df['ml_score'] = ml_scores
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 180.0 Breakout Logic
        df['is_long_entry'] = df['is_long_breakout']
        df['is_short_entry'] = df['is_short_breakout']
        
        # ML Filter
        df['is_liquidity_entry'] = (df['is_long_entry'] | df['is_short_entry']) & (df['ml_score'] >= threshold)
        
        entry_indices = np.where(df['is_liquidity_entry'])[0]
        active_until = None

        for i in entry_indices:
            if i >= len(df) - 1: continue
            if self.balance <= 0: break
            
            entry_time = df['timestamp'].iloc[i]
            if active_until and entry_time < active_until:
                continue

            entry_price = df['close'].iloc[i]
            is_long = df['is_long_entry'].iloc[i]
            atr_val = df['atr'].iloc[i]
            
            # Trailing Stop: 2.0 * ATR
            trailing_dist = 2.0 * atr_val
            # Intended Stop Loss for position sizing
            intended_sl = entry_price - trailing_dist if is_long else entry_price + trailing_dist
            
            exit_price = 0
            exit_time = None
            
            # Simulation loop for trailing stop
            highest_price = entry_price
            lowest_price = entry_price
            
            for j in range(i + 1, len(df)):
                current_high = df['high'].iloc[j]
                current_low = df['low'].iloc[j]
                current_close = df['close'].iloc[j]
                
                if is_long:
                    highest_price = max(highest_price, current_high)
                    stop_price = highest_price - trailing_dist
                    if current_low <= stop_price:
                        exit_price = stop_price
                        exit_time = df['timestamp'].iloc[j]
                        break
                else:
                    lowest_price = min(lowest_price, current_low)
                    stop_price = lowest_price + trailing_dist
                    if current_high >= stop_price:
                        exit_price = stop_price
                        exit_time = df['timestamp'].iloc[j]
                        break
            
            if not exit_time:
                exit_price = df['close'].iloc[-1]
                exit_time = df['timestamp'].iloc[-1]

            # Risk Management & PnL
            # Use intended_sl for position sizing
            pos_size = self.risk_manager.get_position_size(0.5, self.balance, entry_price, intended_sl)
            if pos_size <= 0: continue

            raw_pnl = (exit_price - entry_price) * pos_size if is_long else (entry_price - exit_price) * pos_size
            fee = (entry_price + exit_price) * pos_size * self.friction
            net_pnl = raw_pnl - fee
            
            self.balance += net_pnl
            active_until = exit_time
            
            self.trades.append({
                'symbol': df['symbol'].iloc[0] if 'symbol' in df.columns else 'UNKNOWN',
                'entry_time': str(entry_time),
                'exit_time': str(exit_time),
                'pnl': net_pnl,
                'return': net_pnl / self.initial_balance,
                'exit_type': 'TRAILING_STOP'
            })

        return self.calculate_metrics()

    def calculate_metrics(self):
        if not self.trades:
            return {'total_trades': 0, 'all_trades': []}

        trade_df = pd.DataFrame(self.trades)
        win_rate = (trade_df['pnl'] > 0).mean()
        expectancy = trade_df['return'].mean()
        
        trade_df['cum_balance'] = trade_df['pnl'].cumsum() + self.initial_balance
        balance_series = pd.Series([self.initial_balance] + trade_df['cum_balance'].tolist())
        cum_max = balance_series.cummax()
        drawdowns = (balance_series - cum_max) / cum_max
        max_drawdown = float(drawdowns.min())
        
        wins = trade_df[trade_df['pnl'] > 0]
        losses = trade_df[trade_df['pnl'] <= 0]
        gross_profits = wins['pnl'].sum()
        gross_losses = abs(losses['pnl'].sum())
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else 0.0
        
        metrics = {
            'total_trades': len(self.trades),
            'win_rate': float(win_rate),
            'expectancy': float(expectancy),
            'max_drawdown': max_drawdown,
            'profit_factor': float(profit_factor),
            'exit_type_counts': trade_df['exit_type'].value_counts().to_dict(),
            'all_trades': self.trades
        }
        return metrics
