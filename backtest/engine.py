import pandas as pd
import numpy as np
import os
import json
from strategy.metadata import TOTAL_FRICTION, RISK_PER_TRADE, MAX_DAILY_LOSS
from risk.risk_manager import RiskManager

class BacktestEngine:
    def __init__(self, initial_balance=10000, config_path='/workspace/ai_crypto_strategy/config/config.yaml'):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.risk_manager = RiskManager(config_path)
        self.friction = TOTAL_FRICTION
        self.trades = []
        self.daily_pnl_tracker = {}

    def run(self, df, strategy):
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        active_until = None
        symbol = df["symbol"].iloc[0]

        for i in range(len(df)):
            if i >= len(df) - 1: continue
            if self.balance <= 0: break

            entry_time = df['timestamp'].iloc[i]
            date_str = entry_time.strftime('%Y-%m-%d')
            
            if self.daily_pnl_tracker.get(date_str, 0) <= -MAX_DAILY_LOSS:
                continue

            if active_until and entry_time < active_until:
                continue

            res = strategy.get_signal(df.iloc[:i+1], symbol=symbol)
            if isinstance(res, tuple):
                signal, custom_params = res
            else:
                signal, custom_params = res, {}
                
            if not signal: continue

            entry_price = df['close'].iloc[i]
            is_long = (signal == 'LONG')
            
            tp_price = custom_params.get('tp_price')
            sl_price = custom_params.get('sl_price')
            be_trigger_price = custom_params.get('be_trigger_price')
            
            timeout_bars = custom_params.get('timeout', 999999)
            
            exit_price = 0
            exit_time = None
            exit_type = "TIMEOUT"
            is_be_activated = False

            for j in range(i + 1, min(i + 1 + timeout_bars, len(df))):
                current_high = df['high'].iloc[j]
                current_low = df['low'].iloc[j]
                current_close = df['close'].iloc[j]

                # Breakeven Logic
                if be_trigger_price and not is_be_activated:
                    if is_long and current_high >= be_trigger_price:
                        sl_price = entry_price
                        is_be_activated = True
                    elif not is_long and current_low <= be_trigger_price:
                        sl_price = entry_price
                        is_be_activated = True

                if is_long:
                    if current_high >= tp_price:
                        exit_price = tp_price
                        exit_time = df['timestamp'].iloc[j]
                        exit_type = 'TAKE_PROFIT'
                        break
                    if current_low <= sl_price:
                        exit_price = sl_price
                        exit_time = df['timestamp'].iloc[j]
                        exit_type = 'BREAKEVEN' if is_be_activated else 'STOP_LOSS'
                        break
                else:
                    if current_low <= tp_price:
                        exit_price = tp_price
                        exit_time = df['timestamp'].iloc[j]
                        exit_type = 'TAKE_PROFIT'
                        break
                    if current_high >= sl_price:
                        exit_price = sl_price
                        exit_time = df['timestamp'].iloc[j]
                        exit_type = 'BREAKEVEN' if is_be_activated else 'STOP_LOSS'
                        break
            
            if not exit_time:
                exit_idx = min(i + timeout_bars, len(df) - 1)
                exit_price = df['close'].iloc[exit_idx]
                exit_time = df['timestamp'].iloc[exit_idx]
                exit_type = 'TIMEOUT'

            pos_size = self.risk_manager.get_position_size(RISK_PER_TRADE, self.balance, entry_price, sl_price if not is_be_activated else custom_params.get('sl_price'))
            if pos_size <= 0: continue

            raw_pnl = (exit_price - entry_price) * pos_size if is_long else (entry_price - exit_price) * pos_size
            fee = (entry_price + exit_price) * pos_size * self.friction
            net_pnl = raw_pnl - fee

            pnl_pct = net_pnl / self.balance
            self.daily_pnl_tracker[date_str] = self.daily_pnl_tracker.get(date_str, 0) + pnl_pct

            self.balance += net_pnl
            active_until = exit_time
            self.trades.append({
                'symbol': symbol,
                'entry_time': str(entry_time),
                'exit_time': str(exit_time),
                'pnl': net_pnl,
                'return': net_pnl / self.initial_balance,
                'exit_type': exit_type
            })

        return {'all_trades': self.trades}
