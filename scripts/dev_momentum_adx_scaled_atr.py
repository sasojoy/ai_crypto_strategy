"""
DEV-WINDOW ONLY (< 2026-01-01) test of the user's ORIGINAL v6 idea, which
turned out to differ from what got built: scale the SL/TP ATR MULTIPLE
itself with ADX(14) trend strength, keeping risk sizing FIXED at 2% --
the opposite of what shipped as momentum_monitor_v6.py (which keeps
SL/TP fixed at v1's 2.0x/4.0xATR and scales the RISK FRACTION with ADX
instead). Both are legitimate, different mechanisms; this script tests
the one actually intended for "v6".

Mechanism (decided BEFORE running, no grid search): rather than inventing
new ATR multiples, interpolate between two ALREADY-VALIDATED shapes on
this exact trigger population -- v1's locked 2.0x/4.0xATR and v4's
already-tested-and-shipped wider 2.5x/5.0xATR (RESEARCH_FINDINGS.md "v4
探索") -- using the SAME percentile-rank-within-top-tercile method already
validated for v5 (vol_ratio) and v6 (ADX risk sizing), so avg exposure to
either shape is well-defined and not cherry-picked. Both possible
directions get tested, per explicit user request:
  A) TREND -> WIDER:   ADX rank 0 (weakest qualifying trend) -> 2.0/4.0,
                        ADX rank 1 (strongest) -> 2.5/5.0.
                        User's own hypothesis: give real trends room to
                        breathe (extends v4's finding), keep chop tight.
  B) TREND -> TIGHTER:  the reverse mapping, tested because the user asked
                        for both directions rather than just their hunch.
Risk sizing is a FIXED 2% of reference capital in both scenarios -- only
the stop/target distance varies per trade, not the bet size. Reward:risk
stays 1:2 throughout (TP is always exactly 2x the SL distance, whatever
that distance is for that trade).

Per this project's established discipline: dev window only (2020-2025),
does NOT touch the 2026+ holdout window. Reuses the SAME locked-spec
building blocks (dev_volume_confirm.py's RSI/ATR/find_triggers,
dev_momentum_continuation.py's flip(), dev_momentum_adx_trend_filter.py's
compute_adx()) UNCHANGED, and the corrected PER-SYMBOL, TRIGGER-POPULATION
top-tercile volume cutoff. Tested in ISOLATION from the deployed v6
(ADX-scaled risk) and v5 (vol-ratio-scaled risk) -- not combined.

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
    BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip
from dev_momentum_adx_trend_filter import compute_adx

DEV_CUTOFF = pd.Timestamp('2026-01-01')
DEV_START = pd.Timestamp('2020-01-01')

# The two already-validated shapes being interpolated between -- not new numbers.
NARROW_SL, NARROW_TP = 2.0, 4.0   # v1's locked spec
WIDE_SL, WIDE_TP = 2.5, 5.0       # v4's already-shipped wider variant


def simulate_trade(close, high, low, atr, i, direction, sl_mult, tp_mult):
    entry_price = close[i]
    n = len(close)
    end = min(i + 1 + MAX_HOLD_BARS, n)
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None
    if direction == 'long':
        sl_price = entry_price - sl_mult * atr[i]
        tp_price = entry_price + tp_mult * atr[i]
    else:
        sl_price = entry_price + sl_mult * atr[i]
        tp_price = entry_price - tp_mult * atr[i]

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
    sl_dist_pct = sl_mult * atr[i] / entry_price
    eq_pnl = (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0
    return {'reason': reason, 'equity_pnl_pct': eq_pnl, 'sl_mult': sl_mult, 'tp_mult': tp_mult}


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
    cand['adx_rank'] = cand.groupby('symbol')['adx'].rank(pct=True)
    cand = cand.sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def run_scenario(candidates, frames, mode):
    rows = []
    for row in candidates.itertuples():
        if mode == 'baseline':
            sl_mult, tp_mult = NARROW_SL, NARROW_TP
        elif mode == 'trend_wider':
            sl_mult = NARROW_SL + row.adx_rank * (WIDE_SL - NARROW_SL)
            tp_mult = NARROW_TP + row.adx_rank * (WIDE_TP - NARROW_TP)
        else:  # 'trend_tighter'
            sl_mult = WIDE_SL - row.adx_rank * (WIDE_SL - NARROW_SL)
            tp_mult = WIDE_TP - row.adx_rank * (WIDE_TP - NARROW_TP)
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction, sl_mult, tp_mult)
        if out is None:
            continue
        out['symbol'] = row.symbol
        out['direction'] = row.direction
        out['entry_time'] = row.entry_time
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
    avg_sl, avg_tp = df['sl_mult'].mean(), df['tp_mult'].mean()
    print(f"{label}: n={n}  avg_SL/TP={avg_sl:.2f}/{avg_tp:.2f}  win_rate={wr:.1f}%  PF={pf:.2f}  "
          f"total(linear)={total:+.1f}%  annualized(linear)={total/years:+.1f}%/yr  "
          f"top3_trade_pct_of_profit={top3_pct:.1f}%  quarters_PF>1={q_pf_pass}/{len(q_pf)}  "
          f"symbols_net_positive={n_symbols_positive}/5")
    print("  exit reasons: " + ", ".join(
        f"{r}={c} ({c/n*100:.1f}%)" for r, c in df['reason'].value_counts().items()))


def main():
    print("Building dev-window (2020-2025) high-vol-tercile momentum-continuation candidates...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}\n")
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    baseline = run_scenario(candidates, frames, 'baseline')
    summarize(baseline, "BASELINE (fixed 2.0/4.0, v1 as-is)", years)
    print()

    wider = run_scenario(candidates, frames, 'trend_wider')
    summarize(wider, "A) TREND->WIDER  (weak ADX->2.0/4.0, strong ADX->2.5/5.0)", years)
    print()

    tighter = run_scenario(candidates, frames, 'trend_tighter')
    summarize(tighter, "B) TREND->TIGHTER (strong ADX->2.0/4.0, weak ADX->2.5/5.0)", years)
    print()

    print("By symbol (A, trend->wider):")
    print(wider.groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
    print()
    print("By direction (A, trend->wider):")
    print(wider.groupby('direction')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
