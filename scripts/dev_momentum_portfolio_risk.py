"""
DEV-WINDOW ONLY (< 2026-01-01). Tests two portfolio-construction
refinements requested by the user on top of the locked momentum-
continuation + pyramid mechanism (dev_momentum_pyramid_backtest.py),
addressing the two concrete weaknesses that diagnostic already surfaced:

1. BTC EXCLUSION: BTC was the only net-losing symbol under both the
   no-pyramid and pyramid mechanics; test dropping it from the traded
   universe entirely.
2. CORRELATION-AWARE RISK BUDGET replacing the flat "N concurrent
   position groups" cap: the 5 symbols' daily returns (dev window) are
   moderately-to-highly correlated (0.55-0.80 pairwise, computed below),
   so a flat headcount cap treats 5 simultaneous same-direction BTC/ETH/
   SOL/NEAR/AVAX longs as equally risky as 5 simultaneous positions split
   across both directions -- which understates real concentration risk in
   the first case and overstates it in the second. This replaces the cap
   with a portfolio-variance budget: each open leg is a +1 (long) or -1
   (short) unit-exposure; portfolio risk = sqrt(sum_i sum_j e_i e_j
   corr(sym_i, sym_j)); a new signal is accepted only if adding it keeps
   this risk at or under a fixed budget. Same-direction correlated legs
   now cost MORE than one count each; opposite-direction correlated legs
   (partial hedges) cost less.

Both are portfolio-construction changes on top of the ALREADY-VALIDATED
entry/exit rules -- not a new signal search -- so this stays in the
lower-risk territory of "how much of the existing edge to take and how
to size it", still dev-window only, still not touching holdout.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys
import itertools

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from dev_momentum_pyramid_backtest import build_candidates, simulate_group, DEV_CUTOFF, DEV_START
from dev_volume_confirm import SYMBOLS

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')


def compute_correlation_matrix():
    closes = {}
    for s in SYMBOLS:
        df = pd.read_csv(os.path.join(CACHE_DIR, s.replace('/', '_') + '_1h_extended.csv'), parse_dates=['timestamp'])
        closes[s] = df.set_index('timestamp')['close'].resample('1D').last()
    mat = pd.DataFrame(closes).dropna()
    return mat.pct_change().dropna().corr()


def portfolio_risk(open_legs, corr):
    """open_legs: list of (symbol, direction_sign) with direction_sign +1/-1."""
    if not open_legs:
        return 0.0
    variance = 0.0
    for (s1, e1), (s2, e2) in itertools.product(open_legs, repeat=2):
        variance += e1 * e2 * corr.loc[s1, s2]
    return np.sqrt(max(variance, 0.0))


def run_variant(candidates, frames, corr, symbols_allowed, mode, budget=None, flat_cap=5):
    cand = candidates[candidates['symbol'].isin(symbols_allowed)].reset_index(drop=True)
    open_legs = []          # list of dicts: symbol, direction_sign, exit_time -- for risk accounting
    open_group_exits = []   # exit_time of accepted GROUPS -- for flat-cap mode / signal gating
    all_originals, all_adds = [], []
    n_accepted, n_rejected = 0, 0

    for row in cand.itertuples():
        entry_time = row.entry_time
        e = 1 if row.direction == 'long' else -1

        open_legs = [l for l in open_legs if l['exit_time'] > entry_time]
        open_group_exits = [t for t in open_group_exits if t > entry_time]

        if mode == 'flat':
            accept = len(open_group_exits) < flat_cap
        else:  # correlation-aware risk budget
            trial = [(l['symbol'], l['direction_sign']) for l in open_legs] + [(row.symbol, e)]
            accept = portfolio_risk(trial, corr) <= budget

        if not accept:
            n_rejected += 1
            continue

        df = frames[row.symbol]
        result = simulate_group(df, row.idx, row.direction)
        if result is None:
            continue
        original, add, group_exit_idx = result
        n_accepted += 1
        group_exit_time = df['timestamp'].iloc[group_exit_idx]
        open_group_exits.append(group_exit_time)
        open_legs.append({'symbol': row.symbol, 'direction_sign': e, 'exit_time': group_exit_time})

        original.update(symbol=row.symbol, direction=row.direction)
        all_originals.append(original)
        if add is not None:
            add.update(symbol=row.symbol, direction=row.direction)
            all_adds.append(add)

    return all_originals, all_adds, n_accepted, n_rejected


def stats(df):
    if df is None or (hasattr(df, 'empty') and df.empty) or len(df) == 0:
        return None
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gw = df[df['equity_pnl_pct'] > 0]['equity_pnl_pct'].sum()
    gl = -df[df['equity_pnl_pct'] <= 0]['equity_pnl_pct'].sum()
    pf = gw / gl if gl > 0 else float('inf')
    return {'n': n, 'wr': wr, 'pf': pf, 'sum': df['equity_pnl_pct'].sum()}


def main():
    corr = compute_correlation_matrix()
    print("Pairwise daily-return correlation (dev window):")
    print(corr.round(3).to_string())

    print("\nBuilding candidates...")
    candidates, frames = build_candidates()
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    variants = [
        ("A. Baseline: flat cap=5, all 5 symbols", ['flat', 5], SYMBOLS),
        ("B. Flat cap=5, BTC EXCLUDED", ['flat', 5], [s for s in SYMBOLS if s != 'BTC/USDT']),
        ("C. Correlation-risk budget=2.5, all 5 symbols", ['corr', 2.5], SYMBOLS),
        ("D. Correlation-risk budget=3.0, all 5 symbols", ['corr', 3.0], SYMBOLS),
        ("E. Correlation-risk budget=3.5, all 5 symbols", ['corr', 3.5], SYMBOLS),
        ("F. Correlation-risk budget=3.0, BTC EXCLUDED", ['corr', 3.0], [s for s in SYMBOLS if s != 'BTC/USDT']),
    ]

    print(f"\n{'='*100}")
    print(f"{'Variant':<48}{'accepted':>9}{'rejected':>9}{'n_legs':>8}{'win%':>7}{'PF':>6}{'ann.%/yr':>10}")
    print('=' * 100)
    for label, params, symbols_allowed in variants:
        mode = params[0]
        kwargs = {'flat_cap': params[1]} if mode == 'flat' else {'budget': params[1]}
        originals, adds, n_acc, n_rej = run_variant(candidates, frames, corr, symbols_allowed, mode, **kwargs)
        combined = pd.DataFrame(originals + adds)
        st = stats(combined)
        if st:
            ann = st['sum'] / years
            print(f"{label:<48}{n_acc:>9}{n_rej:>9}{st['n']:>8}{st['wr']:>6.1f}%{st['pf']:>6.2f}{ann:>9.2f}%")
        else:
            print(f"{label:<48}{n_acc:>9}{n_rej:>9}{'0':>8}")


if __name__ == "__main__":
    main()
