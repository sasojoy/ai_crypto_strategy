"""
DEV-WINDOW ONLY (< 2026-01-01). Turns the "extension before entry" finding
from dev_momentum_v8_win_scenarios_2.py into a CONTINUOUS risk-scaling
mechanism instead of a binary filter -- mirroring this research line's
own established playbook: a binary ADX>=25 filter was net-negative
(dev_momentum_adx_trend_filter.py, cut 46.3% of signals, annualized
return fell more than quality rose) but scaling RISK by the same
underlying signal (ADX/vol_ratio) instead of gating participation worked
(v5, v6). Tested here as a plain robustness/reference exercise on v8's
population, per the user's framing (2026-09-23) -- "optimization and
reference material for a trader," not a pipeline to deploy automatically.

The extension-vs-win-rate relationship is NON-monotonic (a hump peaking
around the middle of the distribution, confirmed at both tercile and
quintile resolution: ~43% win rate at the extremes, ~54% in the middle),
unlike v5/v6's monotonic vol_ratio/ADX relationships -- so this can't use
a simple percentile-rank-of-the-raw-value scaling. Instead: risk scales by
how CLOSE a trade's extension is to its symbol's own median extension
(among top-tercile-qualifying trades) -- closest to the center gets
MAX_RISK, furthest (either direction) gets MIN_RISK, same
population-relative-percentile-rank convention as v5/v6, just applied to
DISTANCE FROM CENTER instead of the raw value.

Reuses dev_momentum_tighter_tp.py's exact population/mechanics
(build_candidates(), SL_MULT, simulate_trade(tp_mult=3.0)) and
dev_momentum_v8_win_scenarios_2.py's extension_atr feature, unchanged.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_momentum_tighter_tp import build_candidates, simulate_trade, DEV_CUTOFF, DEV_START
from dev_momentum_v8_win_scenarios_2 import compute_features

TP_MULT = 3.0
MIN_RISK, MAX_RISK = 0.01, 0.03


def quarterly_stability(rows, pnl_col):
    d = pd.DataFrame(rows)
    d['q'] = pd.to_datetime(d['entry_time']).dt.to_period('Q')
    good, total = 0, 0
    for _, g in d.groupby('q'):
        total += 1
        gw = g.loc[g[pnl_col] > 0, pnl_col].sum()
        gl = -g.loc[g[pnl_col] <= 0, pnl_col].sum()
        pf = gw / gl if gl > 0 else float('inf')
        if pf > 1.0:
            good += 1
    return good, total


def summarize(rows, pnl_col, label, years):
    d = pd.DataFrame(rows)
    n = len(d)
    wr = (d[pnl_col] > 0).mean() * 100
    gw = d.loc[d[pnl_col] > 0, pnl_col].sum()
    gl = -d.loc[d[pnl_col] <= 0, pnl_col].sum()
    pf = gw / gl if gl > 0 else float('inf')
    total = d[pnl_col].sum()
    top3 = d.nlargest(3, pnl_col)[pnl_col].sum() / total * 100 if total > 0 else float('nan')
    good, tot = quarterly_stability(rows, pnl_col)
    avg_risk = d['risk_frac'].mean() * 100 if 'risk_frac' in d else 2.0
    print(f"{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total={total:+.1f}%  "
          f"ann={total/years:+.1f}%/yr  top3={top3:.1f}%  quarters_PF1={good}/{tot}  avg_risk={avg_risk:.2f}%")


def main():
    print("Building v8's exact population (classic locked-spec, SL=2.0xATR/TP=3.0xATR)...")
    candidates, frames = build_candidates()
    years = (DEV_CUTOFF - DEV_START).days / 365.25

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
        rows.append({**out, 'symbol': row.symbol, 'direction': row.direction, 'entry_time': row.entry_time,
                     'extension_atr': feats['extension_atr']})
    d = pd.DataFrame(rows)
    d = d[d['reason'] != 'TIMEOUT'].reset_index(drop=True)
    print(f"Trades analyzed: {len(d)}\n")

    # Population-relative anchor: each symbol's OWN median extension among its qualifying trades
    # (same "computed on this test's own population" principle used everywhere else in this
    # research line -- not a fixed external number).
    closeness_rank = 1 - d.groupby('symbol')['extension_atr'].transform(
        lambda x: (x - x.median()).abs().rank(pct=True))
    d['risk_frac_flat'] = 0.02
    d['risk_frac_scaled'] = MIN_RISK + closeness_rank * (MAX_RISK - MIN_RISK)

    # simulate_trade() already returns equity_pnl_pct at flat 2% -- reuse it directly instead of
    # re-deriving from raw price action (keeps this consistent with dev_momentum_tighter_tp.py's
    # own output).
    flat = [{'equity_pnl_pct': v, 'entry_time': t, 'risk_frac': 0.02}
            for v, t in zip(d['equity_pnl_pct'], d['entry_time'])]

    # rescale: simulate_trade's equity_pnl_pct assumes flat 2% baked in, so scaled = flat * (risk_scaled/0.02)
    scaled = [{'equity_pnl_pct': v * (rf / 0.02), 'entry_time': t, 'risk_frac': rf}
              for v, t, rf in zip(d['equity_pnl_pct'], d['entry_time'], d['risk_frac_scaled'])]

    print(f"{'='*78}\nA. FLAT 2% risk (v8 as shipped)\n{'='*78}")
    summarize(flat, 'equity_pnl_pct', '  ', years)

    print(f"\n{'='*78}\nB. Extension-distance-scaled risk (1%-3%, closer to symbol's own median = more)\n{'='*78}")
    summarize(scaled, 'equity_pnl_pct', '  ', years)

    print("\nBy symbol (A. flat):")
    print(pd.DataFrame(flat).assign(symbol=d['symbol']).groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
    print("\nBy symbol (B. scaled):")
    print(pd.DataFrame(scaled).assign(symbol=d['symbol']).groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
