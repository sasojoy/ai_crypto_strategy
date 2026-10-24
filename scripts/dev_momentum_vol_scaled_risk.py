"""
DEV-WINDOW ONLY (< 2026-01-01) test of the user's idea: instead of a fixed
2% risk on every trade that clears the top-tercile volume filter, scale
risk WITH volume-ratio strength -- a barely-qualifying trade (right at the
tercile cutoff) risks less, a trade with an extreme volume ratio risks
more. Motivated by an already-established finding in this research line
(dev_momentum_continuation.py's Spearman test): volume ratio at the
trigger positively correlates with trade P&L for this continuation setup,
so "how much conviction does the volume give this specific trade" is a
real, previously-validated signal -- this only asks whether ACTING on that
gradient (not just using it as a binary gate) helps.

Mechanism (decided BEFORE running this script, no grid search):
  - The existing top-tercile screen is UNCHANGED -- this does not admit
    any trade that wouldn't already qualify today.
  - Within each symbol's top-tercile-qualifying triggers, rank each
    trade's vol_ratio as a percentile (0 = right at the tercile cutoff,
    1 = that symbol's single highest vol_ratio trigger).
  - risk_pct = MIN_RISK + rank * (MAX_RISK - MIN_RISK), MIN_RISK=1%,
    MAX_RISK=3%. The midpoint of a uniform rank distribution is 0.5, so
    the AVERAGE risk across all trades is still ~2% -- this reallocates
    risk toward higher-conviction trades rather than changing how much
    total risk the system takes on average, keeping the comparison to the
    fixed-2% baseline fair (not a stealth leverage increase).

Per this project's established discipline: dev window only (2020-2025),
does NOT touch the 2026+ holdout window. Reuses the SAME locked-spec
building blocks (dev_volume_confirm.py's RSI/ATR/find_triggers,
dev_momentum_continuation.py's flip()) UNCHANGED, and the corrected
PER-SYMBOL, TRIGGER-POPULATION top-tercile volume cutoff.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    SYMBOLS, load_1h, compute_atr, compute_rsi, find_triggers,
    SL_ATR_MULT, TP_ATR_MULT, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
DEV_START = pd.Timestamp('2020-01-01')
BASE_RISK_PER_TRADE = 0.02  # baseline, fixed
MIN_RISK = 0.01   # vol-scaled: risk at the tercile cutoff (weakest qualifying trade)
MAX_RISK = 0.03   # vol-scaled: risk at the single strongest trade per symbol


def simulate_trade(close, high, low, atr, i, direction, risk_frac):
    entry_price = close[i]
    n = len(close)
    end = min(i + 1 + MAX_HOLD_BARS, n)
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None
    if direction == 'long':
        sl_price = entry_price - SL_ATR_MULT * atr[i]
        tp_price = entry_price + TP_ATR_MULT * atr[i]
    else:
        sl_price = entry_price + SL_ATR_MULT * atr[i]
        tp_price = entry_price - TP_ATR_MULT * atr[i]

    for j in range(i + 1, end):
        if direction == 'long':
            if low[j] <= sl_price:
                exit_price, reason = sl_price, 'SL'; break
            if high[j] >= tp_price:
                exit_price, reason = tp_price, 'TP'; break
        else:
            if high[j] >= sl_price:
                exit_price, reason = sl_price, 'SL'; break
            if low[j] <= tp_price:
                exit_price, reason = tp_price, 'TP'; break
    else:
        exit_idx = end - 1
        if exit_idx <= i:
            return None
        exit_price, reason = close[exit_idx], 'TIMEOUT'

    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = SL_ATR_MULT * atr[i] / entry_price
    eq_pnl = (pnl / sl_dist_pct) * risk_frac * 100 if sl_dist_pct > 0 else 0.0
    return {'reason': reason, 'equity_pnl_pct': eq_pnl}


def build_candidates():
    raw = []
    frames = {}
    for s in SYMBOLS:
        df = load_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        frames[s] = df
        for i, reversion_direction in find_triggers(df):
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            raw.append({'symbol': s, 'idx': i, 'direction': flip(reversion_direction),
                        'entry_time': df['timestamp'].iloc[i], 'vol_ratio': df['vol_ratio'].iloc[i]})
    cand = pd.DataFrame(raw)
    cand['vol_tercile'] = cand.groupby('symbol')['vol_ratio'].transform(
        lambda x: pd.qcut(x, 3, labels=['low', 'mid', 'high']))
    cand = cand[cand['vol_tercile'] == 'high'].copy()
    # Percentile rank of vol_ratio WITHIN each symbol's top-tercile-qualifying subset only
    # (0 = at the cutoff, 1 = that symbol's strongest trigger) -- not against all triggers.
    cand['vol_rank'] = cand.groupby('symbol')['vol_ratio'].rank(pct=True)
    cand = cand.sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def run_scenario(candidates, frames, scaled):
    rows = []
    for row in candidates.itertuples():
        risk_frac = (MIN_RISK + row.vol_rank * (MAX_RISK - MIN_RISK)) if scaled else BASE_RISK_PER_TRADE
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction, risk_frac)
        if out is None:
            continue
        out['symbol'] = row.symbol
        out['direction'] = row.direction
        out['entry_time'] = row.entry_time
        out['risk_frac'] = risk_frac
        rows.append(out)
    return pd.DataFrame(rows)


def summarize(df, label, years):
    if df.empty:
        print(f"{label}: 0 trades")
        return
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gross_win = df.loc[df['equity_pnl_pct'] > 0, 'equity_pnl_pct'].sum()
    gross_loss = -df.loc[df['equity_pnl_pct'] <= 0, 'equity_pnl_pct'].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
    total = df['equity_pnl_pct'].sum()
    top3_pct = df.nlargest(3, 'equity_pnl_pct')['equity_pnl_pct'].sum() / total * 100 if total > 0 else float('nan')
    dfq = df.copy()
    dfq['quarter'] = pd.to_datetime(dfq['entry_time']).dt.to_period('Q')
    q_pf = dfq.groupby('quarter')['equity_pnl_pct'].apply(
        lambda x: (x[x > 0].sum() / -x[x <= 0].sum()) if (x <= 0).any() and -x[x <= 0].sum() > 0 else float('inf'))
    q_pf_pass = (q_pf > 1.0).sum()
    n_symbols_positive = (df.groupby('symbol')['equity_pnl_pct'].sum() > 0).sum()
    avg_risk = df['risk_frac'].mean() * 100 if 'risk_frac' in df else BASE_RISK_PER_TRADE * 100
    print(f"{label}: n={n}  avg_risk={avg_risk:.2f}%  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.1f}%  "
          f"annualized(linear)={total/years:+.1f}%/yr  top3_trade_pct_of_profit={top3_pct:.1f}%  "
          f"quarters_PF>1={q_pf_pass}/{len(q_pf)}  symbols_net_positive={n_symbols_positive}/5")


def main():
    print("Building dev-window (2020-2025) high-vol-tercile momentum-continuation candidates...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}\n")
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    baseline = run_scenario(candidates, frames, scaled=False)
    summarize(baseline, "BASELINE (fixed 2% risk)", years)

    scaled = run_scenario(candidates, frames, scaled=True)
    summarize(scaled, f"VOL-SCALED RISK ({MIN_RISK*100:.0f}%-{MAX_RISK*100:.0f}%, avg~2%)", years)
    print()

    print("By symbol (vol-scaled):")
    print(scaled.groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
    print()
    print("By direction (vol-scaled):")
    print(scaled.groupby('direction')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
