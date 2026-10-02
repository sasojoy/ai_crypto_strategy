"""
Scale-in on confirmation (2026-10-02, follow-up to dev_next_bar_reversal.py).
Bar i = trigger (entry at its close); bar i+1 = confirmation bar.
"Flag" = bar i+1 closes against the trade AND its volume < bar i's volume.

  A  current      1 unit at close i
  B  scale-in     0.5 unit at close i; at close i+1, if the trade is still
                  open and NOT flagged, add 0.5 unit at close i+1
  C  confirm-only 0 at close i; at close i+1, if still open and NOT
                  flagged, 1 unit at close i+1
All units share the ORIGINAL stop and target (signal price -2 / +4 ATR).
"Unit" = the quantity whose stop-loss risk at the signal price is 1R, so
risk actually deployed is reported and results are compared PER UNIT OF
AVERAGE RISK (total R / mean risk), plus as raw totals.
Pass: B beats A on total R per unit of risk in all 4 cells (2020-23 /
2024-25 x 15-coin / 35-coin).
v7 locked spec, 1H close-entry proxy, 168h hold, 0.14% friction per leg.
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
from dev_next_bar_reversal import walk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')


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
            p1 = c[i]
            dist1 = 2 * a[i]                      # price distance to the stop at the signal price = 1R per unit
            sl, tp = p1 - sgn * dist1, p1 + sgn * 4 * a[i]
            end, j = i + 1 + MAX_HOLD, i + 1
            leg = lambda entry, px: (sgn * (px - entry) - ROUND_TRIP_FRICTION * entry) / dist1  # R per unit
            hit_sl = (l[j] <= sl) if sgn > 0 else (h[j] >= sl)
            hit_tp = (h[j] >= tp) if sgn > 0 else (l[j] <= tp)
            if hit_sl or hit_tp:                  # decided inside bar i+1: no add possible
                px = sl if hit_sl else tp
                A, B, C = leg(p1, px), 0.5 * leg(p1, px), 0.0
                riskA, riskB, riskC = 1.0, 0.5, 0.0
            else:
                flag = ((c[j] < o[j]) if sgn > 0 else (c[j] > o[j])) and v[j] < v[i]
                px = walk(c, h, l, j + 1, end, sgn, sl, tp)
                A = leg(p1, px)
                add_risk = abs(c[j] - sl) / dist1  # stop risk of one unit bought at close i+1
                if flag:
                    B, riskB, C, riskC = 0.5 * leg(p1, px), 0.5, 0.0, 0.0
                else:
                    B = 0.5 * leg(p1, px) + 0.5 * leg(c[j], px)
                    riskB = 0.5 + 0.5 * add_risk
                    C, riskC = leg(c[j], px), add_risk
                riskA = 1.0
            rows.append(dict(coin=b, sample='15' if b in basket else '35', time=pd.Timestamp(ts[i]),
                             A=A, B=B, C=C, riskA=riskA, riskB=riskB, riskC=riskC))
    d = pd.DataFrame(rows).sort_values('time')
    d['period'] = np.where(d.time < SPLIT, '2020-23', '2024-25')

    def mdd(x):
        eq = np.cumsum(x)
        return (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()

    print('Per cell: totalR | mean risk per signal | totalR per unit of mean risk | maxDD per unit of mean risk')
    passed = True
    for (p, s), g in d.groupby(['period', 'sample']):
        cells = []
        eff = {}
        for k in 'ABC':
            r, rk = g[k].values, g['risk' + k].mean()
            eff[k] = r.sum() / rk
            cells.append(f"{k}: {r.sum():+7.1f}R risk {rk:.2f} -> {eff[k]:+7.1f} (DD {mdd(r) / rk:5.1f})")
        ok = eff['B'] > eff['A']
        passed &= ok
        print(f"  {p} {s}-coin  " + ' | '.join(cells) + f"  {'B>A' if ok else 'x'}")
    for k in 'ABC':
        print(f"  ALL {k}: totalR {d[k].sum():+.1f}, mean risk {d['risk' + k].mean():.2f}, per unit risk {d[k].sum() / d['risk' + k].mean():+.1f}")
    coins_better = (d.groupby('coin').apply(lambda g: g.B.sum() / g.riskB.mean() > g.A.sum() / g.riskA.mean())).mean() * 100
    print(f"  coins where B beats A per unit of risk: {coins_better:.0f}%")
    print(f"\n  SCALE-IN (B) {'PASSES' if passed else 'FAILS'} (beats A per unit of risk in all 4 cells)")


if __name__ == '__main__':
    main()
