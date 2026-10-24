"""
User observation (2026-10-02): after a v7 momentum entry, if the NEXT hour
is a reversal candle with SMALLER volume, the trade mostly goes into a
pullback or a real reversal. Tested exactly as stated:

  condition at the close of bar i+1 (i = trigger bar, entry at its close):
    reversal  = bar i+1 closes against the trade (long: close < open;
                short: close > open)
    weaker    = volume of bar i+1 < volume of bar i (the entry bar)
  only trades still open at that close (stop/target not touched in i+1)

Two questions, both periods (2020-23 / 2024-25), both samples (15-coin
basket / 35 unseen coins):
  1. Is the observation true? win rate / final R of flagged vs other trades
  2. Is acting on it worth it? for flagged trades compare
       hold  : keep the original stop/target
       exit  : close at bar i+1's close
       tight : move the stop to bar i+1's extreme (long: its low) and keep
               the target
v7 locked spec, 1H close-entry proxy, SL 2 / TP 4 ATR, 168h, 0.14% costs.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')


def walk(c, h, l, start, end, sgn, sl, tp):
    for j in range(start, end):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            return sl
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            return tp
    return c[end - 1]


def main():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    rows = []
    for b in basket + others:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        o, c, h, l, v, a, ts = (df[k].values for k in ('open', 'close', 'high', 'low', 'volume', 'atr', 'timestamp'))
        for s in signals(df).itertuples():
            i, sgn = s.i, s.sgn
            entry, risk = c[i], 2 * a[i] / c[i]
            sl, tp = entry - sgn * 2 * a[i], entry + sgn * 4 * a[i]
            end = i + 1 + MAX_HOLD
            j = i + 1
            if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
                continue  # already stopped inside bar i+1
            if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
                continue  # already at target inside bar i+1
            R = lambda px: (sgn * (px - entry) / entry - ROUND_TRIP_FRICTION) / risk
            reversal = (c[j] < o[j]) if sgn > 0 else (c[j] > o[j])
            weaker = v[j] < v[i]
            hold = R(walk(c, h, l, j + 1, end, sgn, sl, tp))
            exit_now = R(c[j])
            tight_sl = l[j] if sgn > 0 else h[j]
            tight = R(walk(c, h, l, j + 1, end, sgn, tight_sl, tp))
            rows.append(dict(coin=b, sample='15' if b in basket else '35', time=pd.Timestamp(ts[i]),
                             flag=reversal and weaker, reversal=reversal, weaker=weaker,
                             hold=hold, exit=exit_now, tight=tight))
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, '2020-23', '2024-25')
    print(f"trades still open after the next bar: {len(d)}; flagged (reversal candle + smaller volume): "
          f"{int(d.flag.sum())} ({d.flag.mean()*100:.1f}%)\n")
    print('1. IS THE OBSERVATION TRUE?  final result if simply held')
    for (p, s), g in d.groupby(['period', 'sample']):
        f, o = g[g.flag], g[~g.flag]
        print(f"  {p} {s}-coin  flagged: n={len(f):4d} win={(f.hold > 0).mean()*100:5.1f}% avgR={f.hold.mean():+.3f}   "
              f"others: n={len(o):4d} win={(o.hold > 0).mean()*100:5.1f}% avgR={o.hold.mean():+.3f}")
    print('\n2. FOR FLAGGED TRADES: what to do at the close of the next bar (avgR)')
    for (p, s), g in d[d.flag].groupby(['period', 'sample']):
        print(f"  {p} {s}-coin  n={len(g):4d}  hold {g.hold.mean():+.3f}   exit now {g.exit.mean():+.3f}   "
              f"tighten stop to that bar's extreme {g.tight.mean():+.3f}")
    f = d[d.flag]
    print(f"  ALL           n={len(f):4d}  hold {f.hold.mean():+.3f}   exit now {f.exit.mean():+.3f}   tighten {f.tight.mean():+.3f}")
    print(f"\n  whole strategy total R: hold everything {d.hold.sum():+.1f} | exit flagged {d.hold.where(~d.flag, d.exit).sum():+.1f} "
          f"| tighten flagged {d.hold.where(~d.flag, d.tight).sum():+.1f}")


if __name__ == '__main__':
    main()
