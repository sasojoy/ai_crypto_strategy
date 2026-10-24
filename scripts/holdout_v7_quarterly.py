"""
DESCRIPTIVE check (2026-10-01, user question: "didn't v7 pass the holdout
and make money in 2026?"). Recomputes 2026 results for the setup that
actually runs live -- v7 = v3 anticipatory 1-minute entry (with the
2026-09-19 fresh-cross fix and the post-close volume-confirmation exit)
+ v6 ADX-scaled risk (1%..3%, live anchors from paper_trading/
thresholds.json) -- on the original 5 coins, split by QUARTER.

Same methodology as the earlier holdout runs this is compared with
(holdout_v3_anticipatory_entry.py): volume cutoffs recalibrated within the
2026 trigger population, only trades whose 7-day window is complete.
Reuses that script's functions unchanged.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from holdout_v3_anticipatory_entry import (SYMBOLS, prepare_symbol, holdout_cutoffs, classic_baseline_trades,
                                           v3_anticipatory_trades, BASE_RISK_PER_TRADE)
from dev_momentum_adx_trend_filter import compute_adx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_RISK, MAX_RISK = 0.01, 0.03


def adx_risk(adx, p1, p99):
    if np.isnan(adx) or p99 <= p1:
        return (MIN_RISK + MAX_RISK) / 2
    return MIN_RISK + max(0.0, min(1.0, (adx - p1) / (p99 - p1))) * (MAX_RISK - MIN_RISK)


def main():
    with open(os.path.join(ROOT, 'paper_trading', 'thresholds.json')) as f:
        th = json.load(f)
    p1s, p99s = th['adx_p1_within_tercile_by_symbol'], th['adx_p99_within_tercile_by_symbol']
    rows = []
    for s in SYMBOLS:
        df, dfm = prepare_symbol(s)
        df['adx'] = compute_adx(df)
        cutoff, cutoff_causal, hdf = holdout_cutoffs(df, s)
        ts = df['timestamp'].values
        for kind, t in (('v1 close-entry', classic_baseline_trades(df, hdf, cutoff)),
                        ('v7 = v3 entry', v3_anticipatory_trades(df, dfm, cutoff, cutoff_causal))):
            for r in t.itertuples():
                h = int(np.searchsorted(ts, np.datetime64(r.timestamp)))
                adx_prev = df['adx'].iloc[h - 1] if kind.startswith('v7') else df['adx'].iloc[h]
                risk = adx_risk(adx_prev, p1s[s], p99s[s])
                R = r.equity_pnl_pct / (BASE_RISK_PER_TRADE * 100)
                rows.append(dict(symbol=s, kind=kind, time=pd.Timestamp(r.timestamp), reason=r.reason,
                                 R=R, eq_flat=R * 2.0, eq_adx=R * risk * 100))
        print(f"  {s}: done (1m data through {dfm['timestamp'].iloc[-1]})", flush=True)
    d = pd.DataFrame(rows)
    d['q'] = d.time.dt.to_period('Q')
    d.to_csv(os.path.join(ROOT, 'scripts', 'holdout_v7_quarterly_trades.csv'), index=False)
    for kind, g in d.groupby('kind', sort=False):
        print('\n' + '=' * 100 + f'\n{kind}  (equity % = sum over trades; flat = 2% risk; ADX = v6 1%..3% risk)')
        for lab, x in list(g.groupby('q')) + [('2026 all', g)]:
            pf = x.R[x.R > 0].sum() / -x.R[x.R < 0].sum() if (x.R < 0).any() else np.inf
            print(f"  {str(lab):9s} n={len(x):4d} win={(x.R > 0).mean()*100:5.1f}% avgR={x.R.mean():+.3f} PF={pf:4.2f}  "
                  f"equity flat {x.eq_flat.sum():+7.1f}%  with ADX risk {x.eq_adx.sum():+7.1f}%")


if __name__ == '__main__':
    main()
