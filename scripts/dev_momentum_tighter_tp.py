"""
DEV-WINDOW ONLY (< 2026-01-01). Tests the opposite direction from
dev_momentum_v4_wider_stop.py: instead of widening the stop (keeping the
2:1 reward:risk ratio), this NARROWS the reward:risk ratio by shrinking TP
while keeping SL fixed at the locked spec's 2.0xATR, on the user's request
after questioning the ~40% win rate -- "does compressing the reward:risk
ratio make the strategy's overall PF more stable (even if each win is
smaller), since a target that's easier to reach should raise win rate?"

This is NOT dev_momentum_v4_lock_profit.py's already-failed idea (moving
the stop to breakeven mid-trade once some profit is banked) -- that
mechanism was proven catastrophic (PF collapsed to 0.06-0.67) because real
winners on this signal routinely retrace before their real move develops,
and an early "lock it in" trigger fires during that retrace and kills the
winner before it can run. This script's mechanism is different: the TP
level itself is fixed and closer from the moment of entry (not moved
mid-trade based on how the trade is doing), so it doesn't specifically
target "trades currently in the retrace" the way the breakeven-stop did --
but it still shares the same underlying risk this research line has
already found real: a smaller TP will convert some of what would have been
big 4xATR winners into smaller 2-3xATR wins along the way, IF the position
happens to pass through the tighter TP level before its eventual real move
(same retrace-then-run pattern). Whether that trade-off still nets out
positive is exactly what this script checks, honestly, rather than assumed
either way.

Deliberately only 2 candidate TP multiples decided BEFORE running this
script, not a parameter hunt: 3.0 (1.5:1 reward:risk) and 2.0 (1:1, even
money) -- SL fixed at the locked spec's 2.0xATR throughout. If neither
raises win rate without destroying PF, the conclusion is "this lever
doesn't work either," not "try more multiples."

Per this project's established discipline: dev window only (2020-2025),
does NOT touch the 2026+ holdout window. Reuses the SAME locked-spec
building blocks and the SAME high-vol-tercile trigger population
dev_momentum_v4_wider_stop.py used, for direct comparability.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    SYMBOLS, load_1h, compute_atr, compute_rsi, find_triggers,
    BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
DEV_START = pd.Timestamp('2020-01-01')
SL_MULT = 2.0  # fixed throughout -- only TP (reward:risk ratio) varies
# (label, TP_ATR_MULT) scenarios -- SL stays 2.0xATR (the locked spec's own value).
SCENARIOS = [
    ('baseline (2:1, TP=4.0)', 4.0),
    ('tighter (1.5:1, TP=3.0)', 3.0),
    ('tighter (1:1, TP=2.0)', 2.0),
]


def simulate_trade(close, high, low, atr, i, direction, tp_mult):
    entry_price = close[i]
    n = len(close)
    end = min(i + 1 + MAX_HOLD_BARS, n)
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None

    if direction == 'long':
        sl_price = entry_price - SL_MULT * atr[i]
        tp_price = entry_price + tp_mult * atr[i]
    else:
        sl_price = entry_price + SL_MULT * atr[i]
        tp_price = entry_price - tp_mult * atr[i]

    exit_price, reason = None, None
    for j in range(i + 1, end):
        if direction == 'long':
            if low[j] <= sl_price:
                exit_price, reason = sl_price, 'SL'
                break
            if high[j] >= tp_price:
                exit_price, reason = tp_price, 'TP'
                break
        else:
            if high[j] >= sl_price:
                exit_price, reason = sl_price, 'SL'
                break
            if low[j] <= tp_price:
                exit_price, reason = tp_price, 'TP'
                break
    if exit_price is None:
        exit_idx = end - 1
        if exit_idx <= i:
            return None
        exit_price, reason = close[exit_idx], 'TIMEOUT'

    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = SL_MULT * atr[i] / entry_price
    eq_pnl = (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0
    return {'reason': reason, 'equity_pnl_pct': eq_pnl}


def build_candidates():
    raw = []
    frames = {}
    for s in SYMBOLS:
        df = load_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        frames[s] = df
        for i, reversion_direction in find_triggers(df):
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            raw.append({'symbol': s, 'idx': i, 'direction': flip(reversion_direction),
                        'entry_time': df['timestamp'].iloc[i], 'vol_ratio': df['vol_ratio'].iloc[i]})
    cand = pd.DataFrame(raw)
    cand['vol_tercile'] = cand.groupby('symbol')['vol_ratio'].transform(
        lambda x: pd.qcut(x, 3, labels=['low', 'mid', 'high']))
    cand = cand[cand['vol_tercile'] == 'high'].sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def run_scenario(candidates, frames, tp_mult):
    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction, tp_mult)
        if out is None:
            continue
        out['symbol'] = row.symbol
        out['direction'] = row.direction
        out['entry_time'] = row.entry_time
        rows.append(out)
    return pd.DataFrame(rows)


def summarize(df, label, years):
    if df.empty:
        print(f"{label}: 0 trades")
        return
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gross_win = df.loc[df['equity_pnl_pct'] > 0, 'equity_pnl_pct'].sum()
    gross_loss = -df.loc[df['equity_pnl_pct'] <= 0, 'equity_pnl_pct'].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
    total = df['equity_pnl_pct'].sum()
    top3_pct = df.nlargest(3, 'equity_pnl_pct')['equity_pnl_pct'].sum() / total * 100 if total > 0 else float('nan')
    dfq = df.copy()
    dfq['quarter'] = pd.to_datetime(dfq['entry_time']).dt.to_period('Q')
    q_pf = dfq.groupby('quarter')['equity_pnl_pct'].apply(
        lambda x: (x[x > 0].sum() / -x[x <= 0].sum()) if (x <= 0).any() and -x[x <= 0].sum() > 0 else float('inf'))
    q_pf_pass = (q_pf > 1.0).sum()
    n_symbols_positive = (df.groupby('symbol')['equity_pnl_pct'].sum() > 0).sum()
    print(f"{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.1f}%  "
          f"annualized(linear)={total/years:+.1f}%/yr  top3_trade_pct_of_profit={top3_pct:.1f}%  "
          f"quarters_PF>1={q_pf_pass}/{len(q_pf)}  symbols_net_positive={n_symbols_positive}/5")
    print("  exit reasons: " + ", ".join(
        f"{r}={c} ({c/n*100:.1f}%)" for r, c in df['reason'].value_counts().items()))


def main():
    print("Building dev-window (2020-2025) high-vol-tercile momentum-continuation candidates...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}\n")
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    for label, tp_mult in SCENARIOS:
        scenario = run_scenario(candidates, frames, tp_mult)
        summarize(scenario, label, years)
        print()

    print(f"{'='*78}\nDETAIL for tightest candidate (SL/TP=2.0/2.0, 1:1) -- long/short split + by-symbol\n{'='*78}")
    chosen = run_scenario(candidates, frames, 2.0)
    for direction in ['long', 'short']:
        summarize(chosen[chosen['direction'] == direction], f"  {direction.upper()}", years)
    print()
    print("By symbol:")
    print(chosen.groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum', mean='mean').to_string())


if __name__ == "__main__":
    main()
