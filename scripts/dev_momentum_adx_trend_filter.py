"""
DEV-WINDOW ONLY (< 2026-01-01) test of a trend/chop regime filter on top of
the locked RSI(14) momentum-continuation spec, motivated by the user's
suspicion that the strategy does badly in choppy/ranging markets. Plausible
given what's already known: a large share of SL-hit trades had already
moved favorably before reversing (dev_momentum_v4_lock_profit.py's
exploration), a classic whipsaw/chop signature -- momentum-continuation
bets assume a breakout continues, but in a genuine range a "breakout" is
usually a fakeout that snaps back.

Filter: standard Wilder ADX(14), computed on the SAME 1H bars, using the
SAME Wilder smoothing convention (alpha=1/14) this codebase already uses
for RSI. Require ADX(14) >= 25 at the trigger bar to take the trade --
25 is Wilder's own textbook "trending" threshold, not something tuned on
this dataset. Decided and written into this script BEFORE running it, and
this is the ONLY threshold tested -- no grid, no "try 20 and 30 too and
keep whichever looks better," to avoid exactly the kind of after-the-fact
parameter picking this research line has consistently guarded against.

Applied on top of the SAME per-symbol, trigger-population top-tercile
volume cutoff as the locked spec (dev_momentum_continuation.py) -- ADX is
an ADDITIONAL gate, not a replacement for the volume filter.

Per this project's established discipline: dev window only (2020-2025),
does NOT touch the 2026+ holdout window. Reuses the SAME locked-spec
building blocks (dev_volume_confirm.py's RSI/find_triggers,
dev_momentum_continuation.py's flip()) UNCHANGED.

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
ADX_PERIOD = 14
ADX_TREND_THRESHOLD = 25  # Wilder's own textbook "trending" cutoff -- not tuned on this data


def compute_adx(df, period=ADX_PERIOD):
    high, low, close = df['high'], df['low'], df['close']
    prev_high, prev_low, prev_close = high.shift(1), low.shift(1), close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)

    alpha = 1 / period
    tr_s = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()

    plus_di = 100 * plus_dm_s / tr_s
    minus_di = 100 * minus_dm_s / tr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=alpha, adjust=False).mean()


def simulate_trade(close, high, low, atr, i, direction):
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
    eq_pnl = (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0
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
    cand = cand[cand['vol_tercile'] == 'high'].sort_values('entry_time').reset_index(drop=True)
    return cand, frames


def run_scenario(candidates, frames, require_trend):
    rows = []
    for row in candidates.itertuples():
        if require_trend and (np.isnan(row.adx) or row.adx < ADX_TREND_THRESHOLD):
            continue
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction)
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
    print(f"{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.1f}%  "
          f"annualized(linear)={total/years:+.1f}%/yr  top3_trade_pct_of_profit={top3_pct:.1f}%  "
          f"quarters_PF>1={q_pf_pass}/{len(q_pf)}  symbols_net_positive={n_symbols_positive}/5")
    print("  exit reasons: " + ", ".join(
        f"{r}={c} ({c/n*100:.1f}%)" for r, c in df['reason'].value_counts().items()))


def main():
    print("Building dev-window (2020-2025) high-vol-tercile momentum-continuation candidates...")
    candidates, frames = build_candidates()
    print(f"Total candidates (before ADX filter): {len(candidates)}\n")
    years = (DEV_CUTOFF - DEV_START).days / 365.25

    baseline = run_scenario(candidates, frames, require_trend=False)
    summarize(baseline, "BASELINE (no ADX filter)", years)
    print()

    filtered = run_scenario(candidates, frames, require_trend=True)
    n_removed = len(candidates) - len(filtered) if not filtered.empty else len(candidates)
    print(f"ADX>=25 filter removes {n_removed}/{len(candidates)} candidates "
          f"({n_removed/len(candidates)*100:.1f}%) as 'choppy'\n")
    summarize(filtered, f"ADX>={ADX_TREND_THRESHOLD} FILTER APPLIED", years)
    print()

    if not filtered.empty:
        print("By symbol (ADX-filtered):")
        print(filtered.groupby('symbol')['equity_pnl_pct'].agg(
            n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
        print()
        print("By direction (ADX-filtered):")
        print(filtered.groupby('direction')['equity_pnl_pct'].agg(
            n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
