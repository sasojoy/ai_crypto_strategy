import pandas as pd
import numpy as np
import argparse
import os
import json
from strategy.metadata import *
from data.fetcher import BinanceFetcher
from models.trainer import ModelTrainer
from backtest.engine import BacktestEngine

class GoldilocksDispatcher:
    def __init__(self, z_score_threshold=1.2, entropy_threshold=0.7, rsi_slope_min=5, be_trigger=2.0):
        self.name = "GOLDILOCKS"
        self.z_score_threshold = z_score_threshold
        self.entropy_threshold = entropy_threshold
        self.rsi_slope_min = rsi_slope_min
        self.be_trigger = be_trigger
        self.last_trade_time = {}

    def calculate_entropy(self, series):
        if series.empty: return 1.0
        prob = series.value_counts(normalize=True)
        return -1 * (prob * np.log2(prob + 1e-9)).sum()

    def get_signal(self, df_15m, symbol="UNKNOWN", df_1h=None):
        if df_1h is None or len(df_1h) < 168 or len(df_15m) < 100:
            return None, {}

        current_time = df_15m['timestamp'].iloc[-1]
        if symbol in self.last_trade_time:
            hours_since = (current_time - self.last_trade_time[symbol]).total_seconds() / 3600
            if hours_since < 8: return None, {}

        latest_1h = df_1h.iloc[-1]
        latest_15m = df_15m.iloc[-1]
        prev_15m = df_15m.iloc[-2]

        rolling_mean = df_1h['adx'].rolling(168).mean()
        rolling_std = df_1h['adx'].rolling(168).std()
        adx_z = (latest_1h['adx'] - rolling_mean.iloc[-1]) / (rolling_std.iloc[-1] + 1e-9)
        entropy_1h = self.calculate_entropy(np.sign(df_1h['close'].diff()).tail(24))

        if adx_z > self.z_score_threshold and entropy_1h < self.entropy_threshold:
            ema_200_val = latest_1h.get('ema_200', latest_1h.get('ema_200_1h', latest_1h['close']))
            rsi_slope = latest_15m['rsi'] - prev_15m['rsi']
            current_atr = latest_15m.get('atr', latest_15m['close'] * 0.01)

            if latest_1h['close'] > ema_200_val and rsi_slope > self.rsi_slope_min:
                self.last_trade_time[symbol] = current_time
                return 'LONG', {
                    'tp_price': latest_15m['close'] + (current_atr * 4.0),
                    'sl_price': latest_15m['close'] - (current_atr * 2.0),
                    'be_trigger_price': latest_15m['close'] + (current_atr * self.be_trigger)
                }
            elif latest_1h['close'] < ema_200_val and rsi_slope < -self.rsi_slope_min:
                self.last_trade_time[symbol] = current_time
                return 'SHORT', {
                    'tp_price': latest_15m['close'] - (current_atr * 4.0),
                    'sl_price': latest_15m['close'] + (current_atr * 2.0),
                    'be_trigger_price': latest_15m['close'] - (current_atr * self.be_trigger)
                }
        return None, {}

class StrategyMain:
    def __init__(self):
        self.fetcher = BinanceFetcher()
        self.trainer = ModelTrainer()

    def run_backtest(self, symbols, days, dispatcher=None):
        if dispatcher is None: dispatcher = GoldilocksDispatcher()
        all_trades = []
        for symbol in symbols:
            df_15m_raw = self.fetcher.fetch_ohlcv(symbol, "15m", limit=days * 96 + 200)
            df_1h_raw = self.fetcher.fetch_ohlcv(symbol, "1h", limit=days * 24 + 200)
            if df_15m_raw.empty or df_1h_raw.empty: continue
            df_15m = self.trainer.feature_engineering(df_15m_raw)
            df_1h = self.trainer.feature_engineering(df_1h_raw)
            df_15m['symbol'] = symbol
            df_15m['timestamp'] = pd.to_datetime(df_15m['timestamp'])
            df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'])
            engine = BacktestEngine()
            class DualTFWrapper:
                def __init__(self, d, h): self.d, self.h = d, h
                def get_signal(self, s, symbol="UNKNOWN"):
                    ts = s['timestamp'].iloc[-1]
                    h_slice = self.h[self.h['timestamp'] <= ts]
                    return self.d.get_signal(s, symbol, df_1h=h_slice)
            results = engine.run(df_15m, DualTFWrapper(dispatcher, df_1h))
            all_trades.extend(results.get('all_trades', []))
        return all_trades

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='backtest')
    parser.add_argument('--symbols', type=str, default='BTCUSDT,ETHUSDT,SOLUSDT')
    parser.add_argument('--days', type=int, default=90)
    args = parser.parse_args()
    if args.mode == 'backtest':
        StrategyMain().run_backtest(args.symbols.split(','), args.days)
