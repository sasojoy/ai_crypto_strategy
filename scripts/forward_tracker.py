"""
FORWARD TRACKER for the v7 signal on 50 coins (pre-registered 2026-10-01,
see RESEARCH_FINDINGS.md). Answers one question with data nobody has seen
yet: does the v7 signal still have a positive edge?

Frozen rules (do not edit after the pre-registration commit):
  coins        15-coin basket + 35 universe coins (fetch_holdout_2026.coins)
  signal       RSI(14) cross of 30/70 on 1H closes, 8-bar cooldown,
               momentum direction, volume ratio (vs 20-bar mean) above the
               coin's FROZEN dev-window cutoff (forward_frozen_cutoffs.json)
  trade        enter at the trigger bar's close, SL 2 x ATR(14), TP 4 x ATR,
               max hold 168 bars, 0.14% round-trip friction, result in R
  start        signals whose bar opens at or after 2026-10-01 00:00 UTC
Decision rule:
  final verdict once >= 1500 CLOSED trades: edge confirmed if mean R > 0
  with one-sided t-test p < 0.05; otherwise not confirmed. Interim runs
  only report -- no early verdict.

Usage:
  python scripts/forward_tracker.py --freeze   (once: writes the cutoffs)
  python scripts/forward_tracker.py            (any time: fetch + report)
Data: data/forward/ (prices) ; results -> data/forward/forward_trades.csv
"""
import json
import os
import sys
import time

import ccxt
import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import find_triggers, ROUND_TRIP_FRICTION
from dev_momentum_continuation import flip
from dev_coin_personality import load
from fetch_holdout_2026 import coins
from holdout_short_crowding import prep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'forward')
CUTOFFS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'forward_frozen_cutoffs.json')
START = pd.Timestamp('2026-10-01')
WARMUP = '2026-08-01T00:00:00Z'
MAX_HOLD = 168
FINAL_N = 1500


def freeze():
    cut = {}
    for b in coins():
        df = prep(load(b))
        vr = [df['vol_ratio'].iloc[i] for i, _ in find_triggers(df) if not np.isnan(df['vol_ratio'].iloc[i])]
        cut[b] = float(np.quantile(vr, 2 / 3))
    with open(CUTOFFS, 'w') as f:
        json.dump(cut, f, indent=1, sort_keys=True)
    print(f'froze {len(cut)} cutoffs -> {CUTOFFS}')


def fetch(ex, b):
    rows, since, now = [], ex.parse8601(WARMUP), ex.milliseconds()
    while since < now:
        batch = ex.fetch_ohlcv(f'{b}/USDT:USDT', '1h', since=since, limit=1500)
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + 1
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates('timestamp').sort_values('timestamp')
    df = df[df['timestamp'] < pd.Timestamp.now('UTC').tz_localize(None).floor('h')]  # drop the still-forming bar
    df.to_csv(os.path.join(OUT, f'{b}_USDT_1h.csv'), index=False)
    return df.reset_index(drop=True)


def walk(c, h, l, i, sgn, a):
    entry, n = c[i], len(c)
    sl, tp = entry - sgn * 2 * a, entry + sgn * 4 * a
    end = min(i + 1 + MAX_HOLD, n)
    for j in range(i + 1, end):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            return 'SL', (sgn * (sl - entry) / entry - ROUND_TRIP_FRICTION) / (2 * a / entry)
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            return 'TP', (sgn * (tp - entry) / entry - ROUND_TRIP_FRICTION) / (2 * a / entry)
    if i + 1 + MAX_HOLD <= n:
        return 'TIMEOUT', (sgn * (c[end - 1] - entry) / entry - ROUND_TRIP_FRICTION) / (2 * a / entry)
    return 'OPEN', np.nan


def report():
    with open(CUTOFFS) as f:
        cut = json.load(f)
    os.makedirs(OUT, exist_ok=True)
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    rows = []
    for b in coins():
        df = prep(fetch(ex, b))
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        for i, rev in find_triggers(df):
            t = pd.Timestamp(ts[i])
            if t < START or np.isnan(atr[i]) or not df['vol_ratio'].iloc[i] > cut[b]:
                continue
            sgn = 1 if flip(rev) == 'long' else -1
            status, r = walk(c, h, l, i, sgn, atr[i])
            rows.append(dict(coin=b, time=t, direction='long' if sgn > 0 else 'short', entry=c[i], status=status, r=r))
        time.sleep(0.1)
    d = pd.DataFrame(rows, columns=['coin', 'time', 'direction', 'entry', 'status', 'r'])
    d.to_csv(os.path.join(OUT, 'forward_trades.csv'), index=False)

    closed = d[d.status != 'OPEN']
    print(f"forward window: {START.date()} .. now   signals {len(d)}   closed {len(closed)}   open {int((d.status == 'OPEN').sum())}")
    if len(closed) >= 2:
        p = ttest_1samp(closed.r, 0, alternative='greater').pvalue
        print(f"  closed: win {(closed.r > 0).mean()*100:.1f}%   avgR {closed.r.mean():+.3f}   "
              f"sumR {closed.r.sum():+.1f}   one-sided p(mean>0) {p:.3f}")
        for side in ('long', 'short'):
            x = closed[closed.direction == side]
            if len(x):
                print(f"  {side:5s}: n {len(x):4d}  avgR {x.r.mean():+.3f}")
        m = closed.groupby(closed.time.dt.to_period('M')).r.agg(['size', 'mean']).round(3)
        print('  by month:\n' + m.to_string())
        if len(closed) >= FINAL_N:
            print(f"\n  FINAL VERDICT (n >= {FINAL_N}): edge {'CONFIRMED' if p < 0.05 and closed.r.mean() > 0 else 'NOT CONFIRMED'}")
        else:
            print(f"\n  interim only: {len(closed)}/{FINAL_N} closed trades toward the final verdict")


if __name__ == '__main__':
    freeze() if '--freeze' in sys.argv else report()
