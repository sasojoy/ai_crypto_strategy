"""
DEVELOPMENT-WINDOW ONLY (< 2026-01-01). Tests the user's idea: "when some
indicator/model trigger fires, use volume to confirm whether it will go up
or down, and separately, use volume to gauge how far a move is likely to
go." A fresh, standalone technical trigger unrelated to any previously
holdout-burned candidate (EMA20 bounce, 4H MTF model) -- picked a priori,
before looking at any result, per the project's discipline against
choosing setups after seeing what "worked": classic RSI(14) oversold
(<30, long/mean-reversion candidate) and overbought (>70,
short/mean-reversion candidate) crosses on 1H bars.

Two separate hypotheses tested on the SAME trigger set:
  H1 (direction confirmation): does the volume level AT the trigger
     (current-bar volume / trailing 20-bar average) predict whether the
     mean-reversion bet (long on oversold, short on overbought) wins or
     loses? Bucketed into terciles by volume ratio, computed on the
     trigger population itself (not cherry-picked thresholds).
  H2 (magnitude, not direction): does the volume ratio at the trigger
     predict how BIG the subsequent move is (max absolute excursion in
     ATR units over the next MAX_HOLD_BARS), regardless of which way it
     goes? This is a genuinely different question from every earlier
     test in this research line -- all 21 prior tests asked "which
     direction", this asks "how far", where volume has a more standard
     theoretical link (participation/conviction -> volatility, not
     necessarily -> direction).

Same trade-outcome mechanics as every earlier 1H test: SL=2xATR(14),
TP=4xATR(14), 7-day max hold (168 1H bars), 0.14% round-trip friction,
2% risk/trade, 8-bar cooldown between triggers per symbol.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']
DEV_CUTOFF = pd.Timestamp('2026-01-01')

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
VOL_LOOKBACK = 20

SL_ATR_MULT = 2.0
TP_ATR_MULT = 4.0
BASE_RISK_PER_TRADE = 0.02
ROUND_TRIP_FRICTION = 0.0014
MAX_HOLD_BARS = 168     # 7 days on 1H bars, same as every earlier 1H test
COOLDOWN_BARS = 8

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')


def load_1h(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1h_extended.csv')
    df = pd.read_csv(path, parse_dates=['timestamp'])
    return df[df['timestamp'] < DEV_CUTOFF].sort_values('timestamp').reset_index(drop=True)


def compute_atr(df, length=14):
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(length).mean()


def compute_rsi(close, period=RSI_PERIOD):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50)


def find_triggers(df):
    """RSI(14) cross-under-30 (oversold -> long candidate) and
    cross-over-70 (overbought -> short candidate), with an 8-bar cooldown
    per symbol so overlapping triggers on the same move aren't double-
    counted."""
    rsi = df['rsi'].values
    n = len(df)
    triggers = []
    last_trigger_idx = -10**9
    for i in range(1, n):
        if i - last_trigger_idx <= COOLDOWN_BARS:
            continue
        if np.isnan(rsi[i - 1]) or np.isnan(rsi[i]):
            continue
        if rsi[i - 1] >= RSI_OVERSOLD and rsi[i] < RSI_OVERSOLD:
            triggers.append((i, 'long'))
            last_trigger_idx = i
        elif rsi[i - 1] <= RSI_OVERBOUGHT and rsi[i] > RSI_OVERBOUGHT:
            triggers.append((i, 'short'))
            last_trigger_idx = i
    return triggers


def trade_outcome(close, high, low, atr, i, direction):
    if np.isnan(atr[i]) or atr[i] <= 0:
        return None
    entry_price = close[i]
    n = len(close)
    end = min(i + 1 + MAX_HOLD_BARS, n)
    if end <= i + 1:
        return None

    if direction == 'long':
        sl_price = entry_price - SL_ATR_MULT * atr[i]
        tp_price = entry_price + TP_ATR_MULT * atr[i]
    else:
        sl_price = entry_price + SL_ATR_MULT * atr[i]
        tp_price = entry_price - TP_ATR_MULT * atr[i]

    exit_price, reason = None, None
    max_up_atr, max_down_atr = 0.0, 0.0
    for j in range(i + 1, end):
        max_up_atr = max(max_up_atr, (high[j] - entry_price) / atr[i])
        max_down_atr = max(max_down_atr, (entry_price - low[j]) / atr[i])
        if direction == 'long':
            if low[j] <= sl_price:
                exit_price, reason = sl_price, 'SL'; break
            if high[j] >= tp_price:
                exit_price, reason = tp_price, 'TP'; break
        else:
            if high[j] >= sl_price:
                exit_price, reason = sl_price, 'SL'; break
            if low[j] <= tp_price:
                exit_price, reason = tp_price, 'TP'; break
    if exit_price is None:
        exit_idx = end - 1
        if exit_idx <= i:
            return None
        exit_price, reason = close[exit_idx], 'TIMEOUT'

    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    eq_pnl = (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE if sl_dist_pct > 0 else 0.0
    magnitude_atr = max(max_up_atr, max_down_atr)  # biggest excursion either way, ATR-normalized
    return {'reason': reason, 'raw_pnl_pct': pnl * 100, 'equity_pnl_pct': eq_pnl * 100, 'magnitude_atr': magnitude_atr}


def build_trigger_dataset():
    all_trades = []
    for s in SYMBOLS:
        df = load_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(VOL_LOOKBACK).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']

        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        triggers = find_triggers(df)
        n_trig = 0
        for i, direction in triggers:
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            outcome = trade_outcome(close, high, low, atr, i, direction)
            if outcome is None:
                continue
            outcome['symbol'] = s
            outcome['direction'] = direction
            outcome['vol_ratio'] = df['vol_ratio'].iloc[i]
            outcome['timestamp'] = df['timestamp'].iloc[i]
            all_trades.append(outcome)
            n_trig += 1
        print(f"  {s}: {n_trig} triggers (RSI oversold/overbought crosses, 8-bar cooldown)")
    return pd.DataFrame(all_trades)


def pooled_stats(df):
    if df.empty:
        return None
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gross_win = df[df['equity_pnl_pct'] > 0]['equity_pnl_pct'].sum()
    gross_loss = -df[df['equity_pnl_pct'] <= 0]['equity_pnl_pct'].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
    equity = 1.0
    for pct in df.sort_values('timestamp')['equity_pnl_pct']:
        equity *= (1 + pct / 100)
    return {'n': n, 'win_rate': wr, 'pf': pf, 'compounded': (equity - 1) * 100}


def random_benchmark_for_subset(full_pool, subset_n, n_seeds=500):
    """Random draws of subset_n trades from the full (unconditional)
    trigger pool -- same trigger mechanics, no volume filter -- to judge
    whether a volume-selected subgroup beats picking that many triggers
    at random."""
    if len(full_pool) < subset_n:
        return None
    results = []
    for seed in range(n_seeds):
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(full_pool), size=subset_n, replace=False)
        st = pooled_stats(full_pool.iloc[idx])
        if st:
            results.append(st)
    return results


def main():
    print("Building RSI(14) oversold/overbought trigger dataset (1H bars, dev window)...")
    trades = build_trigger_dataset()
    print(f"\nTotal triggers with valid outcome + volume data: {len(trades)}")
    if trades.empty:
        return

    print(f"\n{'='*60}\nBASELINE: unconditional RSI mean-reversion (no volume filter)\n{'='*60}")
    for direction in ['long', 'short']:
        sub = trades[trades['direction'] == direction]
        st = pooled_stats(sub)
        if st:
            print(f"  {direction.upper()}: n={st['n']} win_rate={st['win_rate']:.1f}% PF={st['pf']:.2f} compounded={st['compounded']:+.2f}%")
    st_all = pooled_stats(trades)
    print(f"  COMBINED: n={st_all['n']} win_rate={st_all['win_rate']:.1f}% PF={st_all['pf']:.2f} compounded={st_all['compounded']:+.2f}%")

    print(f"\n{'='*60}\nH1: does volume level at the trigger predict WIN/LOSS?\n{'='*60}")
    trades['vol_tercile'] = pd.qcut(trades['vol_ratio'], 3, labels=['low', 'mid', 'high'])
    for direction in ['long', 'short', 'both']:
        sub = trades if direction == 'both' else trades[trades['direction'] == direction]
        print(f"\n  -- {direction.upper()} --")
        for tercile in ['low', 'mid', 'high']:
            tsub = sub[sub['vol_tercile'] == tercile]
            st = pooled_stats(tsub)
            if st:
                print(f"    vol={tercile:4s}: n={st['n']:4d} win_rate={st['win_rate']:.1f}% PF={st['pf']:.2f} compounded={st['compounded']:+.2f}%")
    rho, pval = spearmanr(trades['vol_ratio'], trades['equity_pnl_pct'])
    print(f"\n  Spearman corr(vol_ratio, trade P&L), all triggers pooled: rho={rho:.3f} p={pval:.3f}")

    print(f"\n{'='*60}\nH2: does volume level at the trigger predict MOVE SIZE (magnitude_atr)?\n{'='*60}")
    for tercile in ['low', 'mid', 'high']:
        tsub = trades[trades['vol_tercile'] == tercile]
        print(f"  vol={tercile:4s}: n={len(tsub):4d} mean magnitude={tsub['magnitude_atr'].mean():.2f}x ATR  median={tsub['magnitude_atr'].median():.2f}x ATR")
    rho2, pval2 = spearmanr(trades['vol_ratio'], trades['magnitude_atr'])
    print(f"\n  Spearman corr(vol_ratio, magnitude_atr): rho={rho2:.3f} p={pval2:.3f}")

    print(f"\n{'='*60}\nRandom-entry benchmark for the HIGH-volume subgroup (the practical question:\n"
          f"if you only take volume-confirmed triggers, do you beat picking that many at random?)\n{'='*60}")
    high_sub = trades[trades['vol_tercile'] == 'high']
    st_high = pooled_stats(high_sub)
    if st_high:
        mc = random_benchmark_for_subset(trades, st_high['n'])
        if mc:
            mc_c = np.array([r['compounded'] for r in mc])
            mc_p = np.array([r['pf'] for r in mc])
            mc_w = np.array([r['win_rate'] for r in mc])
            pct_c = (mc_c < st_high['compounded']).mean() * 100
            pct_p = (mc_p < st_high['pf']).mean() * 100
            pct_w = (mc_w < st_high['win_rate']).mean() * 100
            print(f"  High-vol subgroup: n={st_high['n']} win_rate={st_high['win_rate']:.1f}% PF={st_high['pf']:.2f} compounded={st_high['compounded']:+.2f}%")
            print(f"  vs {len(mc)} random draws of the same size from the full trigger pool:")
            print(f"    Compounded beats {pct_c:.1f}% of draws | PF beats {pct_p:.1f}% | Win rate beats {pct_w:.1f}%")


if __name__ == "__main__":
    main()
