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

2026-09-09 addition: also calibrates a SECOND set of cutoffs
(vol_ratio_top_tercile_cutoff_causal_by_symbol) for momentum_monitor_v3.py's
real-time anticipatory-entry mechanism. v3 has to compare a still-forming
hour's PROJECTED volume ratio against a 20-bar volume MA that EXCLUDES that
hour's own volume (you can't know a not-yet-closed bar's volume as part of
its own baseline -- that would be circular). The MAIN cutoff above was
calibrated against an MA that INCLUDES each trigger bar's own volume (valid
for v1/v2 since they only ever evaluate a bar after it's closed) -- reusing
it for the excluding-MA ratio is an apples-to-oranges mismatch: a trigger
bar's own volume is usually above-average (that's why it's a candidate),
so excluding it shrinks the denominator and inflates the ratio by ~9% on
average (up to 13% per symbol, found and fixed 2026-09-09 during the
anticipatory-entry investigation -- see the artifact report from that
session). The causal cutoff is calibrated the same way, on the same
per-symbol trigger population, but with vol_ma20 excluding the current bar,
so it's the correct apples-to-apples threshold for v3's real-time use.

Also now calibrates the 5x5 daily-return correlation matrix used by the
correlation-aware portfolio-risk position cap (replacing the flat
"N concurrent positions" cap -- see scripts/dev_momentum_portfolio_risk.py
and DEPLOYMENT_RISK_ASSESSMENT.md). Verified on the dev window (both
under the old pooled-tercile and the corrected per-symbol-tercile trade
populations): a risk budget of ~3.0 keeps ~97% of the flat-cap's average
return while cutting max drawdown by ~20-24%.

2026-09-14 addition: also calibrates `vol_ratio_p99_within_tercile_by_symbol`
for momentum_monitor_v5.py's volume-scaled risk sizing (see
scripts/dev_momentum_vol_scaled_risk.py and RESEARCH_FINDINGS.md). The
backtest scaled risk by each trade's percentile RANK of vol_ratio within
its symbol's top-tercile-qualifying subset -- a live monitor can't rank
against a still-unknown future population any more than it can compute a
live tercile, so this fixes a second calibrated anchor (the 99th
percentile of vol_ratio among that symbol's OWN top-tercile-qualifying
historical triggers, not the raw max, to avoid one freak outlier pinning
the whole scale) alongside the existing cutoff. v5 then maps a live trade's
vol_ratio linearly between [cutoff -> risk 1%] and [this p99 -> risk 3%],
clamping outside that range, as a live approximation of the backtest's
population-relative rank.

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
    per_symbol_ratios_causal = {}
    latest_ts = None
    for s in SYMBOLS:
        df = load_1h_full(s)
        df['rsi'] = compute_rsi(df['close'])
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        df['vol_ma20_causal'] = df['volume'].rolling(20).mean().shift(1)
        df['vol_ratio_causal'] = df['volume'] / df['vol_ma20_causal']
        triggers = find_triggers(df)
        ratios = [df['vol_ratio'].iloc[i] for i, _ in triggers if not np.isnan(df['vol_ratio'].iloc[i])]
        ratios_causal = [df['vol_ratio_causal'].iloc[i] for i, _ in triggers if not np.isnan(df['vol_ratio_causal'].iloc[i])]
        per_symbol_ratios[s] = ratios
        per_symbol_ratios_causal[s] = ratios_causal
        if latest_ts is None or df['timestamp'].iloc[-1] > latest_ts:
            latest_ts = df['timestamp'].iloc[-1]

    cutoffs = {s: float(pd.Series(r).quantile(2 / 3)) for s, r in per_symbol_ratios.items()}
    cutoffs_causal = {s: float(pd.Series(r).quantile(2 / 3)) for s, r in per_symbol_ratios_causal.items()}
    # p99 of vol_ratio WITHIN the top-tercile-qualifying subset only (>= cutoff), per symbol --
    # the risk-scaling upper anchor for momentum_monitor_v5.py.
    p99_within_tercile = {}
    for s, r in per_symbol_ratios.items():
        series = pd.Series(r)
        top = series[series >= cutoffs[s]]
        p99_within_tercile[s] = float(top.quantile(0.99)) if len(top) else cutoffs[s]
    corr = compute_correlation_matrix()
    result = {
        'vol_ratio_top_tercile_cutoff_by_symbol': cutoffs,
        'vol_ratio_top_tercile_cutoff_causal_by_symbol': cutoffs_causal,
        'vol_ratio_p99_within_tercile_by_symbol': p99_within_tercile,
        'n_triggers_used_by_symbol': {s: len(r) for s, r in per_symbol_ratios.items()},
        'correlation_matrix': {s1: {s2: float(corr.loc[s1, s2]) for s2 in SYMBOLS} for s1 in SYMBOLS},
        'portfolio_risk_budget': 3.0,
        'calibrated_from_data_through': str(latest_ts),
        'calibrated_at': str(pd.Timestamp.now()),
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(result, f, indent=2)
    for s, c in cutoffs.items():
        print(f"  {s}: cutoff={c:.4f}  causal_cutoff={cutoffs_causal[s]:.4f}  p99_within_tercile={p99_within_tercile[s]:.4f}  "
              f"(from {len(per_symbol_ratios[s])} historical triggers)")
    print("\nCorrelation matrix:")
    print(corr.round(3).to_string())
    print(f"\nData through {latest_ts}. Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
