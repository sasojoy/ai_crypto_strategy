"""
BRK4H -- frozen rules (pre-registered, RESEARCH_FINDINGS.md commit d339daf),
identical to the 'control' arm of prereg_squeeze_breakout.py:
  4H bars; close above the previous 20-bar high (long) / below the previous
  20-bar low (short); no new entry within 6 bars of the last one on that
  coin; stop = midpoint of the previous 20-bar range; target = 3R; max hold
  180 bars; 0.14% round-trip friction; result in R.

  python scripts/brk4h.py holdout   one-shot 2026 holdout check (50 coins)
  python scripts/brk4h.py forward   forward tracker from 2026-10-01
"""
import os
import sys
import time

import ccxt
import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, ROUND_TRIP_FRICTION
from dev_coin_personality import ORIGINAL, MAJORS
from fetch_holdout_2026 import coins
from forward_tracker import fetch, OUT as FWD_DIR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLD = os.path.join(ROOT, 'data', 'backtest_cache', 'holdout_2026')
MAX_HOLD = 180
COOLDOWN = 6
FORWARD_START = pd.Timestamp('2026-10-01')
FINAL_N = 5000


def to_4h(df1h):
    x = df1h.set_index('timestamp').resample('4h', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
    x['atr'] = compute_atr(x)
    x['hh20'] = x['high'].shift(1).rolling(20).max()
    x['ll20'] = x['low'].shift(1).rolling(20).min()
    return x


def walk(c, h, l, t, sgn, stop):
    """Returns (status, R). status OPEN when the trade is still running."""
    entry = c[t]
    risk = sgn * (entry - stop) / entry
    if risk <= 0:
        return None
    tp = entry + sgn * 3 * entry * risk
    end = min(t + 1 + MAX_HOLD, len(c))
    for j in range(t + 1, end):
        if (l[j] <= stop) if sgn > 0 else (h[j] >= stop):
            return 'SL', (sgn * (stop - entry) / entry - ROUND_TRIP_FRICTION) / risk
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            return 'TP', (sgn * (tp - entry) / entry - ROUND_TRIP_FRICTION) / risk
    if t + 1 + MAX_HOLD <= len(c):
        return 'TIMEOUT', (sgn * (c[end - 1] - entry) / entry - ROUND_TRIP_FRICTION) / risk
    return 'OPEN', np.nan


def signals(x, start):
    c, h, l, hh, ll, ts = (x[k].values for k in ('close', 'high', 'low', 'hh20', 'll20', 'timestamp'))
    out, last = [], -10**9
    for t in range(len(x)):
        if np.isnan(hh[t]):
            continue
        sgn = 1 if c[t] > hh[t] else (-1 if c[t] < ll[t] else 0)
        if sgn == 0 or t - last <= COOLDOWN:
            continue
        last = t
        if pd.Timestamp(ts[t]) < start:
            continue
        res = walk(c, h, l, t, sgn, (hh[t] + ll[t]) / 2)
        if res is not None:
            out.append((pd.Timestamp(ts[t]), sgn, *res))
    return out


def holdout():
    basket = ORIGINAL + MAJORS
    rows = []
    for b in coins():
        df = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
        for t, sgn, status, r in signals(to_4h(df), pd.Timestamp('2026-01-01')):
            if status != 'OPEN':
                rows.append(dict(coin=b, sample='15' if b in basket else '35', time=t, sgn=sgn, r=r))
    d = pd.DataFrame(rows)
    ok = True
    for s in ('15', '35'):
        x = d[d['sample'] == s].r
        ok &= x.mean() > 0
        print(f"  2026 holdout {s}-coin: n={len(x):5d} win={(x > 0).mean()*100:5.1f}% avgR={x.mean():+.3f} sumR={x.sum():+.1f}")
    print(f"  longs avgR {d[d.sgn == 1].r.mean():+.3f}   shorts avgR {d[d.sgn == -1].r.mean():+.3f}")
    print(d.groupby(d.time.dt.to_period('Q')).r.agg(['size', 'mean']).round(3).to_string())
    print(f"\n  BRK4H HOLDOUT {'PASSES' if ok else 'FAILS'}")


def forward():
    os.makedirs(FWD_DIR, exist_ok=True)
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    rows = []
    for b in coins():
        for t, sgn, status, r in signals(to_4h(fetch(ex, b)), FORWARD_START):
            rows.append(dict(coin=b, time=t, direction='long' if sgn > 0 else 'short', status=status, r=r))
        time.sleep(0.1)
    d = pd.DataFrame(rows, columns=['coin', 'time', 'direction', 'status', 'r'])
    d.to_csv(os.path.join(FWD_DIR, 'forward_trades_brk4h.csv'), index=False)
    closed = d[d.status != 'OPEN']
    print(f"BRK4H forward: signals {len(d)}  closed {len(closed)}  open {int((d.status == 'OPEN').sum())}")
    if len(closed) >= 2:
        p = ttest_1samp(closed.r, 0, alternative='greater').pvalue
        print(f"  closed: win {(closed.r > 0).mean()*100:.1f}%  avgR {closed.r.mean():+.3f}  sumR {closed.r.sum():+.1f}  p(mean>0) {p:.3f}")
        verdict = ('CONFIRMED' if closed.r.mean() > 0 and p < 0.05 else 'NOT CONFIRMED') if len(closed) >= FINAL_N \
            else f'interim {len(closed)}/{FINAL_N}'
        print(f"  {verdict}")


if __name__ == '__main__':
    {'holdout': holdout, 'forward': forward}[sys.argv[1]]()
