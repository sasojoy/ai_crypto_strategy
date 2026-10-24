"""
DEV-WINDOW ONLY (< 2026-01-01). Investigates the calibration issue found
during the 2026-09-08 code audit: the locked momentum-continuation spec's
"top tercile" volume filter has always been computed as a SINGLE POOLED
threshold across all 5 symbols (dev_momentum_continuation.py's
`pd.qcut(trades['vol_ratio'], 3)`, and the live monitor's calibrated
fixed cutoff) -- but BTC's baseline vol_ratio distribution runs
structurally higher than the altcoins', so a shared threshold clears
44.4% of BTC's own triggers but only 25.0% of AVAX's. The "top tercile"
label doesn't mean "each symbol's own most extreme third" -- it's more
lenient toward BTC, stricter toward alts.

This script reruns the SAME locked entry/exit rules (RSI(14) oversold->
short/overbought->long, SL=2xATR/TP=4xATR/7-day hold, no pyramid --
matching dev_momentum_continuation.py exactly) but computes the volume
cutoff PER-SYMBOL (each symbol's own top tercile of its own trigger
population) instead of pooled, to see whether that changes the picture --
in particular, whether it changes BTC's now-consistently-worst dev-window
performance (which contradicts the actual holdout, where BTC was the
single BEST symbol -- see RESEARCH_FINDINGS.md "第二十四次測試" and the
2026-09-08 audit note).

This is a genuinely different signal-selection criterion from the locked,
holdout-validated spec -- NOT a portfolio-sizing tweak like the fixed-
notional or concurrency-cap corrections. It stays dev-window only and is
NOT deployed to the live paper-trading monitors or holdout without a
separate, explicit decision.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from dev_volume_confirm import (
    SYMBOLS, compute_atr, compute_rsi, find_triggers, trade_outcome,
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')


def load_1h_dev(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1h_extended.csv')
    df = pd.read_csv(path, parse_dates=['timestamp'])
    return df[df['timestamp'] < DEV_CUTOFF].sort_values('timestamp').reset_index(drop=True)


def build_trigger_pool():
    per_symbol_triggers = {}
    for s in SYMBOLS:
        df = load_1h_dev(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        triggers = []
        for i, reversion_direction in find_triggers(df):
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            triggers.append({'idx': i, 'direction': flip(reversion_direction),
                              'entry_time': df['timestamp'].iloc[i], 'vol_ratio': df['vol_ratio'].iloc[i]})
        per_symbol_triggers[s] = (df, pd.DataFrame(triggers))
    return per_symbol_triggers


def simulate_trades(per_symbol_triggers, cutoffs):
    """cutoffs: dict symbol -> vol_ratio cutoff to apply (pooled: same
    value for all symbols; per-symbol: each symbol's own value)."""
    all_trades = []
    for s in SYMBOLS:
        df, trig_df = per_symbol_triggers[s]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        cutoff = cutoffs[s]
        sub = trig_df[trig_df['vol_ratio'] >= cutoff]
        for row in sub.itertuples():
            outcome = trade_outcome(close, high, low, atr, row.idx, row.direction)
            if outcome is None:
                continue
            outcome['symbol'] = s
            outcome['direction'] = row.direction
            outcome['entry_time'] = row.entry_time
            all_trades.append(outcome)
    return pd.DataFrame(all_trades)


def pooled_stats(df):
    if df.empty:
        return None
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gw = df[df['equity_pnl_pct'] > 0]['equity_pnl_pct'].sum()
    gl = -df[df['equity_pnl_pct'] <= 0]['equity_pnl_pct'].sum()
    pf = gw / gl if gl > 0 else float('inf')
    equity = 1.0
    for pct in df.sort_values('entry_time')['equity_pnl_pct']:
        equity *= (1 + pct / 100)
    return {'n': n, 'wr': wr, 'pf': pf, 'compounded': (equity - 1) * 100}


def main():
    print("Building per-symbol trigger pools (dev window, 2020-2025)...")
    per_symbol_triggers = build_trigger_pool()

    pooled_all_ratios = pd.concat([t for _, t in per_symbol_triggers.values()])['vol_ratio']
    pooled_cutoff_value = pooled_all_ratios.quantile(2 / 3)
    pooled_cutoffs = {s: pooled_cutoff_value for s in SYMBOLS}
    persymbol_cutoffs = {s: per_symbol_triggers[s][1]['vol_ratio'].quantile(2 / 3) for s in SYMBOLS}

    print(f"\nPooled cutoff (single value, current locked spec): {pooled_cutoff_value:.3f}")
    print("Per-symbol cutoffs (this variant):")
    for s in SYMBOLS:
        n_total = len(per_symbol_triggers[s][1])
        n_pass_pooled = (per_symbol_triggers[s][1]['vol_ratio'] >= pooled_cutoff_value).mean() * 100
        n_pass_own = (per_symbol_triggers[s][1]['vol_ratio'] >= persymbol_cutoffs[s]).mean() * 100
        print(f"  {s}: own_cutoff={persymbol_cutoffs[s]:.3f}  "
              f"(pass-rate under POOLED cutoff={n_pass_pooled:.1f}%, under OWN cutoff={n_pass_own:.1f}%)")

    for label, cutoffs in [("A. POOLED cutoff (current locked spec)", pooled_cutoffs),
                            ("B. PER-SYMBOL cutoff (this variant)", persymbol_cutoffs)]:
        trades = simulate_trades(per_symbol_triggers, cutoffs)
        st = pooled_stats(trades)
        print(f"\n{'='*70}\n{label}\n{'='*70}")
        print(f"Overall: n={st['n']} win_rate={st['wr']:.1f}% PF={st['pf']:.2f} compounded={st['compounded']:+.2f}%")
        print("\nBy symbol:")
        print(trades.groupby('symbol')['equity_pnl_pct'].agg(['count', 'sum', 'mean']).to_string())
        trades['year'] = pd.to_datetime(trades['entry_time']).dt.year
        print("\nBy year:")
        print(trades.groupby('year')['equity_pnl_pct'].agg(['count', 'sum']).to_string())


if __name__ == "__main__":
    main()
