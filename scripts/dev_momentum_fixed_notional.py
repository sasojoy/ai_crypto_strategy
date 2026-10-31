"""
Portfolio-realistic re-evaluation of the LOCKED RSI(14) momentum-
continuation + volume-tercile spec (dev_momentum_continuation.py /
holdout_momentum_validation.py), addressing the two gaps flagged in
DEPLOYMENT_RISK_ASSESSMENT.md:

1. The original backtests used SEQUENTIAL COMPOUNDING (equity *= 1+pct
   per trade in chronological order), which implicitly assumes one trade
   closes before the next opens. This strategy's trades can overlap (7-
   day max hold, 8-hour cooldown), so sequential compounding overstates
   the return a single account could actually realize.
2. No portfolio-level concurrency cap: multiple correlated symbols can
   all be open (and all hit stop-loss) in the same adverse market move,
   so per-trade 2%-of-account risk alone understates true simultaneous
   drawdown risk.

This script does NOT change the locked spec's trigger/entry/exit rules
(RSI(14) oversold->short / overbought->long, volume top-tercile, SL=2xATR
/TP=4xATR/7-day hold/8-bar cooldown) or re-litigate the holdout pass/fail
verdict already recorded in RESEARCH_FINDINGS.md -- it takes the exact
same trigger population and re-aggregates it two ways:
  A. FIXED-NOTIONAL, UNCAPPED: each trade still risks 2% of a FIXED
     reference capital base (not a compounding balance) -- removes the
     compounding-overlap inflation but still takes every signal.
  B. FIXED-NOTIONAL, CONCURRENCY-CAPPED: same, but a new signal is
     REJECTED (no trade at all) if MAX_CONCURRENT positions are already
     open across the whole 5-symbol universe -- what a real, finite risk
     budget would force.
Run on both the dev window (2020-2025) and the holdout window (2026-01-01
through today) for direct comparison to the numbers already reported.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import SYMBOLS, compute_atr, compute_rsi, find_triggers, SL_ATR_MULT, TP_ATR_MULT, \
    BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
MAX_CONCURRENT_OPTIONS = [3, 5, 8]  # position-cap scenarios to compare

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')


def load_1h_full(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1h_full.csv')
    return pd.read_csv(path, parse_dates=['timestamp']).sort_values('timestamp').reset_index(drop=True)


def trade_outcome_with_exit(close, high, low, timestamps, atr, i, direction):
    """Same mechanics as dev_volume_confirm.trade_outcome, but also
    returns the exit bar's timestamp so overlap/concurrency can be
    tracked."""
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

    exit_price, reason, exit_idx = None, None, None
    for j in range(i + 1, end):
        if direction == 'long':
            if low[j] <= sl_price:
                exit_price, reason, exit_idx = sl_price, 'SL', j; break
            if high[j] >= tp_price:
                exit_price, reason, exit_idx = tp_price, 'TP', j; break
        else:
            if high[j] >= sl_price:
                exit_price, reason, exit_idx = sl_price, 'SL', j; break
            if low[j] <= tp_price:
                exit_price, reason, exit_idx = tp_price, 'TP', j; break
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
    return {'reason': reason, 'equity_pnl_pct': eq_pnl * 100,
            'entry_time': timestamps[i], 'exit_time': timestamps[exit_idx]}


def build_candidates(window_start, window_end):
    """All high-vol-tercile momentum-continuation candidate trades whose
    ENTRY falls in [window_start, window_end). Tercile computed on this
    window's own trigger population, same convention as the locked
    dev/holdout scripts."""
    raw = []
    for s in SYMBOLS:
        df = load_1h_full(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']

        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        timestamps = df['timestamp'].values
        for i, reversion_direction in find_triggers(df):
            ts = df['timestamp'].iloc[i]
            if ts < window_start or ts >= window_end:
                continue
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            continuation_direction = flip(reversion_direction)
            outcome = trade_outcome_with_exit(close, high, low, timestamps, atr, i, continuation_direction)
            if outcome is None:
                continue
            outcome['symbol'] = s
            outcome['direction'] = continuation_direction
            outcome['vol_ratio'] = df['vol_ratio'].iloc[i]
            raw.append(outcome)
    trades = pd.DataFrame(raw)
    if trades.empty:
        return trades
    cutoff = trades['vol_ratio'].quantile(2 / 3)
    return trades[trades['vol_ratio'] >= cutoff].sort_values('entry_time').reset_index(drop=True)


def simulate_concurrency(trades, max_concurrent):
    """Event-driven, chronological pass: accept a signal only if fewer
    than max_concurrent positions are currently open; otherwise reject
    (no trade at all) -- exactly what a finite risk budget forces."""
    open_exits = []  # exit_time of currently-open accepted trades
    accepted, rejected = [], 0
    for row in trades.itertuples():
        open_exits = [t for t in open_exits if t > row.entry_time]
        if len(open_exits) >= max_concurrent:
            rejected += 1
            continue
        open_exits.append(row.exit_time)
        accepted.append(row.equity_pnl_pct)
    return accepted, rejected


def max_observed_concurrency(trades):
    """What concurrency actually looks like with NO cap -- to judge
    whether the cap scenarios below are realistic or overly restrictive."""
    events = []
    for row in trades.itertuples():
        events.append((row.entry_time, 1))
        events.append((row.exit_time, -1))
    events.sort(key=lambda x: (x[0], x[1]))  # exits before entries at same instant
    cur, peak = 0, 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def report(label, trades, years):
    if trades.empty:
        print(f"\n{label}: 0 candidate trades")
        return
    n = len(trades)
    peak_concurrency = max_observed_concurrency(trades)
    compounding_equity = 1.0
    for pct in trades['equity_pnl_pct']:
        compounding_equity *= (1 + pct / 100)
    compounded_return = (compounding_equity - 1) * 100

    print(f"\n{'='*70}\n{label}  (n={n} candidate signals, {years:.2f} years, peak observed concurrency={peak_concurrency})\n{'='*70}")
    print(f"  ORIGINAL METHOD (sequential compounding, no cap): total return {compounded_return:+.2f}%  "
          f"-> annualized-equivalent {((1+compounded_return/100)**(1/years)-1)*100 if years>0 else float('nan'):+.2f}%/yr")

    fixed_uncapped_total = trades['equity_pnl_pct'].sum()
    print(f"  FIXED-NOTIONAL, UNCAPPED (linear sum, same fixed base every trade): "
          f"total {fixed_uncapped_total:+.2f}%  -> annualized (linear) {fixed_uncapped_total/years:+.2f}%/yr" if years > 0 else "")

    for cap in MAX_CONCURRENT_OPTIONS:
        accepted, rejected = simulate_concurrency(trades, cap)
        total = sum(accepted)
        ann = total / years if years > 0 else float('nan')
        print(f"  FIXED-NOTIONAL, CAP={cap} concurrent: accepted={len(accepted)} rejected={rejected}  "
              f"total {total:+.2f}%  -> annualized (linear) {ann:+.2f}%/yr")


def main():
    dev_start, dev_end = pd.Timestamp('2020-01-01'), DEV_CUTOFF
    holdout_start, holdout_end = DEV_CUTOFF, pd.Timestamp.now().normalize() + pd.Timedelta(days=1)

    print("Building dev-window candidates (2020-01-01 to 2026-01-01)...")
    dev_trades = build_candidates(dev_start, dev_end)
    dev_years = (dev_end - dev_start).days / 365.25
    report("DEV WINDOW", dev_trades, dev_years)

    print("\nBuilding holdout-window candidates (2026-01-01 to today)...")
    holdout_trades = build_candidates(holdout_start, holdout_end)
    holdout_years = (pd.Timestamp.now() - holdout_start).days / 365.25
    report("HOLDOUT WINDOW", holdout_trades, holdout_years)

    print(f"\n{'='*70}\nSUMMARY: how much did sequential compounding overstate the return?\n{'='*70}")
    for label, trades, years in [("Dev window", dev_trades, dev_years), ("Holdout window", holdout_trades, holdout_years)]:
        if trades.empty or years <= 0:
            continue
        compounding_equity = 1.0
        for pct in trades['equity_pnl_pct']:
            compounding_equity *= (1 + pct / 100)
        orig_ann = ((compounding_equity) ** (1 / years) - 1) * 100
        cap5_accepted, _ = simulate_concurrency(trades, 5)
        cap5_ann = sum(cap5_accepted) / years
        print(f"  {label}: original compounding {orig_ann:+.2f}%/yr  vs  fixed-notional + cap-5 concurrency {cap5_ann:+.2f}%/yr")


if __name__ == "__main__":
    main()
