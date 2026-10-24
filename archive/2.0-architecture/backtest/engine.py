import pandas as pd
import numpy as np
import os
import json
from strategy.metadata import TOTAL_FRICTION, MAX_DAILY_LOSS, BASE_RISK_PER_TRADE, SCALING_OUT_RATIO
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
        symbol = df['symbol'].iloc[0]

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
            ts_atr_dist = custom_params.get('ts_atr_dist')
            atr_val = custom_params.get('atr_val', 0)
            confidence = custom_params.get('confidence')
            
            # 計算部位 (Units) - 提前至此以供 Scaling Out 使用
            risk_ratio = custom_params.get('risk_ratio', BASE_RISK_PER_TRADE)
            if confidence is not None:
                pos_size = self.risk_manager.calculate_alpha_size(self.balance, confidence, entry_price, sl_price)
            else:
                pos_size = self.risk_manager.get_position_size(risk_ratio, self.balance, entry_price, sl_price)
            
            if pos_size <= 0: continue
            
            initial_pos_size = pos_size # 紀錄初始部位
            timeout_bars = custom_params.get('timeout', 999999)
            
            exit_price = 0
            exit_time = None
            exit_type = 'TIMEOUT'
            is_be_activated = False
            accumulated_pnl = 0
            accumulated_fee = 0
            highest_price = entry_price if is_long else 999999999
            lowest_price = entry_price if not is_long else 0

            for j in range(i + 1, min(i + 1 + timeout_bars, len(df))):
                current_high = df['high'].iloc[j]
                current_low = df['low'].iloc[j]
                current_close = df['close'].iloc[j]

                # Update highest/lowest for Trailing Stop
                if is_long:
                    highest_price = max(highest_price, current_high)
                else:
                    lowest_price = min(lowest_price, current_low)

                # Breakeven & Scaling Out Logic
                if be_trigger_price and not is_be_activated:
                    if (is_long and current_high >= be_trigger_price) or (not is_long and current_low <= be_trigger_price):
                        # 1. 執行分批出場 (Scaling Out)
                        scale_out_size = pos_size * SCALING_OUT_RATIO
                        scale_out_pnl = (be_trigger_price - entry_price) * scale_out_size if is_long else (entry_price - be_trigger_price) * scale_out_size
                        scale_out_fee = (entry_price + be_trigger_price) * scale_out_size * self.friction
                        
                        self.balance += (scale_out_pnl - scale_out_fee)
                        accumulated_pnl += scale_out_pnl
                        accumulated_fee += scale_out_fee
                        
                        # 2. 更新剩餘部位與止損
                        pos_size -= scale_out_size
                        sl_price = entry_price
                        is_be_activated = True

                # Trailing Stop Logic
                if ts_atr_dist and atr_val > 0:
                    if is_long:
                        trailing_sl = highest_price - (ts_atr_dist * atr_val)
                        if trailing_sl > sl_price:
                            sl_price = trailing_sl
                    else:
                        trailing_sl = lowest_price + (ts_atr_dist * atr_val)
                        if trailing_sl < sl_price:
                            sl_price = trailing_sl

                if is_long:
                    if current_high >= tp_price:
                        exit_price = tp_price
                        exit_time = df['timestamp'].iloc[j]
                        exit_type = 'TAKE_PROFIT'
                        break
                    if current_low <= sl_price:
                        exit_price = sl_price
                        exit_time = df['timestamp'].iloc[j]
                        exit_type = 'TRAILING_STOP' if (is_be_activated or (ts_atr_dist and highest_price > entry_price + atr_val)) else 'STOP_LOSS'
                        if is_be_activated and exit_price == entry_price:
                            exit_type = 'BREAKEVEN'
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
                        exit_type = 'TRAILING_STOP' if (is_be_activated or (ts_atr_dist and lowest_price < entry_price - atr_val)) else 'STOP_LOSS'
                        if is_be_activated and exit_price == entry_price:
                            exit_type = 'BREAKEVEN'
                        break
            
            if not exit_time:
                exit_idx = min(i + timeout_bars, len(df) - 1)
                exit_price = df['close'].iloc[exit_idx]
                exit_time = df['timestamp'].iloc[exit_idx]
                exit_type = 'TIMEOUT'

            # PnL 計算 (Units * Price Difference) + 累計分批出場損益
            final_raw_pnl = (exit_price - entry_price) * pos_size if is_long else (entry_price - exit_price) * pos_size
            final_fee = (entry_price + exit_price) * pos_size * self.friction
            
            net_pnl = (final_raw_pnl - final_fee) + (accumulated_pnl - accumulated_fee)

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
