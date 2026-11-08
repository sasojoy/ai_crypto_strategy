"""
DEV-WINDOW ONLY (< 2026-01-01). Tests combining v3's anticipatory-entry
mechanism (fresh-cross-guard FIXED version, 2026-09-19) with v6's
ADX-scaled risk sizing -- two independently (thinly) holdout-validated
mechanisms that change ORTHOGONAL things (v3: entry timing; v6: per-trade
risk%) and have never been tested together, per the user's explicit
request after reviewing both variants' current status.

Reuses v3's exact (post-fix) trigger population via
dev_momentum_v3_early_reject.simulate_symbol() -- same entries, same
SL=2xATR/TP=4xATR/168-bar-hold mechanics, same VOL_UNCONFIRMED
confirmation checkpoint -- and only varies how each trade's risk% is
sized:
  A. V3 ALONE: flat 2% (BASE_RISK_PER_TRADE), i.e. v3 exactly as shipped.
  B. V3 + V6: risk scales 1%-3% by each trade's ADX(14) (at the same H-1
     closed bar used for its entry threshold) PERCENTILE RANK within its
     own symbol's v3-qualifying population -- the identical "rank" formula
     momentum_monitor_v6.py itself uses, just applied to v3's population
     instead of the classic closed-bar population.

Since risk% scaling never changes which trades win or lose (only how much
is risked), win_rate is identical between A and B by construction; PF and
total P&L are the only meaningful comparison points.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_momentum_v3_early_reject import (
    SYMBOLS, simulate_symbol, resolve_policy, leg_pnl_pct,
)

MIN_RISK, MAX_RISK = 0.01, 0.03


def leg_pnl_pct_scaled(direction, entry_price, exit_price, sl_price, risk_frac):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - 0.0014
    else:
        pnl = (entry_price - exit_price) / entry_price - 0.0014
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * risk_frac * 100 if sl_dist_pct > 0 else 0.0


def quarterly_stability(rows):
    d = pd.DataFrame(rows)
    d['q'] = pd.to_datetime(d['entry_time']).dt.to_period('Q')
    good, total = 0, 0
    for q, g in d.groupby('q'):
        total += 1
        gw = g[g['pnl'] > 0]['pnl'].sum()
        gl = -g[g['pnl'] <= 0]['pnl'].sum()
        pf = gw / gl if gl > 0 else float('inf')
        if pf > 1.0:
            good += 1
    return good, total


def concentration(rows, top_n=3):
    d = pd.DataFrame(rows)
    total = d['pnl'].sum()
    if total <= 0:
        return float('nan')
    top = d.sort_values('pnl', ascending=False)['pnl'].head(top_n).sum()
    return top / total * 100


def stats_for(rows):
    d = pd.DataFrame(rows)
    if d.empty:
        return None
    n = len(d)
    wr = (d['pnl'] > 0).mean() * 100
    gw = d[d['pnl'] > 0]['pnl'].sum()
    gl = -d[d['pnl'] <= 0]['pnl'].sum()
    pf = gw / gl if gl > 0 else float('inf')
    years = (d['entry_time'].max() - d['entry_time'].min()) / np.timedelta64(365, 'D')
    total_pnl = d['pnl'].sum()
    return dict(n=n, win_rate=wr, pf=pf, total_pnl=total_pnl,
                additive_ann=total_pnl / years if years > 0 else float('nan'),
                avg_risk=d['risk_frac'].mean() * 100)


def main():
    all_trades = []
    print("Re-simulating v3's (fixed) anticipatory-entry mechanism across the dev window...")
    for s in SYMBOLS:
        trades, info = simulate_symbol(s)
        all_trades.extend(trades)
        print(f"  {s}: {info['n_entries']} entries")
    print(f"\nTotal v3 entries: {len(all_trades)}")

    # ADX percentile rank within each symbol's OWN v3-qualifying population (mirrors
    # momentum_monitor_v6.py's rank-based scaling exactly, just on v3's population).
    df_adx = pd.DataFrame([{'symbol': t['symbol'], 'adx': t['adx_at_entry']} for t in all_trades])
    df_adx['adx_rank'] = df_adx.groupby('symbol')['adx'].rank(pct=True)
    for t, rank in zip(all_trades, df_adx['adx_rank']):
        t['adx_rank'] = rank if not np.isnan(rank) else 0.5

    rows_flat, rows_scaled = [], []
    for t in all_trades:
        _, price, reason = resolve_policy(t, None)  # baseline confirmation policy (no early-reject)
        pnl_flat = leg_pnl_pct(t['direction'], t['entry_price'], price, t['sl_price'])
        rows_flat.append(dict(pnl=pnl_flat, reason=reason, entry_time=t['entry_time'],
                               symbol=t['symbol'], risk_frac=0.02))

        risk_frac = MIN_RISK + t['adx_rank'] * (MAX_RISK - MIN_RISK)
        pnl_scaled = leg_pnl_pct_scaled(t['direction'], t['entry_price'], price, t['sl_price'], risk_frac)
        rows_scaled.append(dict(pnl=pnl_scaled, reason=reason, entry_time=t['entry_time'],
                                 symbol=t['symbol'], risk_frac=risk_frac))

    st_flat = stats_for(rows_flat)
    st_scaled = stats_for(rows_scaled)

    gq_flat, tq_flat = quarterly_stability(rows_flat)
    gq_scaled, tq_scaled = quarterly_stability(rows_scaled)
    conc_flat = concentration(rows_flat)
    conc_scaled = concentration(rows_scaled)

    print(f"\n{'='*70}\nA. V3 ALONE (flat 2% risk, as shipped)\n{'='*70}")
    print(f"  n={st_flat['n']}  win_rate={st_flat['win_rate']:.1f}%  PF={st_flat['pf']:.2f}  "
          f"total_pnl={st_flat['total_pnl']:+.1f}%  additive_ann={st_flat['additive_ann']:+.1f}%/yr  "
          f"avg_risk={st_flat['avg_risk']:.2f}%")
    print(f"  quarterly PF>1: {gq_flat}/{tq_flat}  |  top-3-trade concentration: {conc_flat:.1f}%")

    print(f"\n{'='*70}\nB. V3 + V6 (ADX rank-scaled risk 1%-3%, on v3's own trigger population)\n{'='*70}")
    print(f"  n={st_scaled['n']}  win_rate={st_scaled['win_rate']:.1f}%  PF={st_scaled['pf']:.2f}  "
          f"total_pnl={st_scaled['total_pnl']:+.1f}%  additive_ann={st_scaled['additive_ann']:+.1f}%/yr  "
          f"avg_risk={st_scaled['avg_risk']:.2f}%")
    print(f"  quarterly PF>1: {gq_scaled}/{tq_scaled}  |  top-3-trade concentration: {conc_scaled:.1f}%")

    print("\nBy direction (A. flat):")
    print(pd.DataFrame([{**r, 'direction': t['direction']} for r, t in zip(rows_flat, all_trades)])
          .groupby('direction')['pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
    print("\nBy direction (B. ADX-scaled):")
    print(pd.DataFrame([{**r, 'direction': t['direction']} for r, t in zip(rows_scaled, all_trades)])
          .groupby('direction')['pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())

    print("\nBy symbol (A. flat):")
    print(pd.DataFrame(rows_flat).groupby('symbol')['pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                                 total='sum').to_string())
    print("\nBy symbol (B. ADX-scaled):")
    print(pd.DataFrame(rows_scaled).groupby('symbol')['pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                                   total='sum').to_string())


if __name__ == "__main__":
    main()
