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


def main():
    all_ratios = []
    latest_ts = None
    for s in SYMBOLS:
        df = load_1h_full(s)
        df['rsi'] = compute_rsi(df['close'])
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        for i, _ in find_triggers(df):
            v = df['vol_ratio'].iloc[i]
            if not np.isnan(v):
                all_ratios.append(v)
        if latest_ts is None or df['timestamp'].iloc[-1] > latest_ts:
            latest_ts = df['timestamp'].iloc[-1]

    cutoff = float(pd.Series(all_ratios).quantile(2 / 3))
    result = {
        'vol_ratio_top_tercile_cutoff': cutoff,
        'n_triggers_used': len(all_ratios),
        'calibrated_from_data_through': str(latest_ts),
        'calibrated_at': str(pd.Timestamp.now()),
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Calibrated cutoff: {cutoff:.4f}  (from {len(all_ratios)} historical triggers, data through {latest_ts})")
    print(f"Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
