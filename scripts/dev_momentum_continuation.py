"""
DEVELOPMENT-WINDOW ONLY (< 2026-01-01). Follow-up to dev_volume_confirm.py.
That test found a statistically significant (p<0.001) NEGATIVE correlation
between volume-at-trigger and the P&L of an RSI(14) oversold-long/
overbought-short MEAN-REVERSION bet -- i.e. high volume at an RSI extreme
predicted the reversal bet would do WORSE, consistent with test #9's
finding (funding-rate extremes) that this market favors momentum
continuation over reversal at this horizon.

This script tests the natural flip that finding implies, which has NOT
been tested before (test #9 only tested two REVERSAL directions on
funding-rate extremes, both of which failed -- it never tested an actual
continuation-following strategy on any data source): treat RSI(14)
oversold as a SHORT continuation signal (price still falling) and RSI(14)
overbought as a LONG continuation signal (price still rising), i.e. the
exact opposite side of the same triggers used in dev_volume_confirm.py.
Same trigger definitions, same SL/TP/hold/cooldown mechanics, same volume-
tercile bucketing -- only the trade direction assigned to each trigger
type is flipped, so results are directly comparable to the mean-reversion
run.

Not part of the deployed app; safe to delete after use.

=== LOCKED CANDIDATE SPEC (2026-09-08) ===
After this test showed a clean profile (positive every year 2020-2025,
positive in 4/5 symbols with the 5th flat, top-3-trade concentration only
0.4%, 18/24 quarters PF>1.0 with no signal-count blowups, and a smooth
monotonic robustness gradient across a 5x4 RSI-threshold x volume-cutoff
control grid in dev_momentum_control.py), the user explicitly locked this
exact spec as the official candidate for eventual holdout validation:
  - RSI(14) cross below 30 (oversold) -> SHORT; cross above 70
    (overbought) -> LONG (momentum continuation, not reversal).
  - Volume filter: current-bar volume / trailing-20-bar average volume,
    keep only the TOP TERCILE (computed on the trigger population itself,
    not a fixed absolute cutoff).
  - SL=2xATR(14), TP=4xATR(14), max hold 168 1H bars (7 days), 8-bar
    cooldown per symbol, 0.14% round-trip friction, 2% risk/trade.
This file's code is the reference implementation -- any future holdout
script must import these functions UNCHANGED, per the project's one-shot
holdout discipline (see RESEARCH_FINDINGS.md / NEXT_STEPS.md). The 30/70
+ top-tercile choice was fixed BEFORE the control-grid robustness check
ran; picking a different, better-looking cell out of that grid now (e.g.
20/80 + top20%) would be exactly the test-set cherry-picking this whole
project's methodology exists to avoid, so it is deliberately NOT done.
Not yet sent to holdout as of this lock -- that is a separate, later
decision.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    SYMBOLS, load_1h, compute_atr, compute_rsi, find_triggers, trade_outcome,
    pooled_stats, random_benchmark_for_subset,
)


def flip(direction):
    return 'short' if direction == 'long' else 'long'


def build_trigger_dataset():
    all_trades = []
    for s in SYMBOLS:
        df = load_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']

        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        triggers = find_triggers(df)  # (i, 'long') = oversold event, (i, 'short') = overbought event
        n_trig = 0
        for i, reversion_direction in triggers:
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            signal = 'oversold' if reversion_direction == 'long' else 'overbought'
            continuation_direction = flip(reversion_direction)
            outcome = trade_outcome(close, high, low, atr, i, continuation_direction)
            if outcome is None:
                continue
            outcome['symbol'] = s
            outcome['signal'] = signal
            outcome['trade_direction'] = continuation_direction
            outcome['vol_ratio'] = df['vol_ratio'].iloc[i]
            outcome['timestamp'] = df['timestamp'].iloc[i]
            all_trades.append(outcome)
            n_trig += 1
        print(f"  {s}: {n_trig} triggers")
    return pd.DataFrame(all_trades)


def main():
    print("Building RSI(14) oversold/overbought MOMENTUM-CONTINUATION dataset (1H bars, dev window)...")
    print("(oversold -> short, overbought -> long -- the flip of the mean-reversion run)\n")
    trades = build_trigger_dataset()
    print(f"\nTotal triggers with valid outcome + volume data: {len(trades)}")
    if trades.empty:
        return

    print(f"\n{'='*60}\nBASELINE: unconditional momentum-continuation (no volume filter)\n{'='*60}")
    for signal in ['oversold', 'overbought']:
        sub = trades[trades['signal'] == signal]
        st = pooled_stats(sub)
        if st:
            print(f"  {signal.upper()} (-> {sub['trade_direction'].iloc[0]}): n={st['n']} win_rate={st['win_rate']:.1f}% "
                  f"PF={st['pf']:.2f} compounded={st['compounded']:+.2f}%")
    st_all = pooled_stats(trades)
    print(f"  COMBINED: n={st_all['n']} win_rate={st_all['win_rate']:.1f}% PF={st_all['pf']:.2f} compounded={st_all['compounded']:+.2f}%")

    print(f"\n{'='*60}\nDoes volume level strengthen the continuation bet?\n{'='*60}")
    trades['vol_tercile'] = pd.qcut(trades['vol_ratio'], 3, labels=['low', 'mid', 'high'])
    for signal in ['oversold', 'overbought', 'both']:
        sub = trades if signal == 'both' else trades[trades['signal'] == signal]
        print(f"\n  -- {signal.upper()} --")
        for tercile in ['low', 'mid', 'high']:
            tsub = sub[sub['vol_tercile'] == tercile]
            st = pooled_stats(tsub)
            if st:
                print(f"    vol={tercile:4s}: n={st['n']:4d} win_rate={st['win_rate']:.1f}% PF={st['pf']:.2f} compounded={st['compounded']:+.2f}%")
    rho, pval = spearmanr(trades['vol_ratio'], trades['equity_pnl_pct'])
    print(f"\n  Spearman corr(vol_ratio, trade P&L), all triggers pooled: rho={rho:.3f} p={pval:.3f}")
    print("  (For comparison: the mean-reversion run on the SAME triggers scored rho=-0.164, p<0.001.")
    print("   If continuation is the real mechanism, this correlation should flip sign and be similarly significant.)")

    print(f"\n{'='*60}\nRandom-entry benchmark for the HIGH-volume subgroup\n{'='*60}")
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
