"""
ONE-SHOT 2026 HOLDOUT for H_L1 stablecoin-supply signal (passed dev
2026-10-25). Rule exactly as prereg_macro_onchain.py; entries 2026-01-01
.. 2026-09-22 (28-day hold must complete inside the cached data, which
ends 2026-10-20). Pass (fixed before running): pooled BTC+ETH mean > 0
with one-sided bootstrap p < 0.05 and BTC, ETH same sign; fewer than 10
trades = "cannot test" (reported descriptively, no verdict). Run once.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prereg_macro_onchain as P  # noqa: E402

HSTART, LAST_ENTRY = pd.Timestamp('2026-01-01'), pd.Timestamp('2026-09-22')


def main():
    rng = np.random.default_rng(P.SEED)
    P.END = pd.Timestamp('2026-12-31')
    st = P.fetch_stable()
    tot = np.log(st.fillna(0).sum(axis=1).replace(0, np.nan))
    x = tot.diff(30)
    z = ((x - x.rolling(365, min_periods=180).mean()) / x.rolling(365, min_periods=180).std()).shift(1)
    sig = np.sign(z).where(z.abs() > 1, 0)
    parts = []
    for a in ('btc', 'eth'):
        p = P.price(a)['PriceUSD'].dropna()
        d = P.trades_from_signal(p, sig.reindex(p.index), HSTART, P.L_HOLD)
        d = d[d.time <= LAST_ENTRY]
        d['asset'] = a
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    print(f'2026 trades={len(d)}  long={int((d.dir>0).sum())}  short={int((d.dir<0).sum())}')
    print(d.assign(r=(d.r * 100).round(2)).to_string())
    if len(d) < 10:
        print(f'  pooled mean={d.r.mean()*100:+.2f}%  -> cannot test (n<10), descriptive only')
        return
    mean, t, p_, n = P.infer(d.r, rng)
    b, e = d[d.asset == 'btc'].r.mean(), d[d.asset == 'eth'].r.mean()
    print(f'  pooled mean={mean*100:+.2f}%  t={t:+.2f}  p={p_:.4f}  btc={b*100:+.2f}%  eth={e*100:+.2f}%')
    ok = mean > 0 and p_ < 0.05 and np.sign(b) == np.sign(e)
    print(f'  -> H_L1 2026 {"PASS" if ok else "FAIL"}')


if __name__ == '__main__':
    main()
