"""
HOLDOUT VALIDATION (2026-01-01 onward) of momentum_monitor_v3.py's real-time
ANTICIPATORY-ENTRY mechanism (touch-price solve + real-time volume
projection + post-close volume-confirmation checkpoint) -- NOT the
early-reject refinement tested in dev_momentum_v3_early_reject.py, which
was found dev-window-neutral and is not part of what's being validated here.

This is the THIRD time this project's one-shot holdout window has been
spent -- the first was the locked v1 spec itself ("第二十四次測試",
2026-09-08), the second was momentum_monitor_v6.py's ADX-scaled risk
(2026-09-14, scripts/holdout_v6_adx_scaled_risk.py). Spending it a third
time on v3 is a DELIBERATE, EXPLICIT decision the user made in this
conversation (2026-09-17) -- v3's own dev-window number (+387%/yr vs v1's
+79.79%/yr) was always flagged in its docstring as the single largest
never-holdout-validated claim in this research line, precisely because the
uplift comes mostly from ~3.5x more signals firing, which is exactly the
kind of result most vulnerable to dev-window overfitting.

Methodology mirrors holdout_v6_adx_scaled_risk.py:
  - RSI(14)/ATR(14)/Wilder avg_gain/avg_loss/vol_ratio (causal + non-causal)
    computed on a CONTINUOUS 2020-present 1H series per symbol (cached
    *_1h_full.csv topped up with fresh candles via ccxt), so warm-up and
    the 8-hour cooldown carry naturally across the dev/holdout boundary.
  - v3's entry mechanism needs 1-minute data too: cached *_1m_devwindow.csv
    (through 2025-12-31) topped up with fresh 1-minute candles via ccxt
    from 2026-01-01 through now.
  - Only entries with hour_start >= 2026-01-01 count as the holdout
    population. The hour-by-hour walk itself starts scanning from
    2025-12-01 (one month of margin, far more than the 8-hour cooldown
    needs) purely so cooldown state at the boundary is correct, not from
    2020 -- unlike the 1H-only RSI-cross checks in holdout_v6, walking
    every hour with 1-minute granularity across the full 2020-2025 dev
    window here would be redundant (already done in the dev-window script)
    and wastes time for zero effect on the holdout stats.
  - Both the causal AND non-causal top-tercile volume cutoffs are
    recalculated FRESH within the HOLDOUT's own RSI-cross trigger
    population only (not reused from the dev window or from
    paper_trading/thresholds.json, which mixes dev + already-elapsed
    holdout data).
  - A trade whose full 7-day max-hold window isn't yet available (entered
    within the last 7 days before "now") is EXCLUDED, not truncated and
    mislabeled TIMEOUT -- same discipline as holdout_v6.
  - Uses the same fixed-notional-equivalent risk-normalized pnl formula
    (leg_pnl_pct) as every other v1/v2/v3 dev/live script; totals are
    reported as a simple additive sum (not sequential compounding), for
    the same reason dev_momentum_v3_early_reject.py switched to it: v3
    fires 3-4x more overlapping trades than the classic spec, so
    compounding one account through them in entry-time order is not a
    meaningful number (BASELINE below still also reports sequential
    compounding for continuity with the original holdout convention, since
    its own trigger population does NOT overlap heavily).

Reports TWO things on the SAME holdout window:
  1. BASELINE: the classic locked-spec mechanism (wait for the 1H bar to
     close, RSI actually crosses on the closed bar, tercile volume filter)
     -- the "如果只用v1機制" reference point.
  2. V3: the anticipatory-entry population (touches trigger price intra-hour
     + real-time volume projection, confirmed post-close) on the SAME
     holdout window.

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
    SYMBOLS, compute_atr, compute_rsi, find_triggers, pooled_stats,
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

HOLDOUT_CUTOFF = pd.Timestamp('2026-01-01')
WALK_START = pd.Timestamp('2025-12-01')  # entry-detection walk starts here; only >=HOLDOUT_CUTOFF is counted
ALPHA = 1 / 14
MAX_HOLD_MINUTES = MAX_HOLD_BARS * 60
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def compute_rsi_state(close):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=ALPHA, adjust=False).mean()
    avg_loss = loss.ewm(alpha=ALPHA, adjust=False).mean()
    return avg_gain, avg_loss


def threshold_price(prev_close, avg_gain_prev, avg_loss_prev, target_rsi):
    a = ALPHA
    if target_rsi == 30:
        ag_new = avg_gain_prev * (1 - a)
        al_new = ag_new * 70 / 30
        loss = (al_new - avg_loss_prev * (1 - a)) / a
        return prev_close - loss
    elif target_rsi == 70:
        al_new = avg_loss_prev * (1 - a)
        ag_new = al_new * 70 / 30
        gain = (ag_new - avg_gain_prev * (1 - a)) / a
        return prev_close + gain
    raise ValueError(target_rsi)


def load_1h_continuous(symbol):
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
    return df[df['timestamp'] + pd.Timedelta(hours=1) <= now].reset_index(drop=True)


def load_1m_continuous(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1m_devwindow.csv')
    cached = pd.read_csv(path, parse_dates=['timestamp'])
    cached = cached[cached['timestamp'] >= WALK_START].reset_index(drop=True)
    last_cached = cached['timestamp'].max()
    since = exchange.parse8601((last_cached + pd.Timedelta(minutes=1)).isoformat())
    fresh_rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1m', since=since, limit=1000)
        if not batch:
            break
        fresh_rows.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
    if fresh_rows:
        fresh = pd.DataFrame(fresh_rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        fresh['timestamp'] = pd.to_datetime(fresh['timestamp'], unit='ms')
        df = pd.concat([cached, fresh], ignore_index=True)
    else:
        df = cached
    now = pd.Timestamp.now('UTC').tz_localize(None)
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    return df[df['timestamp'] <= now].reset_index(drop=True)


def leg_pnl_pct(direction, entry_price, exit_price, sl_price):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0


def prepare_symbol(symbol):
    """Loads continuous 1H+1m data and computes all indicator columns once."""
    df = load_1h_continuous(symbol)
    df['rsi'] = compute_rsi(df['close'])
    df['atr'] = compute_atr(df)
    ag, al = compute_rsi_state(df['close'])
    df['avg_gain'], df['avg_loss'] = ag, al
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma20']
    df['vol_ma20_causal'] = df['vol_ma20'].shift(1)
    df['vol_ratio_causal'] = df['volume'] / df['vol_ma20_causal']
    dfm = load_1m_continuous(symbol)
    return df, dfm


def holdout_cutoffs(df, symbol):
    triggers = find_triggers(df)
    rows = [(df['timestamp'].iloc[i], df['vol_ratio'].iloc[i], df['vol_ratio_causal'].iloc[i], flip(d))
            for i, d in triggers if df['timestamp'].iloc[i] >= HOLDOUT_CUTOFF]
    hdf = pd.DataFrame(rows, columns=['entry_time', 'vol_ratio', 'vol_ratio_causal', 'direction'])
    hdf = hdf.dropna()
    cutoff = float(hdf['vol_ratio'].quantile(2 / 3)) if len(hdf) else float('nan')
    cutoff_causal = float(hdf['vol_ratio_causal'].quantile(2 / 3)) if len(hdf) else float('nan')
    return cutoff, cutoff_causal, hdf


def classic_baseline_trades(df, hdf, cutoff):
    """v1-equivalent: closed-bar RSI cross, tercile volume filter (fresh
    holdout cutoff), SL=2xATR/TP=4xATR/168-bar hold, on the SAME holdout
    trigger population used to calibrate the cutoff above."""
    close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
    ts = df['timestamp'].values
    n = len(df)
    rows = []
    for row in hdf.itertuples():
        if row.vol_ratio < cutoff:
            continue
        i = int(np.searchsorted(ts, np.datetime64(row.entry_time)))
        if i >= n or np.isnan(atr[i]) or atr[i] <= 0:
            continue
        end = i + 1 + MAX_HOLD_BARS
        if end > n:
            continue  # outcome not yet knowable
        direction = row.direction
        entry_price = close[i]
        sl_price = entry_price - SL_ATR_MULT * atr[i] if direction == 'long' else entry_price + SL_ATR_MULT * atr[i]
        tp_price = entry_price + TP_ATR_MULT * atr[i] if direction == 'long' else entry_price - TP_ATR_MULT * atr[i]
        exit_price, reason = None, None
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
        if exit_price is None:
            exit_price, reason = close[end - 1], 'TIMEOUT'
        pnl = leg_pnl_pct(direction, entry_price, exit_price, sl_price)
        rows.append(dict(equity_pnl_pct=pnl, reason=reason, timestamp=row.entry_time))
    return pd.DataFrame(rows)


def v3_anticipatory_trades(df, dfm, cutoff, cutoff_causal):
    ts1h = df['timestamp'].values
    close1h, atr1h, agv, alv = df['close'].values, df['atr'].values, df['avg_gain'].values, df['avg_loss'].values
    vol_ma20_causal_1h, vol_ratio_1h = df['vol_ma20_causal'].values, df['vol_ratio'].values
    ts1m = dfm['timestamp'].values
    high1m, low1m, close1m, vol1m = dfm['high'].values, dfm['low'].values, dfm['close'].values, dfm['volume'].values
    n1m = len(ts1m)

    start_idx = int(np.searchsorted(ts1h, np.datetime64(WALK_START)))
    start_idx = max(start_idx, 30)
    trades = []
    last_entry_time = None
    for H in range(start_idx, len(df) - 1):
        if np.isnan(agv[H - 1]) or np.isnan(alv[H - 1]) or np.isnan(atr1h[H - 1]) or atr1h[H - 1] <= 0:
            continue
        vma = vol_ma20_causal_1h[H]
        if np.isnan(vma) or vma <= 0:
            continue
        hour_start = ts1h[H]
        if last_entry_time is not None and (hour_start - last_entry_time) < np.timedelta64(8, 'h'):
            continue
        hour_end = hour_start + np.timedelta64(1, 'h')
        i0 = np.searchsorted(ts1m, hour_start, side='left')
        i1 = np.searchsorted(ts1m, hour_end, side='left')
        if i1 - i0 < 1:
            continue

        thr_long = threshold_price(close1h[H - 1], agv[H - 1], alv[H - 1], 70)
        thr_short = threshold_price(close1h[H - 1], agv[H - 1], alv[H - 1], 30)

        vol_h, high_h, low_h = vol1m[i0:i1], high1m[i0:i1], low1m[i0:i1]
        cumvol = np.cumsum(vol_h)
        minutes = np.arange(1, len(vol_h) + 1)
        projected_ratio = cumvol * (60.0 / minutes) / vma
        long_touch = high_h >= thr_long
        short_touch = low_h <= thr_short
        vol_ok = projected_ratio >= cutoff_causal
        qualifying = np.where(long_touch, vol_ok, np.where(short_touch, vol_ok, False))
        if not qualifying.any():
            continue
        k_rel = int(np.argmax(qualifying))
        direction = 'long' if long_touch[k_rel] else 'short'
        entry_price = thr_long if direction == 'long' else thr_short
        entry_idx = i0 + k_rel
        atr_sizing = atr1h[H - 1]
        sl_price = entry_price - SL_ATR_MULT * atr_sizing if direction == 'long' else entry_price + SL_ATR_MULT * atr_sizing
        tp_price = entry_price + TP_ATR_MULT * atr_sizing if direction == 'long' else entry_price - TP_ATR_MULT * atr_sizing

        end_idx = min(entry_idx + MAX_HOLD_MINUTES, n1m)
        if end_idx < entry_idx + MAX_HOLD_MINUTES:
            last_entry_time = ts1m[entry_idx]
            continue  # outcome not yet knowable (too close to "now") -- excluded, not truncated
        fut_high, fut_low, fut_close = high1m[entry_idx:end_idx], low1m[entry_idx:end_idx], close1m[entry_idx:end_idx]
        if direction == 'long':
            sl_hit, tp_hit = fut_low <= sl_price, fut_high >= tp_price
        else:
            sl_hit, tp_hit = fut_high >= sl_price, fut_low <= tp_price
        first_sl = np.argmax(sl_hit) if sl_hit.any() else None
        first_tp = np.argmax(tp_hit) if tp_hit.any() else None
        if first_sl is None and first_tp is None:
            nat_rel, nat_reason = len(fut_close) - 1, 'TIMEOUT'
        elif first_tp is None or (first_sl is not None and first_sl <= first_tp):
            nat_rel, nat_reason = first_sl, 'SL'
        else:
            nat_rel, nat_reason = first_tp, 'TP'
        nat_idx = entry_idx + nat_rel
        nat_time = ts1m[nat_idx]
        nat_price = sl_price if nat_reason == 'SL' else tp_price if nat_reason == 'TP' else fut_close[nat_rel]

        confirmed = bool(vol_ratio_1h[H] >= cutoff) if not np.isnan(vol_ratio_1h[H]) else False
        hour_end_price = close1h[H]

        last_entry_time = ts1m[entry_idx]

        if hour_start < HOLDOUT_CUTOFF:
            continue  # walked for cooldown continuity only, not part of the counted holdout population

        if hour_end < nat_time and not confirmed:
            exit_time, exit_price, reason = hour_end, hour_end_price, 'VOL_UNCONFIRMED'
        else:
            exit_time, exit_price, reason = nat_time, nat_price, nat_reason
        pnl = leg_pnl_pct(direction, entry_price, exit_price, sl_price)
        trades.append(dict(equity_pnl_pct=pnl, reason=reason, timestamp=hour_start, symbol=None))
    return pd.DataFrame(trades)


def additive_stats(d):
    if d is None or d.empty:
        return None
    n = len(d)
    wr = (d['equity_pnl_pct'] > 0).mean() * 100
    gw = d[d['equity_pnl_pct'] > 0]['equity_pnl_pct'].sum()
    gl = -d[d['equity_pnl_pct'] <= 0]['equity_pnl_pct'].sum()
    pf = gw / gl if gl > 0 else float('inf')
    return dict(n=n, win_rate=wr, pf=pf, total_pnl=d['equity_pnl_pct'].sum(),
                reasons=d['reason'].value_counts().to_dict())


def main():
    print("Loading continuous 2020-present 1H + 1-minute (from 2025-12-01) data, topped up via ccxt...")
    baseline_all, v3_all = [], []
    for s in SYMBOLS:
        df, dfm = prepare_symbol(s)
        print(f"  {s}: 1H data through {df['timestamp'].iloc[-1]}, 1m data through {dfm['timestamp'].iloc[-1]}")
        cutoff, cutoff_causal, hdf = holdout_cutoffs(df, s)
        print(f"    holdout-calibrated cutoff={cutoff:.3f} causal_cutoff={cutoff_causal:.3f} (n_triggers={len(hdf)})")

        base_trades = classic_baseline_trades(df, hdf, cutoff)
        base_trades['symbol'] = s
        baseline_all.append(base_trades)

        v3_trades = v3_anticipatory_trades(df, dfm, cutoff, cutoff_causal)
        v3_trades['symbol'] = s
        v3_all.append(v3_trades)
        print(f"    baseline (classic, closed-bar) entries: {len(base_trades)} | "
              f"v3 (anticipatory) entries: {len(v3_trades)}")

    baseline_df = pd.concat(baseline_all, ignore_index=True)
    v3_df = pd.concat(v3_all, ignore_index=True)

    print(f"\n{'='*78}\n1. BASELINE: classic locked-spec (wait for hour close), holdout window\n{'='*78}")
    st_base_pooled = pooled_stats(baseline_df.rename(columns={'timestamp': 'timestamp'}))
    print(f"  Sequential-compounding convention (comparable to prior holdout runs):")
    print(f"    n={st_base_pooled['n']} win_rate={st_base_pooled['win_rate']:.1f}% PF={st_base_pooled['pf']:.2f} "
          f"compounded={st_base_pooled['compounded']:+.2f}%")
    st_base_add = additive_stats(baseline_df)
    print(f"  Additive convention: total_pnl={st_base_add['total_pnl']:+.2f}%  reasons={st_base_add['reasons']}")

    print(f"\n{'='*78}\n2. V3: anticipatory-entry mechanism, SAME holdout window\n{'='*78}")
    st_v3_add = additive_stats(v3_df)
    print(f"  n={st_v3_add['n']} win_rate={st_v3_add['win_rate']:.1f}% PF={st_v3_add['pf']:.2f} "
          f"total_pnl={st_v3_add['total_pnl']:+.2f}%  reasons={st_v3_add['reasons']}")

    print(f"\nBy symbol (v3):")
    print(v3_df.groupby('symbol')['equity_pnl_pct'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())
    print(f"\nBy symbol (baseline):")
    print(baseline_df.groupby('symbol')['equity_pnl_pct'].agg(n='count', win_rate=lambda x: (x > 0).mean() * 100, total='sum').to_string())


if __name__ == "__main__":
    main()
