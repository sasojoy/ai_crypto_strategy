"""
DEV-WINDOW ONLY (< 2026-01-01) exploratory test of the user's hypothesis:
does the locked RSI(14) momentum-continuation + volume-tercile spec work
BETTER on meme coins / smaller-cap alts than the current 5-symbol universe
(BTC/ETH/SOL/NEAR/AVAX)? A fresh, standalone test on 4 NEW symbols never
used anywhere else in this research line, picked a priori for a mix of
"pure meme" and "smaller-cap alt" with enough history to be worth testing:
  - DOGE/USDT   -- longest-history meme coin (Binance futures since 2020-07)
  - 1000SHIB/USDT:USDT -- second-longest meme coin (since 2021-05)
  - 1000PEPE/USDT:USDT -- newer but very high-volume/high-hype meme coin (since 2023-05)
  - INJ/USDT    -- smaller-cap non-meme altcoin, not a meme play (since 2022-08)
These do NOT have the original 5 symbols' full 2020-2025 cached history --
each is backtested over whatever history Binance actually has for it, up to
the SAME DEV_CUTOFF as everywhere else in this project (2026-01-01, so the
2026+ holdout window stays untouched even for a brand-new symbol set).
Sample sizes and periods are consequently NOT uniform across symbols --
reported per-symbol, not just pooled, so that isn't hidden.

Uses the EXACT SAME mechanics as the locked spec (dev_volume_confirm.py's
RSI(14)/ATR(14)/find_triggers, dev_momentum_continuation.py's flip(),
SL=2xATR/TP=4xATR/168-bar max hold/8-bar cooldown/0.14% friction/2% risk),
and the same corrected PER-SYMBOL, TRIGGER-POPULATION top-tercile volume
cutoff -- i.e. each of these 4 symbols is screened against its OWN top
third of triggers, not benchmarked against the original 5's cutoffs.

Fetches live from Binance via ccxt (these symbols aren't in
data/backtest_cache/) and caches locally under data/backtest_cache/ so
repeat runs don't re-download.

Not part of the deployed app; safe to delete after use. This is purely
exploratory -- a promising result here would need its own holdout-style
discipline before being taken seriously, same as anything else in this
research line.
"""
import os
import sys

import ccxt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    compute_atr, compute_rsi, find_triggers,
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip

DEV_CUTOFF = pd.Timestamp('2026-01-01')
CANDIDATES = ['DOGE/USDT', '1000SHIB/USDT:USDT', '1000PEPE/USDT:USDT', 'INJ/USDT']
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def cache_path(symbol):
    safe = symbol.replace('/', '_').replace(':', '_')
    return os.path.join(CACHE_DIR, f"{safe}_1h_extended.csv")


def fetch_and_cache(symbol):
    path = cache_path(symbol)
    if os.path.exists(path):
        return pd.read_csv(path, parse_dates=['timestamp'])

    since = exchange.parse8601('2019-01-01T00:00:00Z')
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
        if pd.to_datetime(since, unit='ms') >= DEV_CUTOFF:
            break
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    df = df[df['timestamp'] < DEV_CUTOFF].reset_index(drop=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_csv(path, index=False)
    return df


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


def build_candidates_for_symbol(symbol):
    df = fetch_and_cache(symbol)
    df['rsi'] = compute_rsi(df['close'])
    df['atr'] = compute_atr(df)
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma20']

    raw = []
    for i, reversion_direction in find_triggers(df):
        if np.isnan(df['vol_ratio'].iloc[i]):
            continue
        raw.append({'idx': i, 'direction': flip(reversion_direction),
                    'entry_time': df['timestamp'].iloc[i], 'vol_ratio': df['vol_ratio'].iloc[i]})
    cand = pd.DataFrame(raw)
    if cand.empty:
        return cand, df
    cutoff = cand['vol_ratio'].quantile(2 / 3)
    cand = cand[cand['vol_ratio'] >= cutoff].reset_index(drop=True)
    return cand, df


def summarize(df, label):
    if df.empty:
        print(f"{label}: 0 trades")
        return None
    n = len(df)
    wr = (df['equity_pnl_pct'] > 0).mean() * 100
    gross_win = df.loc[df['equity_pnl_pct'] > 0, 'equity_pnl_pct'].sum()
    gross_loss = -df.loc[df['equity_pnl_pct'] <= 0, 'equity_pnl_pct'].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
    total = df['equity_pnl_pct'].sum()
    print(f"{label}: n={n}  win_rate={wr:.1f}%  PF={pf:.2f}  total(linear)={total:+.1f}%")
    print("  exit reasons: " + ", ".join(
        f"{r}={c} ({c/n*100:.1f}%)" for r, c in df['reason'].value_counts().items()))
    return {'n': n, 'win_rate': wr, 'pf': pf, 'total': total}


def main():
    all_rows = []
    for symbol in CANDIDATES:
        print(f"\n{'='*70}\n{symbol}\n{'='*70}")
        cand, df = build_candidates_for_symbol(symbol)
        if cand.empty:
            print("  no valid triggers")
            continue
        first_bar, last_bar = df['timestamp'].iloc[0], df['timestamp'].iloc[-1]
        years = (last_bar - first_bar).days / 365.25
        print(f"  data range: {first_bar.date()} -> {last_bar.date()} ({years:.2f} years)")
        print(f"  candidates (top-tercile-of-own-triggers): {len(cand)}")

        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        rows = []
        for row in cand.itertuples():
            out = simulate_trade(close, high, low, atr, row.idx, row.direction)
            if out is None:
                continue
            out['direction'] = row.direction
            out['entry_time'] = row.entry_time
            rows.append(out)
        sym_df = pd.DataFrame(rows)
        stats = summarize(sym_df, f"  {symbol}")
        if stats:
            stats['annualized'] = stats['total'] / years
            print(f"  annualized(linear)={stats['annualized']:+.1f}%/yr")
            sym_df['symbol'] = symbol
            all_rows.append(sym_df)

    print(f"\n{'='*70}\nCOMBINED (all 4 new symbols pooled -- periods differ, informational only)\n{'='*70}")
    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        summarize(combined, "COMBINED")
        print("\nFor reference, the original 5-symbol universe (BTC/ETH/SOL/NEAR/AVAX) scored:")
        print("  n=1755  win_rate=40.6%  PF=1.22  annualized(linear)=+82.3%/yr  (scripts/dev_momentum_v4_wider_stop.py baseline)")


if __name__ == "__main__":
    main()
