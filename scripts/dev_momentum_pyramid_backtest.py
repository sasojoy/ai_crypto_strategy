"""
DEV-WINDOW ONLY (< 2026-01-01) backtest of the EXPERIMENTAL trend-
following pyramid add-on built into paper_trading/momentum_monitor_v2.py.
This mechanism (add one more fixed-notional unit once a position's
unrealized move reaches +1x the ORIGINAL entry ATR, at most one add per
position) is NOT part of the locked spec that passed holdout validation
(RESEARCH_FINDINGS.md "第二十三/二十四次測試") and has never been tested
anywhere in this research line -- the user asked to see its backtest
performance before running it forward in paper mode indefinitely.

Per this project's established discipline, this is run ONLY on the dev
window (2020-2025), the same free-to-iterate territory as everything
else in this research -- it deliberately does NOT touch the 2026+
holdout window. The holdout has already been used once for the no-
pyramid version of this exact strategy (passed, but with a thin margin --
see "第二十四次測試"); spending it again on a brand-new, never-discussed
mechanism without a separate explicit conversation with the user would
repeat exactly the "burn the holdout on every new idea" pattern this
project has consistently guarded against.

Methodology note: unlike the live v2 paper monitor (which polls 1-minute
bars), this backtest evaluates SL/TP/pyramid-trigger against 1H bar highs
/lows, consistent with every other backtest in this research line. This
is a coarser approximation than the live version's 1-minute checks, so
the live paper-trading track record and this backtest's numbers are not
expected to match exactly -- flagged here rather than glossed over.

CORRECTION (2026-09-09): build_candidates() used to compute the top-
tercile vol_ratio cutoff POOLED across all 5 symbols -- the same bug the
2026-09-08 code review already fixed in dev_momentum_continuation.py /
calibrate_momentum_threshold.py / the live monitors, but this script was
created for the pyramid experiment and was missed by that pass. The
pooled cutoff let BTC clear the bar far more often than the altcoins
(its vol_ratio runs structurally higher), which is why this script's
original run showed BTC as the sole net-losing symbol (-57.6%) --
matching the very BTC dev/holdout contradiction RESEARCH_FINDINGS.md's
code-review section traces to this exact bug. Fixed to compute the
cutoff separately per symbol, same as everywhere else. Re-run after the
fix: combined +142.96%/yr (was +133.97%/yr), BTC now the smallest net-
positive contributor (+24.2%, was -57.6%) instead of the only loser.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from dev_volume_confirm import (
    SYMBOLS, compute_atr, compute_rsi, find_triggers,
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
DEV_START = pd.Timestamp('2020-01-01')
MAX_CONCURRENT_GROUPS = 5
PYRAMID_TRIGGER_ATR = 1.0
MAX_ADDS_PER_POSITION = 1

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')


def load_1h_dev(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1h_extended.csv')
    df = pd.read_csv(path, parse_dates=['timestamp'])
    return df[df['timestamp'] < DEV_CUTOFF].sort_values('timestamp').reset_index(drop=True)


def leg_pnl_pct(direction, entry_price, exit_price, sl_price):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0


def simulate_group(df, entry_idx, direction):
    """Bar-by-bar (1H) simulation of one signal's full lifecycle,
    including up to one pyramid add. Returns (original_leg, add_leg_or_None,
    group_exit_idx)."""
    close, high, low, timestamps = df['close'].values, df['high'].values, df['low'].values, df['timestamp'].values
    atr_series = compute_atr(df).values
    n = len(df)
    atr = atr_series[entry_idx]
    if np.isnan(atr) or atr <= 0:
        return None

    entry_price = close[entry_idx]
    if direction == 'long':
        sl_price = entry_price - SL_ATR_MULT * atr
        tp_price = entry_price + TP_ATR_MULT * atr
    else:
        sl_price = entry_price + SL_ATR_MULT * atr
        tp_price = entry_price - TP_ATR_MULT * atr

    end = min(entry_idx + 1 + MAX_HOLD_BARS, n)
    if end <= entry_idx + 1:
        return None
    max_hold_exit_time = pd.Timestamp(timestamps[entry_idx]) + pd.Timedelta(hours=MAX_HOLD_BARS)

    original = {'entry_time': timestamps[entry_idx], 'entry_price': entry_price, 'sl_price': sl_price,
                'tp_price': tp_price, 'closed': False}
    add = None
    group_exit_idx = end - 1

    for j in range(entry_idx + 1, end):
        ts = pd.Timestamp(timestamps[j])

        if not original['closed']:
            hit = None
            if direction == 'long':
                if low[j] <= sl_price: hit = (sl_price, 'SL')
                elif high[j] >= tp_price: hit = (tp_price, 'TP')
            else:
                if high[j] >= sl_price: hit = (sl_price, 'SL')
                elif low[j] <= tp_price: hit = (tp_price, 'TP')
            if hit is None and ts >= max_hold_exit_time:
                hit = (close[j], 'TIMEOUT')
            if hit:
                exit_price, reason = hit
                original.update(closed=True, exit_price=exit_price, exit_idx=j, reason=reason,
                                equity_pnl_pct=leg_pnl_pct(direction, entry_price, exit_price, sl_price))

        if add is not None and not add['closed']:
            hit = None
            if direction == 'long':
                if low[j] <= add['sl_price']: hit = (add['sl_price'], 'SL')
                elif high[j] >= add['tp_price']: hit = (add['tp_price'], 'TP')
            else:
                if high[j] >= add['sl_price']: hit = (add['sl_price'], 'SL')
                elif low[j] <= add['tp_price']: hit = (add['tp_price'], 'TP')
            if hit is None and ts >= max_hold_exit_time:
                hit = (close[j], 'TIMEOUT')
            if hit:
                exit_price, reason = hit
                add.update(closed=True, exit_price=exit_price, exit_idx=j, reason=reason,
                           equity_pnl_pct=leg_pnl_pct(direction, add['entry_price'], exit_price, add['sl_price']))

        if not original['closed'] and add is None:
            favorable_move = (high[j] - entry_price) if direction == 'long' else (entry_price - low[j])
            if favorable_move >= PYRAMID_TRIGGER_ATR * atr:
                add_price = close[j]
                if direction == 'long':
                    add_sl, add_tp = add_price - SL_ATR_MULT * atr, add_price + TP_ATR_MULT * atr
                else:
                    add_sl, add_tp = add_price + SL_ATR_MULT * atr, add_price - TP_ATR_MULT * atr
                add = {'entry_time': ts, 'entry_price': add_price, 'sl_price': add_sl, 'tp_price': add_tp, 'closed': False}

        if original['closed'] and (add is None or add['closed']):
            group_exit_idx = j
            break

    if not original['closed']:
        original.update(closed=True, exit_price=close[end - 1], exit_idx=end - 1, reason='TIMEOUT',
                         equity_pnl_pct=leg_pnl_pct(direction, entry_price, close[end - 1], sl_price))
    if add is not None and not add['closed']:
        add.update(closed=True, exit_price=close[end - 1], exit_idx=end - 1, reason='TIMEOUT',
                   equity_pnl_pct=leg_pnl_pct(direction, add['entry_price'], close[end - 1], add['sl_price']))

    return original, add, group_exit_idx


def build_candidates():
    raw = []
    frames = {}
    for s in SYMBOLS:
        df = load_1h_dev(s)
        df['rsi'] = compute_rsi(df['close'])
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        frames[s] = df
        for i, reversion_direction in find_triggers(df):
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            raw.append({'symbol': s, 'idx': i, 'direction': flip(reversion_direction),
                        'entry_time': df['timestamp'].iloc[i], 'vol_ratio': df['vol_ratio'].iloc[i]})
    cand = pd.DataFrame(raw)
    # Per-symbol top-tercile cutoff, not pooled across all 5 -- pooled lets BTC's
    # structurally-higher vol_ratio distribution clear the bar more often than the
    # altcoins (see CORRECTION note above).
    cutoffs = cand.groupby('symbol')['vol_ratio'].quantile(2 / 3)
    cand['cutoff'] = cand['symbol'].map(cutoffs)
    cand = cand[cand['vol_ratio'] >= cand['cutoff']].drop(columns='cutoff').sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def main():
    print("Building dev-window (2020-2025) high-vol-tercile momentum-continuation candidates...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}")

    open_group_exits = []  # (exit_time) of currently accepted, still-open groups
    all_originals, all_adds = [], []
    n_accepted, n_rejected, n_with_add = 0, 0, 0

    for row in candidates.itertuples():
        entry_time = row.entry_time
        open_group_exits = [t for t in open_group_exits if t > entry_time]
        if len(open_group_exits) >= MAX_CONCURRENT_GROUPS:
            n_rejected += 1
            continue

        df = frames[row.symbol]
        result = simulate_group(df, row.idx, row.direction)
        if result is None:
            continue
        original, add, group_exit_idx = result
        n_accepted += 1
        group_exit_time = df['timestamp'].iloc[group_exit_idx]
        open_group_exits.append(group_exit_time)

        original.update(symbol=row.symbol, direction=row.direction)
        all_originals.append(original)
        if add is not None:
            n_with_add += 1
            add.update(symbol=row.symbol, direction=row.direction)
            all_adds.append(add)

    print(f"Accepted groups: {n_accepted}  Rejected (concurrency cap): {n_rejected}  "
          f"Groups that got a pyramid add: {n_with_add} ({n_with_add/n_accepted*100:.1f}%)")

    years = (DEV_CUTOFF - DEV_START).days / 365.25
    orig_df = pd.DataFrame(all_originals)
    add_df = pd.DataFrame(all_adds)
    combined = pd.concat([orig_df, add_df], ignore_index=True) if not add_df.empty else orig_df

    def summarize(df, label):
        if df.empty:
            print(f"\n{label}: 0 legs")
            return
        n = len(df)
        wr = (df['equity_pnl_pct'] > 0).mean() * 100
        gross_win = df[df['equity_pnl_pct'] > 0]['equity_pnl_pct'].sum()
        gross_loss = -df[df['equity_pnl_pct'] <= 0]['equity_pnl_pct'].sum()
        pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
        total = df['equity_pnl_pct'].sum()
        print(f"\n{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.2f}%  "
              f"annualized(linear)={total/years:+.2f}%/yr")

    print(f"\n{'='*70}\nRESULTS -- dev window ({years:.2f} years), fixed-notional sizing, cap={MAX_CONCURRENT_GROUPS} concurrent groups\n{'='*70}")
    summarize(orig_df, "ORIGINAL LEGS ONLY (equivalent to no-pyramid baseline)")
    summarize(add_df, "PYRAMID-ADD LEGS ONLY")
    summarize(combined, "COMBINED (original + add) -- this is the actual v2 mechanism's total")

    print(f"\n{'='*70}\nBy year (combined):\n{'='*70}")
    combined['year'] = pd.to_datetime(combined['entry_time']).dt.year
    print(combined.groupby('year')['equity_pnl_pct'].agg(['count', 'sum', 'mean']).to_string())

    print(f"\n{'='*70}\nBy symbol (combined):\n{'='*70}")
    print(combined.groupby('symbol')['equity_pnl_pct'].agg(['count', 'sum', 'mean']).to_string())

    print(f"\nFor comparison, the no-pyramid baseline (scripts/dev_momentum_fixed_notional.py, cap=5) "
          f"scored +73.98%/yr linear over the same dev window.")


if __name__ == "__main__":
    main()
