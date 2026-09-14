"""
DEV-WINDOW ONLY (< 2026-01-01) test of a second attempt at the "improve
performance in choppy markets" idea, after dev_momentum_adx_trend_filter.py's
binary ADX>=25 gate turned out to be a net negative (per-trade quality did
improve, but cutting 46.3% of signals shrank annualized return far more
than the quality gain made up for -- see RESEARCH_FINDINGS.md "ADX 趨勢／
盤整濾網"). That test's own writeup suggested the more promising next step:
scale POSITION SIZE down in chop instead of skipping the trade outright, so
trade count doesn't collapse.

Mechanism (decided BEFORE running this script, no grid search): same
per-trade continuous-risk-scaling approach as
dev_momentum_vol_scaled_risk.py (already validated and deployed as
momentum_monitor_v5.py), but scaling on ADX(14) trend strength instead of
volume ratio. The existing top-tercile volume screen is COMPLETELY
UNCHANGED -- every trade that qualifies today still qualifies, none are
skipped. risk_pct = linear interpolation of ADX between two FIXED anchors:
ADX=15 (weak/choppy, textbook "no trend") -> risk 1%, ADX=35 (textbook
"strong trend") -> risk 3%, clamped outside that range. These anchors are
standard textbook trend-strength bands, not tuned on this dataset -- this
is the ONLY parameterization tested, same discipline as every other test
in this line.

Per this project's established discipline: dev window only (2020-2025),
does NOT touch the 2026+ holdout window. Reuses the SAME locked-spec
building blocks (dev_volume_confirm.py's RSI/ATR/find_triggers,
dev_momentum_continuation.py's flip(), dev_momentum_adx_trend_filter.py's
compute_adx()) UNCHANGED, and the corrected PER-SYMBOL, TRIGGER-POPULATION
top-tercile volume cutoff. Tested in ISOLATION from momentum_monitor_v5.py's
already-deployed vol-ratio risk scaling -- not combined, to keep clean
attribution (same reasoning v3's docstring gives for not combining with
v2's pyramid add-on).

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
from dev_momentum_adx_trend_filter import compute_adx

DEV_CUTOFF = pd.Timestamp('2026-01-01')
DEV_START = pd.Timestamp('2020-01-01')
BASE_RISK_PER_TRADE = 0.02  # baseline, fixed
MIN_RISK, MAX_RISK = 0.01, 0.03
ADX_LOW, ADX_HIGH = 15, 35  # textbook weak-trend / strong-trend anchors, not tuned


def adx_scaled_risk(adx_value):
    if np.isnan(adx_value):
        return (MIN_RISK + MAX_RISK) / 2
    rank = (adx_value - ADX_LOW) / (ADX_HIGH - ADX_LOW)
    rank = max(0.0, min(1.0, rank))
    return MIN_RISK + rank * (MAX_RISK - MIN_RISK)


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
        df['adx'] = compute_adx(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        frames[s] = df
        for i, reversion_direction in find_triggers(df):
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            raw.append({'symbol': s, 'idx': i, 'direction': flip(reversion_direction),
                        'entry_time': df['timestamp'].iloc[i], 'vol_ratio': df['vol_ratio'].iloc[i],
                        'adx': df['adx'].iloc[i]})
    cand = pd.DataFrame(raw)
    cand['vol_tercile'] = cand.groupby('symbol')['vol_ratio'].transform(
        lambda x: pd.qcut(x, 3, labels=['low', 'mid', 'high']))
    cand = cand[cand['vol_tercile'] == 'high'].copy()
    # Percentile rank of ADX WITHIN each symbol's top-tercile-qualifying subset (0=weakest
    # trend among qualifying trades, 1=strongest) -- guarantees avg risk == exactly 2%,
    # same fairness property as momentum_monitor_v5.py's vol_ratio ranking. Computed
    # separately from the fixed-anchor version above so both can be compared.
    cand['adx_rank'] = cand.groupby('symbol')['adx'].rank(pct=True)
    cand = cand.sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def run_scenario(candidates, frames, mode):
    rows = []
    for row in candidates.itertuples():
        if mode == 'baseline':
            risk_frac = BASE_RISK_PER_TRADE
        elif mode == 'fixed_anchor':
            risk_frac = adx_scaled_risk(row.adx)
        else:  # 'rank'
            risk_frac = MIN_RISK + row.adx_rank * (MAX_RISK - MIN_RISK)
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

    baseline = run_scenario(candidates, frames, mode='baseline')
    summarize(baseline, "BASELINE (fixed 2% risk)", years)

    fixed_anchor = run_scenario(candidates, frames, mode='fixed_anchor')
    summarize(fixed_anchor, f"ADX-SCALED, FIXED ANCHORS (ADX{ADX_LOW}->1%, ADX{ADX_HIGH}->3%)", years)

    ranked = run_scenario(candidates, frames, mode='rank')
    summarize(ranked, "ADX-SCALED, PERCENTILE RANK (avg risk forced to exactly 2%)", years)
    print()

    print("By symbol (rank-based ADX-scaled):")
    print(ranked.groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
    print()
    print("By direction (rank-based ADX-scaled):")
    print(ranked.groupby('direction')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
