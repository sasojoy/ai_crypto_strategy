"""
DEV-WINDOW ONLY (< 2026-01-01). ANALYSIS, not a new candidate: answers the
user's question "once a trade starts drawing down after entry, is it
basically doomed to hit the stop?" -- directly relevant given this
research line's own earlier finding (dev_momentum_v4_lock_profit.py) that
64.5% of eventual TP winners first retraced through breakeven before
running to the full target, which is why any early-exit/lock-profit
mechanism tested here has backfired.

For every trade in the classic locked-spec population (same as
dev_momentum_v4_wider_stop.py / dev_momentum_tighter_tp.py: per-symbol
top-tercile, n=1755), walks the SAME 1H price path used for the real
SL/TP simulation and records, MINUTE-BY-MINUTE... no, bar-by-bar on 1H
data (matching this strategy's own resolution), the MAXIMUM ADVERSE
EXCURSION (drawdown in the direction that hurts the position, e.g. price
falling for a long) reached AT ANY POINT before the trade's actual
resolution (SL/TP/TIMEOUT), expressed as a fraction of the SL distance
(so 1.0 = "touched the stop exactly", by definition true for every SL
trade and never true for a TP trade, since hitting the stop IS the SL
outcome).

Reports, split by eventual outcome (TP win vs SL loss):
  - the distribution of max adverse excursion reached along the way
  - specifically: what fraction of eventual TP WINNERS at some point drew
    down to at least 25% / 50% / 75% of the way to their stop before
    turning around and winning anyway
  - the reverse: of trades that drew down to at least X% of the way to
    stop within the first 24 hours after entry, what fraction still went
    on to win?

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
    SL_ATR_MULT, TP_ATR_MULT, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

EARLY_WINDOW_BARS = 24  # "within the first 24 hours after entry" for the early-drawdown check


def simulate_with_path(close, high, low, atr, i, direction):
    entry_price = close[i]
    n = len(close)
    end = min(i + 1 + MAX_HOLD_BARS, n)
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None

    if direction == 'long':
        sl_price = entry_price - SL_ATR_MULT * atr[i]
        tp_price = entry_price + TP_ATR_MULT * atr[i]
    else:
        sl_price = entry_price + SL_ATR_MULT * atr[i]
        tp_price = entry_price - TP_ATR_MULT * atr[i]
    sl_dist = SL_ATR_MULT * atr[i]

    max_adverse_frac = 0.0        # over the WHOLE hold, as fraction of SL distance
    max_adverse_frac_early = 0.0  # restricted to the first EARLY_WINDOW_BARS bars
    reason = 'TIMEOUT'
    exit_idx = end - 1
    for j in range(i + 1, end):
        if direction == 'long':
            adverse = (entry_price - low[j]) / sl_dist
        else:
            adverse = (high[j] - entry_price) / sl_dist
        adverse = max(0.0, adverse)
        max_adverse_frac = max(max_adverse_frac, adverse)
        if j - i <= EARLY_WINDOW_BARS:
            max_adverse_frac_early = max(max_adverse_frac_early, adverse)

        if direction == 'long':
            if low[j] <= sl_price:
                reason, exit_idx = 'SL', j
                break
            if high[j] >= tp_price:
                reason, exit_idx = 'TP', j
                break
        else:
            if high[j] >= sl_price:
                reason, exit_idx = 'SL', j
                break
            if low[j] <= tp_price:
                reason, exit_idx = 'TP', j
                break

    return dict(reason=reason, max_adverse_frac=min(max_adverse_frac, 1.0),
                max_adverse_frac_early=min(max_adverse_frac_early, 1.0),
                bars_held=exit_idx - i)


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


def main():
    print("Building the classic locked-spec population (n should be ~1755)...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}\n")

    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_with_path(close, high, low, atr, row.idx, row.direction)
        if out is None:
            continue
        out['symbol'] = row.symbol
        rows.append(out)
    d = pd.DataFrame(rows)
    d = d[d['reason'] != 'TIMEOUT']  # negligible (~0.5%), excluded to keep the SL-vs-TP question clean
    print(f"Trades analyzed (SL or TP only): {len(d)}\n")

    print(f"{'='*78}\nDistribution of MAX ADVERSE EXCURSION reached at any point before "
          f"resolution\n(as a fraction of the SL distance -- 1.0 = touched the stop)\n{'='*78}")
    for reason, g in d.groupby('reason'):
        q = g['max_adverse_frac'].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        print(f"  {reason} (n={len(g)}): p10={q[0.1]:.2f} p25={q[0.25]:.2f} median={q[0.5]:.2f} "
              f"p75={q[0.75]:.2f} p90={q[0.9]:.2f}")

    print(f"\n{'='*78}\nOf the eventual TP WINNERS, what fraction drew down to at least X% of "
          f"the way to the stop\nAT SOME POINT before eventually winning?\n{'='*78}")
    winners = d[d['reason'] == 'TP']
    for thresh in [0.25, 0.50, 0.75, 0.90]:
        frac = (winners['max_adverse_frac'] >= thresh).mean() * 100
        print(f"  Drew down to >= {thresh*100:.0f}% of the way to stop: {frac:.1f}% of {len(winners)} winners")

    print(f"\n{'='*78}\nOf trades that drew down to at least X% of the way to stop WITHIN THE "
          f"FIRST {EARLY_WINDOW_BARS}h after entry,\nwhat fraction still went on to WIN (hit TP)?\n{'='*78}")
    for thresh in [0.25, 0.50, 0.75, 0.90]:
        sub = d[d['max_adverse_frac_early'] >= thresh]
        if len(sub) == 0:
            continue
        win_rate = (sub['reason'] == 'TP').mean() * 100
        print(f"  Early drawdown >= {thresh*100:.0f}% of stop distance (n={len(sub)}): "
              f"{win_rate:.1f}% still went on to hit TP  (unconditional win rate: "
              f"{(d['reason']=='TP').mean()*100:.1f}%)")

    print(f"\n{'='*78}\nFor comparison: trades that NEVER drew down more than 10% of the way to "
          f"stop at any point\n{'='*78}")
    clean = d[d['max_adverse_frac'] < 0.10]
    print(f"  n={len(clean)} ({len(clean)/len(d)*100:.1f}% of all trades)  win_rate={(clean['reason']=='TP').mean()*100:.1f}%")


if __name__ == "__main__":
    main()
