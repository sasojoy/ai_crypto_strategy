"""
Computes the volume-ratio top-tercile cutoff for the locked RSI(14)
momentum-continuation strategy (see RESEARCH_FINDINGS.md "第二十三次測試"
and scripts/dev_momentum_continuation.py), for use by
paper_trading/momentum_monitor.py.

The backtests computed this tercile as a BATCH percentile over each
test's own trigger population (dev window, then separately the holdout
window). A live monitor can't do that -- it sees one bar at a time, not
a whole future window -- so this script calibrates a FIXED cutoff value
from all historical triggers up to now (2020-present) and the monitor
applies that fixed value prospectively. This is the standard, honest way
to turn a "percentile of this batch" backtest rule into a live rule: no
lookahead, but the cutoff should be periodically recalibrated (e.g. every
few months) by re-running this script, since the volume-ratio
distribution can drift over time.

2026-09-08 correction: this now calibrates a SEPARATE cutoff PER SYMBOL,
not one pooled value shared across all 5 -- an audit found the pooled
version let BTC clear the bar 44-45% of the time (its vol_ratio runs
structurally higher) versus only ~24-28% for the altcoins, which isn't
the intended "each symbol's own top third". See dev_momentum_continuation
.py's "CORRECTION" docstring note for the full writeup.

Also now calibrates the 5x5 daily-return correlation matrix used by the
correlation-aware portfolio-risk position cap (replacing the flat
"N concurrent positions" cap -- see scripts/dev_momentum_portfolio_risk.py
and DEPLOYMENT_RISK_ASSESSMENT.md). Verified on the dev window (both
under the old pooled-tercile and the corrected per-symbol-tercile trade
populations): a risk budget of ~3.0 keeps ~97% of the flat-cap's average
return while cutting max drawdown by ~20-24%.

Not part of the deployed app; run manually / on a schedule to refresh
paper_trading/thresholds.json.
"""
import os
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from dev_volume_confirm import SYMBOLS, compute_rsi, find_triggers

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'thresholds.json')


def load_1h_full(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1h_full.csv')
    return pd.read_csv(path, parse_dates=['timestamp']).sort_values('timestamp').reset_index(drop=True)


def compute_correlation_matrix():
    closes = {}
    for s in SYMBOLS:
        df = load_1h_full(s)
        closes[s] = df.set_index('timestamp')['close'].resample('1D').last()
    mat = pd.DataFrame(closes).dropna()
    return mat.pct_change().dropna().corr()


def main():
    per_symbol_ratios = {}
    latest_ts = None
    for s in SYMBOLS:
        df = load_1h_full(s)
        df['rsi'] = compute_rsi(df['close'])
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        ratios = [df['vol_ratio'].iloc[i] for i, _ in find_triggers(df) if not np.isnan(df['vol_ratio'].iloc[i])]
        per_symbol_ratios[s] = ratios
        if latest_ts is None or df['timestamp'].iloc[-1] > latest_ts:
            latest_ts = df['timestamp'].iloc[-1]

    cutoffs = {s: float(pd.Series(r).quantile(2 / 3)) for s, r in per_symbol_ratios.items()}
    corr = compute_correlation_matrix()
    result = {
        'vol_ratio_top_tercile_cutoff_by_symbol': cutoffs,
        'n_triggers_used_by_symbol': {s: len(r) for s, r in per_symbol_ratios.items()},
        'correlation_matrix': {s1: {s2: float(corr.loc[s1, s2]) for s2 in SYMBOLS} for s1 in SYMBOLS},
        'portfolio_risk_budget': 3.0,
        'calibrated_from_data_through': str(latest_ts),
        'calibrated_at': str(pd.Timestamp.now()),
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(result, f, indent=2)
    for s, c in cutoffs.items():
        print(f"  {s}: cutoff={c:.4f}  (from {len(per_symbol_ratios[s])} historical triggers)")
    print("\nCorrelation matrix:")
    print(corr.round(3).to_string())
    print(f"\nData through {latest_ts}. Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
