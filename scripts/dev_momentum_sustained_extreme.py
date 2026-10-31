"""
DEV-WINDOW ONLY (< 2026-01-01). Tests, as a deliberate a-priori-specified
candidate (not a rerun of the bug), the idea that fell out of v3's
2026-09-19 bug fix by accident: instead of only entering on a FRESH RSI(14)
cross above 70 / below 30 (the locked spec's own definition, enforced by
find_triggers()'s "previous bar was NOT yet past the threshold" check),
allow re-entry into an ALREADY-sustained overbought/oversold state -- i.e.
"as long as RSI stays extreme and volume still confirms, keep adding in
that direction every cooldown period" -- rather than treating it as a
one-shot breakout signal.

This is explicitly NOT a re-test of the buggy code (that mechanism also
conflated this idea with v3's separate real-time anticipatory-entry timing,
and used the entry-mechanism's own touch-price math incidentally instead of
a clean signal definition). Isolated here to ONE variable at a time, per
this research line's standing discipline (see e.g. how the pyramid add-on
was kept isolated from v3, and v4/v5/v6 were never tested combined):
  - SAME classic v1-style "wait for the bar to close" timing (entry price =
    that bar's own close) -- NOT v3's anticipatory intra-hour entry, which
    is a separate, already-tested mechanism.
  - SAME SL=2xATR(14)/TP=4xATR(14)/168-bar hold/2% risk/0.14% friction.
  - SAME momentum-CONTINUATION direction convention (RSI>70 -> long,
    RSI<30 -> short) already established as this research line's locked
    spec, not the mean-reversion flip.
  - SAME per-symbol top-tercile volume filter, computed on THIS candidate's
    own trigger population (a different population than the classic
    fresh-cross one, so its own fresh cutoff, not reused from elsewhere).
  - ONLY the trigger condition changes: instead of "RSI crosses fresh" (previous
    bar NOT yet past 70/30, current bar IS), this fires whenever RSI is
    ALREADY beyond 70/30 on the closed bar, gated only by an 8-BAR COOLDOWN
    per symbol (COOLDOWN_BARS=8, same constant already used everywhere else
    in this research line) -- so it can keep re-firing every 8 hours for as
    long as the extreme (and volume) persists, not just once per breakout.

Compared directly against dev_momentum_continuation.py's existing
fresh-cross-only population on the SAME dev window.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    SYMBOLS, load_1h, compute_atr, compute_rsi, trade_outcome, pooled_stats,
    COOLDOWN_BARS, RSI_OVERSOLD, RSI_OVERBOUGHT,
)
from dev_momentum_continuation import build_trigger_dataset as build_classic_dataset_raw


def find_sustained_triggers(df):
    """Fires whenever RSI is ALREADY beyond 70/30 on the closed bar, gated
    only by an 8-bar per-symbol cooldown from the last trigger (of either
    direction) -- not a fresh-cross requirement."""
    rsi = df['rsi'].values
    n = len(df)
    triggers = []
    last_trigger_idx = -10 ** 9
    for i in range(n):
        if i - last_trigger_idx <= COOLDOWN_BARS:
            continue
        if np.isnan(rsi[i]):
            continue
        if rsi[i] > RSI_OVERBOUGHT:
            triggers.append((i, 'long'))
            last_trigger_idx = i
        elif rsi[i] < RSI_OVERSOLD:
            triggers.append((i, 'short'))
            last_trigger_idx = i
    return triggers


def build_sustained_dataset():
    all_trades = []
    for s in SYMBOLS:
        df = load_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']

        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        triggers = find_sustained_triggers(df)
        raw = []
        for i, direction in triggers:
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            raw.append({'idx': i, 'direction': direction, 'vol_ratio': df['vol_ratio'].iloc[i],
                        'timestamp': df['timestamp'].iloc[i]})
        raw_df = pd.DataFrame(raw)
        n_trig = len(raw_df)
        if n_trig == 0:
            print(f"  {s}: 0 triggers")
            continue
        cutoff = raw_df['vol_ratio'].quantile(2 / 3)
        qualifying = raw_df[raw_df['vol_ratio'] >= cutoff]
        n_qual = 0
        for row in qualifying.itertuples():
            outcome = trade_outcome(close, high, low, atr, row.idx, row.direction)
            if outcome is None:
                continue
            outcome['symbol'] = s
            outcome['direction'] = row.direction
            outcome['vol_ratio'] = row.vol_ratio
            outcome['timestamp'] = row.timestamp
            all_trades.append(outcome)
            n_qual += 1
        print(f"  {s}: {n_trig} sustained-extreme triggers (all cooldown-spaced), "
              f"vol_cutoff={cutoff:.3f}, {n_qual} pass the volume filter")
    return pd.DataFrame(all_trades)


def build_classic_dataset():
    """Raw fresh-cross triggers (dev_momentum_continuation.py) have NO volume
    filter applied by default -- apply the SAME per-symbol top-tercile filter
    (dev_momentum_persymbol_tercile.py's corrected, currently-locked
    methodology) here so the comparison to the sustained-extreme population
    (which is volume-filtered) is apples-to-apples. Also normalizes the
    direction column name (raw uses 'trade_direction') to 'direction'."""
    raw = build_classic_dataset_raw()
    raw = raw.rename(columns={'trade_direction': 'direction'})
    cutoff = raw.groupby('symbol')['vol_ratio'].transform(lambda x: x.quantile(2 / 3))
    return raw[raw['vol_ratio'] >= cutoff].copy()


def quarterly_stability(df):
    d = df.copy()
    d['q'] = pd.to_datetime(d['timestamp']).dt.to_period('Q')
    good = 0
    total = 0
    for q, g in d.groupby('q'):
        total += 1
        st = pooled_stats(g)
        if st and st['pf'] > 1.0:
            good += 1
    return good, total


def concentration(df, top_n=3):
    total = df['equity_pnl_pct'].sum()
    if total <= 0:
        return float('nan')
    top = df.sort_values('equity_pnl_pct', ascending=False)['equity_pnl_pct'].head(top_n).sum()
    return top / total * 100


def main():
    print("Building SUSTAINED-EXTREME trigger dataset (dev window, RSI already >70/<30, 8-bar cooldown)...")
    sustained = build_sustained_dataset()
    print(f"\nTotal sustained-extreme trades: {len(sustained)}")

    print("\nBuilding CLASSIC fresh-cross-only dataset (existing locked spec) for comparison...")
    classic = build_classic_dataset()
    print(f"Total classic trades: {len(classic)}")

    for label, df in [("CLASSIC (fresh cross only, locked spec)", classic),
                       ("SUSTAINED-EXTREME (re-enter while extreme persists)", sustained)]:
        st = pooled_stats(df)
        good_q, total_q = quarterly_stability(df)
        conc = concentration(df)
        print(f"\n{'='*70}\n{label}\n{'='*70}")
        print(f"  n={st['n']}  win_rate={st['win_rate']:.1f}%  PF={st['pf']:.2f}  "
              f"compounded={st['compounded']:+.2f}%")
        print(f"  quarterly PF>1: {good_q}/{total_q}  |  top-3-trade concentration: {conc:.1f}%")
        print("  by symbol:")
        print(df.groupby('symbol')['equity_pnl_pct'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                           total='sum').to_string())
        print("  by direction:")
        print(df.groupby('direction')['equity_pnl_pct'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                              total='sum').to_string())


if __name__ == "__main__":
    main()
