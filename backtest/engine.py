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

    def run(self, df, ml_scores, threshold=0.7, fine_df=None):
        df = df.copy()
        df['ml_score'] = ml_scores
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        if fine_df is not None:
            fine_df = fine_df.copy()
            fine_df['timestamp'] = pd.to_datetime(fine_df['timestamp'])
            fine_df.set_index('timestamp', inplace=True)

        # Vectorized Entry Signal Check
        # 168.0 Logic: Z < -1.5 AND RSI Crosses 30 AND 4H Trend Up
        df['rsi_prev'] = df['rsi'].shift(1)
        df['rsi_cross_30'] = (df['rsi_prev'] < 30) & (df['rsi'] >= 30)
        
        df['is_liquidity_entry'] = (df['z_score_dist'] < -1.5) & (df['rsi_cross_30'] == 1) & (df['trend_up_4h'] == 1) & (df['ml_score'] >= threshold)

        entry_indices = df.index[df['is_liquidity_entry']].tolist()

        for i in entry_indices:
            if i >= len(df) - 1: continue
            if self.balance <= 0: break

            entry_time = df['timestamp'].iloc[i]
            entry_price = df['close'].iloc[i]
            rsi_val = df['rsi'].iloc[i]
            
            # TP: EMA200 (The Mean)
            tp_price = df['ema200'].iloc[i]
            # SL: 0.8 * ATR
            atr_val = df['atr'].iloc[i] if 'atr' in df.columns else entry_price * 0.01
            sl_price = entry_price - 0.8 * atr_val
            
            print(f"Entry: {entry_time} | Price: {entry_price:.2f} | RSI: {rsi_val:.2f} | Reason: Z={df['z_score_dist'].iloc[i]:.2f}, ML={df['ml_score'].iloc[i]:.2f}")
            
            exit_price = 0
            exit_time = None
            exit_type = None

            if fine_df is not None:
                end_time = entry_time + pd.Timedelta(hours=24)
                window = fine_df.loc[entry_time:end_time]
                
                if not window.empty:
                    # Vectorized Exit Checks
                    sl_hits = window[window['low'] <= sl_price]
                    tp_hits = window[window['high'] >= tp_price]
                    
                    # Find first hit
                    sl_idx = sl_hits.index[0] if not sl_hits.empty else None
                    tp_idx = tp_hits.index[0] if not tp_hits.empty else None
                    
                    if sl_idx and (not tp_idx or sl_idx < tp_idx):
                        exit_time = sl_idx
                        exit_price = sl_price
                        exit_type = 'SL'
                    elif tp_idx:
                        exit_time = tp_idx
                        exit_price = tp_price
                        exit_type = 'TP_MEAN'
                    else:
                        # Time Stop
                        exit_time = window.index[-1]
                        exit_price = window['close'].iloc[-1]
                        exit_type = 'TIME_STOP'

            if not exit_type:
                # Fallback to 12h exit if no fine_df or window empty
                exit_idx = min(i + 12, len(df) - 1)
                exit_price = df['close'].iloc[exit_idx]
                exit_time = df['timestamp'].iloc[exit_idx]
                exit_type = 'EXPIRED'

            # Calculate PnL with Friction
            slippage = 0.0005
            fee = 0.0004
            trade_return = (exit_price / entry_price) - 1
            net_return = trade_return - (fee + slippage) * 2
            total_pnl = self.balance * net_return
            self.balance += total_pnl

            duration = (pd.to_datetime(exit_time) - pd.to_datetime(entry_time)).total_seconds() / 3600
            self.trades.append({
                'symbol': df['symbol'].iloc[0] if 'symbol' in df.columns else 'UNKNOWN',
                'entry_time': str(entry_time),
                'exit_time': str(exit_time),
                'duration': duration,
                'pnl': total_pnl,
                'return': net_return,
                'exit_type': exit_type
            })

        return self.calculate_metrics()

    def calculate_metrics(self):
        if not self.trades:
            return {'error': 'No trades executed'}

        trade_df = pd.DataFrame(self.trades)
        win_rate = (trade_df['pnl'] > 0).mean()
        expectancy = trade_df['return'].mean()

        wins = trade_df[trade_df['pnl'] > 0]
        losses = trade_df[trade_df['pnl'] <= 0]

        avg_win = wins['return'].mean() if not wins.empty else 0
        avg_loss = losses['return'].mean() if not losses.empty else 0

        gross_profits = wins['pnl'].sum()
        gross_losses = abs(losses['pnl'].sum())
        profit_factor = gross_profits / gross_losses if gross_losses != 0 else float('inf')

        trade_df['cum_balance'] = trade_df['pnl'].cumsum() + self.initial_balance
        trade_df['cum_max'] = trade_df['cum_balance'].cummax()
        max_drawdown = ((trade_df['cum_balance'] - trade_df['cum_max']) / trade_df['cum_max']).min()

        metrics = {
            'total_trades': len(self.trades),
            'win_rate': float(win_rate),
            'expectancy': float(expectancy),
            'max_drawdown': float(max_drawdown),
            'profit_factor': float(profit_factor),
            'avg_win': float(avg_win),
            'avg_loss': float(avg_loss),
            'total_return': float(trade_df['pnl'].sum() / self.initial_balance),
            'trades': self.trades
        }

        with open('/workspace/ai_crypto_strategy/logs/backtest_report.json', 'w') as f:
            json.dump(metrics, f)

        return metrics
