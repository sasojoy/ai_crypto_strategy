"""
DEV-WINDOW ONLY (< 2026-01-01). ANALYSIS, not a new candidate -- follow-up
to dev_momentum_v8_win_scenarios.py (which tested the user's 3 proposed
scenarios and found only modest effects). This round tests 5 further
candidate scenarios, chosen for a theoretical reason each, on the exact
SAME v8 population (classic locked-spec entry, SL=2.0xATR/TP=3.0xATR),
each with ONE pre-specified operational definition:

  1. ADX(14) at the trigger bar -- quartiles. This research line already
     established "chop hurts, trend helps" at the risk-sizing level (v6);
     this asks whether it also shows up directly in WIN RATE for v8.
  2. Trend alignment -- is price on the "correct" side of a longer-term
     EMA(50) for the trade's direction (above it for a long, below for a
     short)? Binary: trading WITH vs AGAINST the bigger-picture trend.
  3. ATR expansion vs contraction -- current ATR(14) vs ATR 10 bars ago.
     Binary: expanding (genuine breakout regime) vs contracting (move
     happening inside an still-compressing range).
  4. Extension before entry -- how far price has already moved (in ATR
     units) in the trigger's direction over the prior 10 bars. Terciles:
     fresh move vs already-extended.
  5. BTC concurrent confirmation (non-BTC symbols only) -- is BTC's own
     trailing-10-bar return in the SAME direction as this trade? Binary:
     market-wide alignment vs isolated/against-BTC move.

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

from dev_momentum_tighter_tp import build_candidates, simulate_trade
from dev_momentum_adx_trend_filter import compute_adx

TP_MULT = 3.0
TRAILING_WINDOW = 10


def compute_features(frames, symbol, idx, direction):
    df = frames[symbol]
    if idx < 50:  # need 50 bars for EMA50 warm-up
        return None

    close = df['close']
    atr = df['atr']

    # 2. trend alignment vs EMA(50)
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[idx]
    price = close.iloc[idx]
    aligned_with_trend = (price > ema50) if direction == 'long' else (price < ema50)

    # 3. ATR expansion vs contraction
    if idx < TRAILING_WINDOW or np.isnan(atr.iloc[idx - TRAILING_WINDOW]) or atr.iloc[idx - TRAILING_WINDOW] <= 0:
        return None
    atr_expanding = atr.iloc[idx] > atr.iloc[idx - TRAILING_WINDOW]

    # 4. extension before entry (in ATR units, signed toward the trade's own direction)
    prior_price = close.iloc[idx - TRAILING_WINDOW]
    raw_move = price - prior_price
    extension_atr = (raw_move if direction == 'long' else -raw_move) / atr.iloc[idx]

    # 5. BTC concurrent confirmation (only meaningful for non-BTC symbols)
    btc_df = frames['BTC/USDT']
    btc_ts = df['timestamp'].iloc[idx]
    btc_match = btc_df.index[btc_df['timestamp'] == btc_ts]
    btc_aligned = None
    if len(btc_match) and btc_match[0] >= TRAILING_WINDOW:
        bidx = btc_match[0]
        btc_return = (btc_df['close'].iloc[bidx] - btc_df['close'].iloc[bidx - TRAILING_WINDOW]) / btc_df['close'].iloc[bidx - TRAILING_WINDOW]
        btc_aligned = (btc_return > 0) if direction == 'long' else (btc_return < 0)

    return {
        'aligned_with_trend': bool(aligned_with_trend),
        'atr_expanding': bool(atr_expanding),
        'extension_atr': float(extension_atr),
        'btc_aligned': btc_aligned,
    }


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


def main():
    print("Building v8's exact population (classic locked-spec, SL=2.0xATR/TP=3.0xATR)...")
    candidates, frames = build_candidates()
    for s, df in frames.items():
        df['adx'] = compute_adx(df)

    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction, TP_MULT)
        if out is None:
            continue
        feats = compute_features(frames, row.symbol, row.idx, row.direction)
        if feats is None:
            continue
        adx_value = df['adx'].iloc[row.idx]
        if np.isnan(adx_value):
            continue
        rows.append({**out, 'symbol': row.symbol, 'direction': row.direction, 'entry_time': row.entry_time,
                     'adx': adx_value, **feats})
    d = pd.DataFrame(rows)
    d = d[d['reason'] != 'TIMEOUT']
    print(f"Trades analyzed: {len(d)}  (baseline win_rate={(d['reason']=='TP').mean()*100:.1f}%)\n")

    d['adx_quartile'] = d.groupby('symbol')['adx'].transform(
        lambda x: pd.qcut(x, 4, labels=['Q1_weak', 'Q2', 'Q3', 'Q4_strong'], duplicates='drop'))
    report("1. ADX(14) quartile at trigger", d.groupby('adx_quartile', observed=True))

    report("2. Trend alignment vs EMA(50)", d.groupby('aligned_with_trend'))

    report("3. ATR expanding vs contracting (vs 10 bars ago)", d.groupby('atr_expanding'))

    d['extension_tercile'] = d.groupby('symbol')['extension_atr'].transform(
        lambda x: pd.qcut(x, 3, labels=['fresh', 'mid', 'already_extended'], duplicates='drop'))
    report("4. Extension before entry (ATR units, terciles)", d.groupby('extension_tercile', observed=True))

    non_btc = d[(d['symbol'] != 'BTC/USDT') & d['btc_aligned'].notna()]
    print(f"(5. BTC confirmation -- non-BTC trades only, n={len(non_btc)})")
    report("5. BTC concurrent trend confirmation (non-BTC symbols)", non_btc.groupby('btc_aligned'))

    print(f"{'='*78}\nCross-check: best single-feature cell x ADX Q4 (highest-conviction combo)\n{'='*78}")
    combo = d[(d['adx_quartile'] == 'Q4_strong') & (d['aligned_with_trend'])]
    report("ADX Q4 + trend-aligned", [('combo', combo)])


if __name__ == "__main__":
    main()
