"""
DEV-WINDOW ONLY (< 2026-01-01). Tests combining the user-accepted 1.5:1
reward:risk candidate (SL=2.0xATR/TP=3.0xATR, dev_momentum_tighter_tp.py,
2026-09-19) with v6's ADX-scaled risk sizing -- two orthogonal levers
(exit distance vs per-trade risk%) that have never been tested together,
mirroring the same isolate-one-variable-then-combine pattern that already
worked for dev_momentum_v3_plus_v6.py.

Reuses the EXACT same trigger population as dev_momentum_tighter_tp.py
(dev_momentum_v4_wider_stop.py's high-vol-tercile classic population,
n=1755) and its SL=2.0xATR/TP=3.0xATR mechanics unchanged. Only the risk
sizing varies:
  A. 1.5:1 ALONE: flat 2% (BASE_RISK_PER_TRADE).
  B. 1.5:1 + V6: risk scales 1%-3% by each trigger's ADX(14) PERCENTILE
     RANK within its own symbol's top-tercile-qualifying population -- the
     identical "rank" formula momentum_monitor_v6.py itself uses.

Win_rate is identical between A and B by construction (risk% scaling never
flips a trade's sign, only its magnitude) -- PF and total P&L are the
meaningful comparison.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import ROUND_TRIP_FRICTION, MAX_HOLD_BARS
from dev_momentum_tighter_tp import build_candidates, SL_MULT
from dev_momentum_adx_trend_filter import compute_adx

TP_MULT = 3.0  # the accepted 1.5:1 candidate
MIN_RISK, MAX_RISK = 0.01, 0.03


def simulate_trade_with_adx(close, high, low, atr, adx, i, direction):
    entry_price = close[i]
    n = len(close)
    end = min(i + 1 + MAX_HOLD_BARS, n)
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None

    if direction == 'long':
        sl_price = entry_price - SL_MULT * atr[i]
        tp_price = entry_price + TP_MULT * atr[i]
    else:
        sl_price = entry_price + SL_MULT * atr[i]
        tp_price = entry_price - TP_MULT * atr[i]

    exit_price, reason = None, None
    for j in range(i + 1, end):
        if direction == 'long':
            if low[j] <= sl_price:
                exit_price, reason = sl_price, 'SL'
                break
            if high[j] >= tp_price:
                exit_price, reason = tp_price, 'TP'
                break
        else:
            if high[j] >= sl_price:
                exit_price, reason = sl_price, 'SL'
                break
            if low[j] <= tp_price:
                exit_price, reason = tp_price, 'TP'
                break
    if exit_price is None:
        exit_idx = end - 1
        if exit_idx <= i:
            return None
        exit_price, reason = close[exit_idx], 'TIMEOUT'

    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = SL_MULT * atr[i] / entry_price
    return {'reason': reason, 'raw_pnl': pnl, 'sl_dist_pct': sl_dist_pct, 'adx': adx[i]}


def quarterly_stability(df, pnl_col):
    d = df.copy()
    d['q'] = pd.to_datetime(d['entry_time']).dt.to_period('Q')
    good, total = 0, 0
    for q, g in d.groupby('q'):
        total += 1
        gw = g[g[pnl_col] > 0][pnl_col].sum()
        gl = -g[g[pnl_col] <= 0][pnl_col].sum()
        pf = gw / gl if gl > 0 else float('inf')
        if pf > 1.0:
            good += 1
    return good, total


def concentration(df, pnl_col, top_n=3):
    total = df[pnl_col].sum()
    if total <= 0:
        return float('nan')
    top = df.nlargest(top_n, pnl_col)[pnl_col].sum()
    return top / total * 100


def summarize(df, pnl_col, label, years):
    n = len(df)
    wr = (df[pnl_col] > 0).mean() * 100
    gw = df[df[pnl_col] > 0][pnl_col].sum()
    gl = -df[df[pnl_col] <= 0][pnl_col].sum()
    pf = gw / gl if gl > 0 else float('inf')
    total = df[pnl_col].sum()
    gq, tq = quarterly_stability(df, pnl_col)
    conc = concentration(df, pnl_col)
    print(f"{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.1f}%  "
          f"annualized(linear)={total/years:+.1f}%/yr  quarters_PF>1={gq}/{tq}  "
          f"top3_pct_of_profit={conc:.1f}%")


def main():
    print("Building candidates (same high-vol-tercile population as dev_momentum_tighter_tp.py)...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}\n")

    for s, df in frames.items():
        df['adx'] = compute_adx(df)

    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr, adx = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['adx'].values
        out = simulate_trade_with_adx(close, high, low, atr, adx, row.idx, row.direction)
        if out is None:
            continue
        out['symbol'] = row.symbol
        out['direction'] = row.direction
        out['entry_time'] = row.entry_time
        rows.append(out)
    trades = pd.DataFrame(rows)
    print(f"Trades with valid outcome: {len(trades)}\n")

    trades['adx_rank'] = trades.groupby('symbol')['adx'].rank(pct=True)
    trades['flat_pnl'] = (trades['raw_pnl'] / trades['sl_dist_pct']) * 0.02 * 100
    trades['risk_frac'] = MIN_RISK + trades['adx_rank'] * (MAX_RISK - MIN_RISK)
    trades['scaled_pnl'] = (trades['raw_pnl'] / trades['sl_dist_pct']) * trades['risk_frac'] * 100

    from dev_momentum_tighter_tp import DEV_CUTOFF, DEV_START
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    print(f"{'='*78}\nA. 1.5:1 ALONE (flat 2% risk)\n{'='*78}")
    summarize(trades, 'flat_pnl', '  ', years)
    print(f"  avg_risk={0.02*100:.2f}%")

    print(f"\n{'='*78}\nB. 1.5:1 + V6 (ADX rank-scaled risk 1%-3%)\n{'='*78}")
    summarize(trades, 'scaled_pnl', '  ', years)
    print(f"  avg_risk={trades['risk_frac'].mean()*100:.2f}%")

    print("\nBy symbol (A. flat):")
    print(trades.groupby('symbol')['flat_pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                     total='sum').to_string())
    print("\nBy symbol (B. ADX-scaled):")
    print(trades.groupby('symbol')['scaled_pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                       total='sum').to_string())
    print("\nBy direction (A. flat):")
    print(trades.groupby('direction')['flat_pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                        total='sum').to_string())
    print("\nBy direction (B. ADX-scaled):")
    print(trades.groupby('direction')['scaled_pnl'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100,
                                                          total='sum').to_string())


if __name__ == "__main__":
    main()
