"""
DEV-WINDOW ONLY (< 2026-01-01). Partial take-profit for the v7 signal
(optimization track, 2026-09-30; goal: higher win rate / smaller losses).

Take a fraction f of the position off at a first target T1, run the rest to
the normal 4xATR target. Grid fixed before running:
  T1 in {1, 2, 3} x ATR  (0.5R / 1R / 1.5R)
  f  in {1/3, 1/2}
  remainder stop: 'orig' (stays at -2xATR) or 'be' (moved to entry once T1
                  fills -- note the full breakeven stop already failed
                  badly for this signal; here only the remainder is exposed)
Plus references: market spec (SL 2 / TP 4 ATR) and v8's full exit at 3xATR.

Basket: 15 liquid coins; v7 locked spec, 1H close trigger; 0.14% friction
on the whole position; results in R of the full position (1R = 1% equity
at 1% risk). 1H conservatism: a bar touching both the stop and a target is
a stop. On the bar where T1 fills, a final-target touch counts (price must
pass T1 first), a breakeven-stop touch counts as a stop (order unknown).

Judged on: total R and max drawdown (in R, trades in time order) in
2020-23 and 2024-25, win rate, and coins improved.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi, ROUND_TRIP_FRICTION
from dev_coin_personality import ORIGINAL, MAJORS, load
from dev_momentum_pullback_entry import signals, MAX_HOLD

SPLIT = pd.Timestamp('2024-01-01')
VARIANTS = [(t1, f, rs) for t1 in (1.0, 2.0, 3.0) for f in (1 / 3, 1 / 2) for rs in ('orig', 'be')]


def first_hit(c, h, l, start, end, sgn, sl, tp):
    """Returns (bar, 'SL'|'TP') of the first touch from `start`, or (None, None)."""
    for j in range(start, end):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            return j, 'SL'
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            return j, 'TP'
    return None, None


def simulate(c, h, l, i, sgn, a, t1=None, f=0.0, rs='orig', tp_mult=4.0):
    entry = c[i]
    risk = 2 * a / entry
    end = min(i + 1 + MAX_HOLD, len(c))
    sl, tp = entry - sgn * 2 * a, entry + sgn * tp_mult * a
    ret = lambda px: sgn * (px - entry) / entry
    if t1 is None:
        j, why = first_hit(c, h, l, i + 1, end, sgn, sl, tp)
        px = sl if why == 'SL' else tp if why == 'TP' else c[end - 1]
        return (ret(px) - ROUND_TRIP_FRICTION) / risk
    p1 = entry + sgn * t1 * a
    j, why = first_hit(c, h, l, i + 1, end, sgn, sl, p1)
    if why is None:
        return (ret(c[end - 1]) - ROUND_TRIP_FRICTION) / risk
    if why == 'SL':
        return (ret(sl) - ROUND_TRIP_FRICTION) / risk
    part1 = f * ret(p1)
    sl2 = entry if rs == 'be' else sl
    # On the T1 bar itself: price must pass T1 before the final target, so a
    # final-target touch there is a certain fill. A breakeven-stop touch on
    # that bar has unknown order -> counted as a stop (conservative).
    if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
        return (part1 + (1 - f) * ret(tp) - ROUND_TRIP_FRICTION) / risk
    if rs == 'be' and ((l[j] <= sl2) if sgn > 0 else (h[j] >= sl2)):
        return (part1 + (1 - f) * ret(sl2) - ROUND_TRIP_FRICTION) / risk
    j2, why2 = first_hit(c, h, l, j + 1, end, sgn, sl2, tp)
    px2 = sl2 if why2 == 'SL' else tp if why2 == 'TP' else c[end - 1]
    return (part1 + (1 - f) * ret(px2) - ROUND_TRIP_FRICTION) / risk


def max_dd(r):
    eq = np.cumsum(r)
    return (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()


def main():
    rows = []
    for b in ORIGINAL + MAJORS:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        for s in signals(df).itertuples():
            rec = dict(coin=b, time=pd.Timestamp(ts[s.i]),
                       spec=simulate(c, h, l, s.i, s.sgn, atr[s.i]),
                       v8_tp3=simulate(c, h, l, s.i, s.sgn, atr[s.i], tp_mult=3.0))
            for t1, f, rs in VARIANTS:
                rec[f'T1={t1:.0f}ATR f={f:.2f} {rs}'] = simulate(c, h, l, s.i, s.sgn, atr[s.i], t1, f, rs)
            rows.append(rec)
    d = pd.DataFrame(rows).sort_values('time').reset_index(drop=True)
    d['period'] = np.where(d.time < SPLIT, 'disc', 'conf')

    cols = ['spec', 'v8_tp3'] + [f'T1={t1:.0f}ATR f={f:.2f} {rs}' for t1, f, rs in VARIANTS]
    print('=' * 125 + '\nPARTIAL TAKE-PROFIT, 15-coin basket (R of full position; maxDD in R, trades in time order)')
    print(f"{'variant':24s} | {'2020-23 totR':>12} {'win%':>6} {'maxDD':>6} {'ret/DD':>6} | {'2024-25 totR':>12} {'win%':>6} {'maxDD':>6} {'ret/DD':>6} | coins better")
    for col in cols:
        cells = []
        for p in ('disc', 'conf'):
            x = d.loc[d.period == p, col].values
            dd = max_dd(x)
            cells.append(f"{x.sum():+12.1f} {(x > 0).mean()*100:6.1f} {dd:6.1f} {x.sum()/dd:6.2f}")
        better = '-' if col == 'spec' else f"{(d.groupby('coin')[col].sum() > d.groupby('coin')['spec'].sum()).sum()}/15"
        print(f"{col:24s} | {cells[0]} | {cells[1]} | {better}")
    print(f"\n  signals: {len(d)} (2020-23 {int((d.period == 'disc').sum())}, 2024-25 {int((d.period == 'conf').sum())})")


if __name__ == '__main__':
    main()
