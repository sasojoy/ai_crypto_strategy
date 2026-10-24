"""
DEVELOPMENT-WINDOW ONLY (< 2026-01-01). Control-group robustness check for
dev_momentum_continuation.py's finding (RSI(14) extreme + high volume ->
momentum-continuation bet, high-vol tercile: n=1754, win_rate=40.4%,
PF=1.20, beat 100% of matched random draws, positive in every year
2020-2025, top-3-trade concentration only 0.4%).

Same discipline as the earlier Fibonacci-ratio control test (test #8 in
RESEARCH_FINDINGS.md): if 30/70 and "top volume tercile" are not special,
a genuine effect should survive swapping in nearby, arbitrarily-chosen
RSI thresholds and volume cutoffs. If the effect only appears at exactly
30/70 + top-third, that is the same red flag that sank the raw Fibonacci
0.618 level.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import SYMBOLS, load_1h, compute_atr, compute_rsi, trade_outcome, pooled_stats

COOLDOWN_BARS = 8
RSI_PAIRS = [(20, 80), (25, 75), (30, 70), (35, 65), (40, 60)]
VOL_TOP_PCTS = [0.50, 0.33, 0.25, 0.20]


def prep_symbol_data():
    data = {}
    for s in SYMBOLS:
        df = load_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        data[s] = df
    return data


def find_triggers_at(df, oversold_th, overbought_th):
    rsi = df['rsi'].values
    n = len(df)
    triggers = []
    last_idx = -10**9
    for i in range(1, n):
        if i - last_idx <= COOLDOWN_BARS:
            continue
        if np.isnan(rsi[i - 1]) or np.isnan(rsi[i]):
            continue
        if rsi[i - 1] >= oversold_th and rsi[i] < oversold_th:
            triggers.append((i, 'oversold'))
            last_idx = i
        elif rsi[i - 1] <= overbought_th and rsi[i] > overbought_th:
            triggers.append((i, 'overbought'))
            last_idx = i
    return triggers


def flip(signal):
    return 'short' if signal == 'oversold' else 'long'


def build_for_thresholds(data, oversold_th, overbought_th):
    rows = []
    for s, df in data.items():
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        for i, signal in find_triggers_at(df, oversold_th, overbought_th):
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            outcome = trade_outcome(close, high, low, atr, i, flip(signal))
            if outcome is None:
                continue
            outcome['vol_ratio'] = df['vol_ratio'].iloc[i]
            outcome['timestamp'] = df['timestamp'].iloc[i]
            rows.append(outcome)
    return pd.DataFrame(rows)


def main():
    print("Preparing RSI/ATR/volume-ratio for all symbols once...")
    data = prep_symbol_data()

    print(f"\n{'='*80}\nCONTROL GRID: RSI threshold pair x volume-cutoff percentile\n"
          f"(momentum-continuation: oversold->short, overbought->long, top-N% volume only)\n{'='*80}")
    print(f"{'RSI pair':>12} | " + " | ".join(f"top{int(p*100):>3d}%".rjust(22) for p in VOL_TOP_PCTS))
    print(f"{'':>12} | " + " | ".join("n / win% / PF".rjust(22) for _ in VOL_TOP_PCTS))
    print("-" * (12 + 3 + len(VOL_TOP_PCTS) * 25))

    for os_th, ob_th in RSI_PAIRS:
        trades = build_for_thresholds(data, os_th, ob_th)
        cells = []
        for pct in VOL_TOP_PCTS:
            cutoff = trades['vol_ratio'].quantile(1 - pct)
            sub = trades[trades['vol_ratio'] >= cutoff]
            st = pooled_stats(sub)
            if st:
                cells.append(f"n={st['n']:4d} {st['win_rate']:4.1f}% PF={st['pf']:.2f}".rjust(22))
            else:
                cells.append("(no trades)".rjust(22))
        print(f"{f'{os_th}/{ob_th}':>12} | " + " | ".join(cells))

    print("\nFor reference, breakeven win rate given SL=2xATR/TP=4xATR (before friction) is ~33.3%;")
    print("PF > 1.0 and win rate meaningfully above ~33% across a spread of arbitrary threshold choices")
    print("(not just the original 30/70 + top-tercile combo) would indicate a robust effect, not a fluke.")


if __name__ == "__main__":
    main()
