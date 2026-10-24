"""
HOLDOUT TEST (pre-registered, RESEARCH_FINDINGS.md commit 02eb998). Run ONCE.
7-day cross-sectional momentum (XS7) on 2026 data, rules identical to the
7-day run of prereg_xs_momentum.py. Pass: annualized return > 0 and
Sharpe > 0 on all 50 coins AND on the 35 unseen coins.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_coin_personality import ORIGINAL, MAJORS
from fetch_holdout_2026 import coins
from prereg_xs_momentum import weekly_inputs, backtest, stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLD = os.path.join(ROOT, 'data', 'backtest_cache', 'holdout_2026')
START = pd.Timestamp('2026-01-01')


def main():
    closes, funding = {}, {}
    for b in coins():
        df = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
        daily = df.set_index('timestamp')['close'].resample('1D')
        full_days = df.groupby(df['timestamp'].dt.floor('D')).size()
        s = daily.last()
        closes[b] = s[full_days.reindex(s.index).fillna(0) == 24]  # only complete UTC days
        f = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_funding.csv'))
        f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
        funding[b] = f.set_index('timestamp')['funding_rate']
    px = pd.DataFrame(closes)
    weeks = [w for w in weekly_inputs(px, funding, 7) if w[0] >= START]
    others = [c for c in coins() if c not in ORIGINAL + MAJORS]
    momentum = lambda sc: list(sc.sort_values().index)
    ok = True
    for label, universe in (('50 coins', list(px.columns)), ('35 unseen coins', others)):
        r = backtest(weeks, universe, momentum)
        s = stats(r)
        ok &= s['ann'] > 0 and s['sharpe'] > 0
        print(f"  {label:16s} weeks={s['n']:2d} ({r.index.min().date()} .. {r.index.max().date()})  ann={s['ann']:+7.1f}%  "
              f"CAGR={s['cagr']:+7.1f}%  Sharpe={s['sharpe']:+.2f}  maxDD={s['mdd']:5.1f}%")
        q = r.groupby(r.index.to_period('Q')).agg(['size', 'sum'])
        print('     by quarter (weeks, summed weekly return): ' +
              '  '.join(f"{p}: {int(n)}w {v*100:+.1f}%" for p, (n, v) in q.iterrows()))
    print(f"\n  XS7 HOLDOUT {'PASSES' if ok else 'FAILS'}")


if __name__ == '__main__':
    main()
