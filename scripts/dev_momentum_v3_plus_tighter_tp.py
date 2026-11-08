"""
DEV-WINDOW ONLY (< 2026-01-01). Tests combining v3's (fresh-cross-guard
FIXED, 2026-09-19) anticipatory-entry mechanism with the user-accepted
1.5:1 reward:risk candidate (SL=2.0xATR/TP=3.0xATR,
dev_momentum_tighter_tp.py) -- two orthogonal levers (entry timing vs exit
distance) that have never been tested together.

Reuses dev_momentum_v3_early_reject.simulate_symbol(), now parameterized
by tp_mult, so the SAME entry mechanism, confirmation checkpoint, and
population-generation logic is used for both scenarios -- only TP changes:
  A. V3 AT 2:1 (as shipped): TP=4.0xATR -- the corrected baseline already
     reported (n=4,381, PF 1.11, +468.6% total, 19/24 quarters).
  B. V3 AT 1.5:1: TP=3.0xATR, SL unchanged at 2.0xATR.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_momentum_v3_early_reject import SYMBOLS, simulate_symbol, resolve_policy, leg_pnl_pct


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
    top = d.nlargest(top_n, 'pnl')['pnl'].sum()
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
                additive_ann=total_pnl / years if years > 0 else float('nan'))


def run_scenario(tp_mult, label):
    all_trades = []
    for s in SYMBOLS:
        trades, info = simulate_symbol(s, tp_mult=tp_mult)
        all_trades.extend(trades)
        print(f"  {s}: {info['n_entries']} entries")
    print(f"  Total: {len(all_trades)}")

    rows = []
    for t in all_trades:
        _, price, reason = resolve_policy(t, None)
        pnl = leg_pnl_pct(t['direction'], t['entry_price'], price, t['sl_price'])
        rows.append(dict(pnl=pnl, reason=reason, entry_time=t['entry_time'], symbol=t['symbol'],
                          direction=t['direction']))

    st = stats_for(rows)
    gq, tq = quarterly_stability(rows)
    conc = concentration(rows)
    print(f"\n{label}: n={st['n']}  win_rate={st['win_rate']:.1f}%  PF={st['pf']:.2f}  "
          f"total_pnl={st['total_pnl']:+.1f}%  additive_ann={st['additive_ann']:+.1f}%/yr  "
          f"quarters_PF>1={gq}/{tq}  top3_pct={conc:.1f}%")
    print(pd.DataFrame(rows).groupby('symbol')['pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                            total='sum').to_string())
    print(pd.DataFrame(rows).groupby('direction')['pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                               total='sum').to_string())
    return rows, st


def main():
    print("Re-simulating v3 (fixed) at TP=4.0xATR (2:1, as shipped)...")
    rows_21, st_21 = run_scenario(4.0, "A. V3 at 2:1 (TP=4.0, as shipped)")

    print("\nRe-simulating v3 (fixed) at TP=3.0xATR (1.5:1, accepted candidate)...")
    rows_15, st_15 = run_scenario(3.0, "\nB. V3 at 1.5:1 (TP=3.0)")


if __name__ == "__main__":
    main()
