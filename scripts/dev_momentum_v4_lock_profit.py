"""
DEV-WINDOW ONLY (< 2026-01-01) backtest of a NEW, never-tested profit-
locking mechanism for the locked RSI(14) momentum-continuation spec: move
the stop-loss to BREAKEVEN (entry price) once the trade has moved at least
ARM_ATR x its own entry ATR in its favor.

Motivated by an earlier back-of-envelope exploration (not committed, done
live with the user) of the locked spec's actual trade population: exit
reasons split ~63% SL / ~36% TP / ~0.5% TIMEOUT, i.e. TP is itself a hard
cap at 4xATR and almost nothing reaches the 7-day timeout -- so the
strategy's edge is a fixed ~2:1 SL:TP payoff at a sub-50% win rate, NOT
unbounded "let a few winners run forever" tail gains. That rough pass also
found 53.7% of SL-hit trades had already moved >=1xATR favorably before
reversing -- i.e. roughly half of all losses are give-backs of an
already-profitable move, a population a breakeven stop could rescue. But
that estimate only touched already-losing trades and ignored the whipsaw
cost of also touching trades headed for TP, so it very likely overstated
the benefit -- this script fixes that by walking EVERY trade uniformly.

Tested across a small ARM_ATR grid (0.5/1.0/1.5) since the right trigger
distance isn't obvious a priori.

Per this project's established discipline: dev window only (2020-2025),
does NOT touch the 2026+ holdout window (already spent once on the
no-this-mechanism locked spec; spending it again on a brand-new untested
mechanism needs its own explicit decision, not an automatic side effect of
a good dev-window number). Reuses the SAME locked-spec building blocks
(dev_volume_confirm.py's RSI/ATR/find_triggers, dev_momentum_continuation.py's
flip()) UNCHANGED, and the corrected PER-SYMBOL, TRIGGER-POPULATION top-
tercile volume cutoff (dev_momentum_continuation.py's actual methodology --
NOT the rougher all-bars quantile the earlier back-of-envelope pass used).

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
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
DEV_START = pd.Timestamp('2020-01-01')
ARM_ATR_GRID = [0.5, 1.0, 1.5]


def simulate_trade(close, high, low, atr, i, direction, arm_atr):
    """Bar-by-bar 1H walk with a breakeven stop armed once the trade has
    moved >= arm_atr x its own ATR in its favor (arm_atr=None reproduces
    the baseline -- no breakeven mechanism -- exactly, same as
    dev_volume_confirm.trade_outcome). Risk sizing is always keyed to the
    ORIGINAL stop distance, never the moved one -- position size is fixed
    at entry, before it's known whether the stop will ever move."""
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

    armed = False
    exit_price, reason = None, None
    for j in range(i + 1, end):
        if direction == 'long':
            if not armed and arm_atr is not None and (high[j] - entry_price) / atr[i] >= arm_atr:
                sl_price = max(sl_price, entry_price)
                armed = True
            if low[j] <= sl_price:
                exit_price, reason = sl_price, ('BE' if armed else 'SL')
                break
            if high[j] >= tp_price:
                exit_price, reason = tp_price, 'TP'
                break
        else:
            if not armed and arm_atr is not None and (entry_price - low[j]) / atr[i] >= arm_atr:
                sl_price = min(sl_price, entry_price)
                armed = True
            if high[j] >= sl_price:
                exit_price, reason = sl_price, ('BE' if armed else 'SL')
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
    orig_sl_dist_pct = SL_ATR_MULT * atr[i] / entry_price
    eq_pnl = (pnl / orig_sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if orig_sl_dist_pct > 0 else 0.0
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
    # PER-SYMBOL top tercile, computed on the TRIGGER population itself -- matches
    # dev_momentum_continuation.py's actual (corrected) methodology exactly, not the
    # rougher all-bars quantile the earlier back-of-envelope pass used.
    cand['vol_tercile'] = cand.groupby('symbol')['vol_ratio'].transform(
        lambda x: pd.qcut(x, 3, labels=['low', 'mid', 'high']))
    cand = cand[cand['vol_tercile'] == 'high'].sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def run_scenario(candidates, frames, arm_atr):
    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction, arm_atr)
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
        return None
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gross_win = df.loc[df['equity_pnl_pct'] > 0, 'equity_pnl_pct'].sum()
    gross_loss = -df.loc[df['equity_pnl_pct'] <= 0, 'equity_pnl_pct'].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
    total = df['equity_pnl_pct'].sum()
    top3_pct = df.nlargest(3, 'equity_pnl_pct')['equity_pnl_pct'].sum() / total * 100 if total > 0 else float('nan')
    df = df.copy()
    df['quarter'] = pd.to_datetime(df['entry_time']).dt.to_period('Q')
    q_pf = df.groupby('quarter')['equity_pnl_pct'].apply(
        lambda x: (x[x > 0].sum() / -x[x <= 0].sum()) if (x <= 0).any() and -x[x <= 0].sum() > 0 else float('inf'))
    q_pf_pass = (q_pf > 1.0).sum()
    print(f"{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.1f}%  "
          f"annualized(linear)={total/years:+.1f}%/yr  top3_trade_pct_of_profit={top3_pct:.1f}%  "
          f"quarters_PF>1={q_pf_pass}/{len(q_pf)}")
    return {'n': n, 'win_rate': wr, 'pf': pf, 'total': total, 'annualized': total / years}


def main():
    print("Building dev-window (2020-2025) high-vol-tercile momentum-continuation candidates...")
    candidates, frames = build_candidates()
    print(f"Total candidates: {len(candidates)}\n")
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    print(f"{'='*78}\nBASELINE -- no breakeven mechanism (should match dev_momentum_continuation.py)\n{'='*78}")
    baseline = run_scenario(candidates, frames, arm_atr=None)
    summarize(baseline, "BASELINE", years)
    print("\nExit reason breakdown (baseline):")
    print(baseline.groupby('reason')['equity_pnl_pct'].agg(['count', 'mean', 'sum']).to_string())

    print(f"\n{'='*78}\nARM_ATR GRID -- breakeven stop armed once trade moves >= X ATR favorably\n{'='*78}")
    results = {}
    for arm_atr in ARM_ATR_GRID:
        scenario = run_scenario(candidates, frames, arm_atr=arm_atr)
        results[arm_atr] = scenario
        summarize(scenario, f"ARM_ATR={arm_atr}", years)

    best_arm = max(ARM_ATR_GRID, key=lambda a: results[a]['equity_pnl_pct'].sum())
    best = results[best_arm]
    print(f"\n{'='*78}\nDETAIL for best-performing ARM_ATR={best_arm}\n{'='*78}")
    print("\nExit reason breakdown:")
    print(best.groupby('reason')['equity_pnl_pct'].agg(['count', 'mean', 'sum']).to_string())
    print(f"\nHow many trades that WOULD have hit TP under baseline got diverted to BE instead?")
    merged = baseline[['entry_time', 'symbol', 'reason']].rename(columns={'reason': 'baseline_reason'}).merge(
        best[['entry_time', 'symbol', 'reason']].rename(columns={'reason': 'be_reason'}),
        on=['entry_time', 'symbol'])
    diverted_from_tp = ((merged['baseline_reason'] == 'TP') & (merged['be_reason'] == 'BE')).sum()
    n_tp_baseline = (merged['baseline_reason'] == 'TP').sum()
    print(f"  {diverted_from_tp} of {n_tp_baseline} baseline TP-winners got stopped at breakeven instead "
          f"({diverted_from_tp/n_tp_baseline*100:.1f}%) -- this is the whipsaw cost the earlier rough estimate missed.")

    print(f"\nBy symbol:")
    print(best.groupby('symbol')['equity_pnl_pct'].agg(['count', 'sum', 'mean']).to_string())
    print(f"\nBy direction:")
    print(best.groupby('direction')['equity_pnl_pct'].agg(['count', 'sum', 'mean']).to_string())
    print(f"\nBy year:")
    best_y = best.copy()
    best_y['year'] = pd.to_datetime(best_y['entry_time']).dt.year
    print(best_y.groupby('year')['equity_pnl_pct'].agg(['count', 'sum', 'mean']).to_string())


if __name__ == "__main__":
    main()
