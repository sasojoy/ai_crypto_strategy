"""
Post-pass robustness diagnostics for H_K1 (dev window only, 2026 untouched).
Not a test and not tuning: the rule is unchanged, only the timing is
made worse to see whether the result survives.
  (a) stale score: funding from (s-14d, s-7d] instead of (s-7d, s]
  (b) one-day implementation lag: positions taken at Monday close,
      forward return Monday->Monday, funding window shifted by one day
  (c) 1-week lookback replaced by the single most recent settlement
      (noisier score) -- same ranking machinery
A genuine carry/reversal effect should decay gracefully under (a)/(b);
an alignment bug would vanish or flip.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = sys.argv[:1]
import prereg_xs_funding as K  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402
from prereg_xs_momentum import backtest  # noqa: E402

fn = lambda sc: list(sc.sort_values(ascending=False).index)  # noqa: E731


def weeks_variant(px, fund, kind):
    sundays = px.index[px.index.dayofweek == 6]
    out = []
    for s in sundays:
        lag = pd.Timedelta(days=1) if kind == 'lag1d' else pd.Timedelta(0)
        e0, e1 = s + lag, s + lag + pd.Timedelta(days=7)
        if e0 not in px.index or e1 not in px.index:
            continue
        if kind == 'stale':
            lo, hi = s - pd.Timedelta(days=14), s - pd.Timedelta(days=7)
        else:
            lo, hi = s - pd.Timedelta(days=7), s
        sc = {}
        for c in px.columns:
            f = fund[c][(fund[c].index > lo) & (fund[c].index <= hi)]
            if kind == 'last1':
                f = f.iloc[-1:]
            if len(f):
                sc[c] = f.mean()
        sc = pd.Series(sc)
        fwd = px.loc[e1] / px.loc[e0] - 1
        ok = sc.index[sc.notna() & fwd.reindex(sc.index).notna()]
        flo, fhi = e0 + pd.Timedelta(days=1), e1 + pd.Timedelta(days=1)
        fsum = pd.Series({c: fund[c][(fund[c].index > flo) & (fund[c].index <= fhi)].sum() for c in ok})
        out.append((s, sc[ok], fwd[ok], fsum))
    return out


def main():
    px, fund = full_daily_panel()
    px = px[(px.index >= K.START) & (px.index < K.END)]
    for kind in ('base', 'stale', 'lag1d', 'last1'):
        weeks = weeks_variant(px, fund, kind)
        r = backtest(weeks, list(px.columns), fn)
        dec = K.decompose(weeks, list(px.columns), fn)
        for per, m in [('2020-23', r.index < K.SPLIT), ('2024-25', r.index >= K.SPLIT), ('full', r.index == r.index)]:
            dm = dec.loc[r.index[m]]
            print(f'  {kind:6s} {per:8s} ann net={r[m].mean()*52*100:+7.1f}%  Sharpe={K.sharpe(r[m]):+.2f}  '
                  f'price={dm.price.mean()*52*100:+6.1f}%  funding={dm.funding.mean()*52*100:+5.1f}%')


if __name__ == '__main__':
    main()
