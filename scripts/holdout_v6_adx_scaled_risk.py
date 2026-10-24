"""
HOLDOUT VALIDATION (2026-01-01 onward) of momentum_monitor_v6.py's ADX-
scaled risk mechanism.

This is the SECOND time this project's one-shot holdout window has been
spent -- the first was the locked v1 spec itself ("第二十四次測試",
2026-09-08: n=214, win_rate 37.4%, PF 1.03, compounded +0.18%, beating a
500-seed random benchmark at the 83-84th percentile on all three metrics).
Spending it again on v6 is a DELIBERATE, EXPLICIT decision the user made
in this conversation (2026-09-14), not an automatic side effect of a good
dev-window number -- this project's stated discipline (RESEARCH_FINDINGS.md,
v3's docstring) is against burning the holdout on every new idea, and that
bar is satisfied here by the user's explicit request to do exactly this.

Methodology mirrors the original holdout_momentum_validation.py as closely
as possible from its documented description (RESEARCH_FINDINGS.md /
NEXT_STEPS.md) -- that script's file itself no longer exists locally (it
was never git-tracked, per this project's appendix of disposable dev
scripts), so this is a faithful reconstruction, not a rerun of literally
the same code:
  - RSI(14)/ATR(14)/vol_ratio/ADX(14) computed on a CONTINUOUS 2020-present
    1H series per symbol (data/backtest_cache/*_1h_full.csv topped up with
    fresh candles through now via ccxt), so warm-up and the 8-bar cooldown
    carry naturally across the dev/holdout boundary -- no artificial cold
    start at 2026-01-01.
  - Only triggers with entry_time >= 2026-01-01 count as the holdout
    population used for every stat below.
  - The volume top-tercile cutoff is recalculated FRESH, per symbol,
    WITHIN the holdout trigger population only -- same "percentile
    computed within that test's own population" principle used everywhere
    else in this research line, not reused from the dev window or from
    paper_trading/thresholds.json's live calibration.
  - v6-specific: the ADX p1/p99 risk-scaling anchors are ALSO calibrated
    fresh within the holdout's own top-tercile-qualifying population, NOT
    reused from thresholds.json (whose live calibration mixes dev + already
    -elapsed holdout data -- reusing it here would leak holdout data into
    its own calibration inputs).
  - Uses SEQUENTIAL COMPOUNDING (dev_volume_confirm.pooled_stats), matching
    the ORIGINAL holdout test's own convention (not the fixed-notional
    linear convention the newer v4/v5/v6 dev-window scripts use), so the
    baseline number here is directly comparable to the recorded
    "n=214, win_rate 37.4%, PF 1.03, compounded +0.18%" result as a sanity
    check that this reconstruction is faithful.
  - 500-seed random-benchmark percentile against the FULL unconditional
    holdout trigger pool (no volume filter), same as the original.

Reports THREE things:
  1. Sanity check: does the tercile-selected, flat-2%-risk baseline (i.e.
     "v1 run forward on the extended holdout") reproduce something close
     to the recorded 第24次測試 numbers?
  2. v6 vs that SAME baseline, on the SAME holdout trade population: does
     ADX-scaled risk sizing actually help out of sample, or was the dev-
     window finding a fluke?
  3. Both against the random benchmark, for context.

One-shot: not to be re-run with different parameters after seeing the
result. Not part of the deployed app.
"""
import os
import sys

import ccxt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    SYMBOLS, compute_atr, compute_rsi, find_triggers, pooled_stats, random_benchmark_for_subset,
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip
from dev_momentum_adx_trend_filter import compute_adx

HOLDOUT_CUTOFF = pd.Timestamp('2026-01-01')
MIN_RISK, MAX_RISK = 0.01, 0.03
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def load_1h_continuous(symbol):
    """Full 2020-present series: cached _1h_full.csv topped up with fresh
    candles through now via ccxt, so the holdout window runs all the way
    to today instead of stopping wherever the cache was last refreshed."""
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1h_full.csv')
    df = pd.read_csv(path, parse_dates=['timestamp'])
    last_cached = df['timestamp'].iloc[-1]
    since = exchange.parse8601((last_cached + pd.Timedelta(hours=1)).isoformat())
    fresh_rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
        if not batch:
            break
        fresh_rows.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
    if fresh_rows:
        fresh = pd.DataFrame(fresh_rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        fresh['timestamp'] = pd.to_datetime(fresh['timestamp'], unit='ms')
        df = pd.concat([df, fresh], ignore_index=True)
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    now = pd.Timestamp.now('UTC').tz_localize(None)
    df = df[df['timestamp'] + pd.Timedelta(hours=1) <= now].reset_index(drop=True)
    return df


def simulate_trade(close, high, low, atr, i, direction):
    """Returns raw (pre-risk-scaling) trade outcome: reason, raw pnl %,
    and the SL-distance % needed to convert into equity terms at any
    chosen risk fraction. Requires the FULL 7-day max-hold window to
    already be available in the data -- unlike the dev-window scripts
    (which never need to look past a fixed historical cutoff), this
    holdout script walks all the way to "now", so a trade triggered in
    the last 7 days would otherwise get its lookback window silently
    truncated at today and get mislabeled as a premature TIMEOUT exit
    instead of being excluded as "outcome not yet knowable"."""
    entry_price = close[i]
    n = len(close)
    end = i + 1 + MAX_HOLD_BARS
    if end > n or np.isnan(atr[i]) or atr[i] <= 0:
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
        raw_pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        raw_pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = SL_ATR_MULT * atr[i] / entry_price
    return {'reason': reason, 'raw_pnl': raw_pnl, 'sl_dist_pct': sl_dist_pct}


def main():
    frames = {}
    all_triggers_holdout = []   # UNCONDITIONAL (no volume filter) -- for the random benchmark pool
    tercile_candidates = []     # after per-symbol, within-holdout-population tercile filter

    print("Loading continuous 2020-present 1H data (topping up cache with fresh candles)...")
    per_symbol_holdout_triggers = {}
    for s in SYMBOLS:
        df = load_1h_continuous(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['adx'] = compute_adx(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']
        frames[s] = df
        print(f"  {s}: data through {df['timestamp'].iloc[-1]}")

        holdout_rows = []
        for i, reversion_direction in find_triggers(df):
            ts = df['timestamp'].iloc[i]
            if ts < HOLDOUT_CUTOFF:
                continue
            if np.isnan(df['vol_ratio'].iloc[i]):
                continue
            holdout_rows.append({
                'symbol': s, 'idx': i, 'direction': flip(reversion_direction),
                'entry_time': ts, 'vol_ratio': df['vol_ratio'].iloc[i], 'adx': df['adx'].iloc[i],
            })
        per_symbol_holdout_triggers[s] = pd.DataFrame(holdout_rows)
        all_triggers_holdout.append(per_symbol_holdout_triggers[s])

    full_holdout_pool = pd.concat(all_triggers_holdout, ignore_index=True)
    print(f"\nTotal unconditional holdout triggers (all symbols, no volume filter): {len(full_holdout_pool)}")

    # Per-symbol top-tercile cutoff computed FRESH within the holdout trigger population only.
    for s in SYMBOLS:
        sub = per_symbol_holdout_triggers[s]
        if sub.empty:
            continue
        cutoff = sub['vol_ratio'].quantile(2 / 3)
        qualifying = sub[sub['vol_ratio'] >= cutoff].copy()
        qualifying['adx_rank'] = qualifying['adx'].rank(pct=True)
        tercile_candidates.append(qualifying)

    candidates = pd.concat(tercile_candidates, ignore_index=True) if tercile_candidates else pd.DataFrame()
    print(f"Holdout candidates after per-symbol top-tercile filter: {len(candidates)}\n")

    # Simulate every candidate once, get raw outcome (reason/raw_pnl/sl_dist_pct); derive both
    # baseline (flat 2%) and v6 (ADX rank-scaled) equity from the SAME underlying trade.
    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction)
        if out is None:
            continue
        out['symbol'] = row.symbol
        out['entry_time'] = row.entry_time
        out['timestamp'] = row.entry_time
        out['adx_rank'] = row.adx_rank
        rows.append(out)
    trades = pd.DataFrame(rows)

    baseline_df = trades.copy()
    baseline_df['equity_pnl_pct'] = (baseline_df['raw_pnl'] / baseline_df['sl_dist_pct']) * BASE_RISK_PER_TRADE * 100

    v6_df = trades.copy()
    risk_frac = MIN_RISK + v6_df['adx_rank'] * (MAX_RISK - MIN_RISK)
    v6_df['equity_pnl_pct'] = (v6_df['raw_pnl'] / v6_df['sl_dist_pct']) * risk_frac * 100

    # Random benchmark: 500 draws of the same size from the FULL unconditional holdout pool,
    # scored at flat 2% risk (matching the tercile-vs-random question, independent of ADX scaling).
    full_pool_scored = full_holdout_pool.copy()
    full_pool_frames_rows = []
    for row in full_pool_scored.itertuples():
        df = frames[row.symbol]
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out = simulate_trade(close, high, low, atr, row.idx, row.direction)
        if out is None:
            continue
        out['timestamp'] = row.entry_time
        out['equity_pnl_pct'] = (out['raw_pnl'] / out['sl_dist_pct']) * BASE_RISK_PER_TRADE * 100 if out['sl_dist_pct'] > 0 else 0.0
        full_pool_frames_rows.append(out)
    full_pool_df = pd.DataFrame(full_pool_frames_rows)

    print(f"{'='*78}\n1. SANITY CHECK: tercile + flat-2% baseline vs recorded 第24次測試 numbers\n{'='*78}")
    st_baseline = pooled_stats(baseline_df)
    print(f"  This run: n={st_baseline['n']}  win_rate={st_baseline['win_rate']:.1f}%  "
          f"PF={st_baseline['pf']:.2f}  compounded={st_baseline['compounded']:+.2f}%")
    print(f"  Recorded (2026-09-08, shorter holdout window): n=214  win_rate=37.4%  PF=1.03  compounded=+0.18%")

    bench = random_benchmark_for_subset(full_pool_df, st_baseline['n'])
    if bench:
        bench_df = pd.DataFrame(bench)
        pct_compounded = (bench_df['compounded'] < st_baseline['compounded']).mean() * 100
        pct_pf = (bench_df['pf'] < st_baseline['pf']).mean() * 100
        pct_wr = (bench_df['win_rate'] < st_baseline['win_rate']).mean() * 100
        print(f"  vs 500-seed random benchmark: compounded beats {pct_compounded:.1f}%, "
              f"PF beats {pct_pf:.1f}%, win_rate beats {pct_wr:.1f}%")

    print(f"\n{'='*78}\n2. v6 (ADX-scaled risk) vs the SAME baseline, on the SAME holdout trades\n{'='*78}")
    st_v6 = pooled_stats(v6_df)
    print(f"  BASELINE (flat 2%):     n={st_baseline['n']}  win_rate={st_baseline['win_rate']:.1f}%  "
          f"PF={st_baseline['pf']:.2f}  compounded={st_baseline['compounded']:+.2f}%")
    print(f"  V6 (ADX-scaled 1%-3%):  n={st_v6['n']}  win_rate={st_v6['win_rate']:.1f}%  "
          f"PF={st_v6['pf']:.2f}  compounded={st_v6['compounded']:+.2f}%")
    print(f"  avg risk -- baseline: {BASE_RISK_PER_TRADE*100:.2f}%  v6: {risk_frac.mean()*100:.2f}%")

    print(f"\nBy symbol (v6):")
    print(v6_df.groupby('symbol')['equity_pnl_pct'].agg(
        n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
