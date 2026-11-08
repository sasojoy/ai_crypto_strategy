"""
DEV-WINDOW ONLY (< 2026-01-01). ANALYSIS, not a new candidate -- answers
the user's question: on v8's exact population (classic locked-spec entry,
SL=2.0xATR/TP=3.0xATR, the accepted 1.5:1 candidate), is there a
SPECIFIC, identifiable scenario where the win (TP-hit) probability is
much higher than the ~47.8% baseline? Tests exactly the three hypotheses
the user proposed, each with ONE pre-specified operational definition
(not tuned after looking at results, and not a hunt for whichever cutoff
looks best):

  A. Volume magnitude WITHIN the already-qualifying (top-tercile) set --
     does clearing the bar by a LOT predict a better win rate than just
     barely clearing it? Bucketed into quartiles of vol_ratio among
     qualifying trades.
  B. "Quiet before the breakout" -- the trailing 10-bar average vol_ratio
     BEFORE the trigger bar (excluding it) is low, i.e. the market was
     unusually quiet right up until this trigger. Bucketed into terciles.
  C. "Reversal after a high-volume move the OTHER way" -- within the 10
     bars before the trigger, was there a bar that (a) moved price AGAINST
     the eventual trigger's direction and (b) had elevated volume (vol_
     ratio >= that symbol's own top-tercile cutoff, i.e. was itself an
     unusually high-volume bar)? Binary: yes/no.

Reuses dev_momentum_tighter_tp.py's exact population/mechanics
(build_candidates(), SL_MULT, simulate_trade(tp_mult=3.0)) unchanged.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_momentum_tighter_tp import build_candidates, simulate_trade, SL_MULT

TP_MULT = 3.0  # v8's accepted candidate
TRAILING_WINDOW = 10  # bars looked back for features B and C, decided a priori


def compute_features(df, idx, direction, cutoff):
    """df: full 1H frame for this symbol (has close/vol_ratio columns).
    idx: the trigger bar's index. direction: the trade's direction
    ('long'/'short' -- continuation, so 'long' means price is expected to
    keep rising)."""
    start = max(0, idx - TRAILING_WINDOW)
    window = df.iloc[start:idx]  # excludes the trigger bar itself
    if len(window) < TRAILING_WINDOW:
        return None  # not enough history right at the start of the series

    # B: trailing average vol_ratio before the trigger
    trailing_vol_avg = window['vol_ratio'].mean()

    # C: was there a bar in the window that moved price AGAINST this trade's direction
    # AND had elevated volume (>= this symbol's own top-tercile cutoff)?
    bar_returns = window['close'].pct_change()
    if start > 0:
        bar_returns.iloc[0] = (window['close'].iloc[0] - df['close'].iloc[start - 1]) / df['close'].iloc[start - 1]
    against_move = bar_returns < 0 if direction == 'long' else bar_returns > 0
    high_vol = window['vol_ratio'] >= cutoff
    had_reverse_spike = bool((against_move & high_vol).any())

    return {'trailing_vol_avg': trailing_vol_avg, 'had_reverse_spike': had_reverse_spike}


def main():
    print("Building v8's exact population (classic locked-spec, SL=2.0xATR/TP=3.0xATR)...")
    candidates, frames = build_candidates()

    # per-symbol non-causal top-tercile cutoff, same convention used everywhere else in this
    # research line, needed for feature C's "was that prior bar itself high-volume" check.
    cutoffs = candidates.groupby('symbol')['vol_ratio'].quantile(2 / 3).to_dict()
    # NOTE: candidates here is ALREADY filtered to the top tercile, so this recomputes the
    # cutoff on the qualifying subset itself (a slightly higher bar than the original raw-trigger
    # cutoff) -- deliberately: feature C asks "was that prior bar ALSO a strong volume bar", and
    # using the same qualifying-population's own bar for consistency is the natural yardstick.

    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction, TP_MULT)
        if out is None:
            continue
        feats = compute_features(df, row.idx, row.direction, cutoffs[row.symbol])
        if feats is None:
            continue
        rows.append({**out, 'symbol': row.symbol, 'direction': row.direction,
                     'entry_time': row.entry_time, 'vol_ratio': row.vol_ratio, **feats})
    d = pd.DataFrame(rows)
    d = d[d['reason'] != 'TIMEOUT']  # negligible, keeps the SL-vs-TP win-rate question clean
    print(f"Trades analyzed: {len(d)}  (baseline win_rate={(d['reason']=='TP').mean()*100:.1f}%)\n")

    def report(label, groups):
        print(f"{'='*78}\n{label}\n{'='*78}")
        for name, g in groups:
            if len(g) == 0:
                continue
            wr = (g['reason'] == 'TP').mean() * 100
            gw = g.loc[g['equity_pnl_pct'] > 0, 'equity_pnl_pct'].sum()
            gl = -g.loc[g['equity_pnl_pct'] <= 0, 'equity_pnl_pct'].sum()
            pf = gw / gl if gl > 0 else float('inf')
            print(f"  {name}: n={len(g)}  win_rate={wr:.1f}%  PF={pf:.2f}")
        print()

    print("A. Volume magnitude WITHIN the qualifying (top-tercile) set (quartiles of vol_ratio)")
    d['vol_quartile'] = d.groupby('symbol')['vol_ratio'].transform(
        lambda x: pd.qcut(x, 4, labels=['Q1_low', 'Q2', 'Q3', 'Q4_high'], duplicates='drop'))
    report("A. Volume magnitude quartile (within qualifying set)", d.groupby('vol_quartile', observed=True))

    print("B. Trailing 10-bar average volume BEFORE the trigger ('quiet before breakout'?)")
    d['trailing_vol_tercile'] = d.groupby('symbol')['trailing_vol_avg'].transform(
        lambda x: pd.qcut(x, 3, labels=['low_quiet', 'mid', 'high_already_loud'], duplicates='drop'))
    report("B. Trailing volume tercile (before trigger)", d.groupby('trailing_vol_tercile', observed=True))

    print("C. A high-volume move AGAINST this trade's direction within the prior 10 bars?")
    report("C. Reverse high-volume spike in prior window", d.groupby('had_reverse_spike'))

    print(f"{'='*78}\nCross-check: A x C combined (highest-conviction cell)\n{'='*78}")
    top_and_reverse = d[(d['vol_quartile'] == 'Q4_high') & (d['had_reverse_spike'])]
    top_no_reverse = d[(d['vol_quartile'] == 'Q4_high') & (~d['had_reverse_spike'])]
    for name, g in [('Q4 volume + reverse spike', top_and_reverse), ('Q4 volume, no reverse spike', top_no_reverse)]:
        if len(g) == 0:
            print(f"  {name}: n=0")
            continue
        wr = (g['reason'] == 'TP').mean() * 100
        gw = g.loc[g['equity_pnl_pct'] > 0, 'equity_pnl_pct'].sum()
        gl = -g.loc[g['equity_pnl_pct'] <= 0, 'equity_pnl_pct'].sum()
        pf = gw / gl if gl > 0 else float('inf')
        print(f"  {name}: n={len(g)}  win_rate={wr:.1f}%  PF={pf:.2f}")


if __name__ == "__main__":
    main()
