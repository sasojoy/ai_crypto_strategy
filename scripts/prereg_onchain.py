"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向F：鏈上資料", 2026-10-24).
DEV WINDOW: BTC 2012-01-01 .. 2025-12-31, ETH 2016-01-01 .. 2025-12-31.
2026 untouched. Data: data/backtest_cache/onchain/{btc,eth}_daily.csv
(CoinMetrics community, fetch_onchain.py). Price = CoinMetrics PriceUSD
(daily close); the long history is the point, Binance is too short.

Every signal is lagged one day (decision at the close of day d uses data
through d-1; CoinMetrics finalises a day some hours after it ends).
z = value minus trailing 365-day mean, over trailing 365-day std
(causal, >= 180 days). Entry when |z| > 1 and not already in a trade;
hold h days; return = dir * log(P[d+h] / P[d]) - 0.14 %.

  H_F1  valuation (MVRV): z of log(CapMVRVCur); dir = -sign(z); h = 28
  H_F2  exchange net flow: 7-day sum of (FlowInExUSD - FlowOutExUSD)
        over CapMrktCurUSD; z of that; dir = -sign(z) (net inflow =
        sell pressure -> short; outflow -> long); h = 7
  H_F3  exchange balance trend: 30-day log change of SplyExNtv; z;
        dir = -sign(z) (coins leaving exchanges -> long); h = 28
  H_F4  network activity momentum: 28-day log change of the 7-day mean
        of AdrActCnt; z; dir = +sign(z); h = 28

Inference per hypothesis: trades of BTC and ETH pooled; one-sided
t-test and 10,000x bootstrap. Four hypotheses, so alpha = 0.05 / 4 =
0.0125. Pass = pooled mean > 0, p < 0.0125, pooled mean > 0 both before
2020-01-01 and from 2020-01-01, and BTC mean > 0 and ETH mean > 0.
Breakdowns (by year, long/short) only after a pass. No re-tuning.
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONC = os.path.join(ROOT, 'data', 'backtest_cache', 'onchain')
DEV = {'btc': pd.Timestamp('2012-01-01'), 'eth': pd.Timestamp('2016-01-01')}
END, SPLIT = pd.Timestamp('2026-01-01'), pd.Timestamp('2020-01-01')
ZWIN, ZMIN, ZCUT = 365, 180, 1.0
COST = 0.0014
N_BOOT, ALPHA, SEED = 10000, 0.0125, 20261024


def zscore(x):
    return (x - x.rolling(ZWIN, min_periods=ZMIN).mean()) / x.rolling(ZWIN, min_periods=ZMIN).std()


def signals(d):
    s = pd.DataFrame(index=d.index)
    s['F1'] = -zscore(np.log(d['CapMVRVCur']))
    nf = (d['FlowInExUSD'] - d['FlowOutExUSD']).rolling(7).sum() / d['CapMrktCurUSD']
    s['F2'] = -zscore(nf)
    s['F3'] = -zscore(np.log(d['SplyExNtv']).diff(30))
    s['F4'] = zscore(np.log(d['AdrActCnt'].rolling(7).mean()).diff(28))
    return s.shift(1)  # one-day publication lag


HOLD = {'F1': 28, 'F2': 7, 'F3': 28, 'F4': 28}


def trades(asset):
    d = pd.read_csv(os.path.join(ONC, f'{asset}_daily.csv'), parse_dates=['time']).set_index('time')
    d = d[d.index < END]
    s = signals(d)
    p = d['PriceUSD']
    out = {}
    for h, hd in HOLD.items():
        rows, last_exit = [], pd.Timestamp('2000-01-01')
        idx = d.index
        for i in range(len(idx) - hd):
            t = idx[i]
            v = s[h].iloc[i]
            if t < DEV[asset] or t < last_exit or not np.isfinite(v) or abs(v) <= ZCUT:
                continue
            dr = np.sign(v)
            rows.append((asset, t, dr, dr * np.log(p.iloc[i + hd] / p.iloc[i]) - COST))
            last_exit = idx[i + hd]
        out[h] = pd.DataFrame(rows, columns=['asset', 'time', 'dir', 'r'])
    return out


def infer(x, rng):
    x = np.asarray(x, float)
    if len(x) < 20:
        return np.nan, np.nan, np.nan, len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, (N_BOOT, len(x))).mean(1)
    return x.mean(), t, (boot <= 0).mean(), len(x)


def main():
    rng = np.random.default_rng(SEED)
    tr = {a: trades(a) for a in ('btc', 'eth')}
    names = {'F1': 'H_F1 MVRV valuation (28d)', 'F2': 'H_F2 exchange net flow (7d)',
             'F3': 'H_F3 exchange balance trend (28d)', 'F4': 'H_F4 active-address momentum (28d)'}
    for h, name in names.items():
        d = pd.concat([tr['btc'][h], tr['eth'][h]], ignore_index=True)
        print(f'\n=== {name} ===')
        res = {}
        for label, sub in [('pooled', d), ('btc', d[d.asset == 'btc']), ('eth', d[d.asset == 'eth'])]:
            for per, m in [('pre-2020', sub.time < SPLIT), ('2020-25', sub.time >= SPLIT), ('full', slice(None))]:
                x = sub[m].r if not isinstance(m, slice) else sub.r
                mean, t, p, n = infer(x, rng)
                res[(label, per)] = (mean, p)
                print(f'  {label:6s} {per:8s} mean={mean*100:+6.2f}%  t={t:+5.2f}  p={p:.4f}  trades={n}')
        ok = (res[('pooled', 'full')][0] > 0 and res[('pooled', 'full')][1] < ALPHA
              and res[('pooled', 'pre-2020')][0] > 0 and res[('pooled', '2020-25')][0] > 0
              and res[('btc', 'full')][0] > 0 and res[('eth', 'full')][0] > 0)
        print(f'  -> {h} {"PASS" if ok else "FAIL"}')
        if ok:
            for lab, m in [('long', d.dir > 0), ('short', d.dir < 0)]:
                print(f'    {lab:5s} n={m.sum()}  mean={d[m].r.mean()*100:+.2f}%')
            for y, g in d.groupby(d.time.dt.year):
                print(f'    {y}: n={len(g)}  mean={g.r.mean()*100:+.2f}%  win={(g.r>0).mean()*100:.0f}%')
        d.to_csv(os.path.join(ROOT, 'scripts', f'onchain_{h}_trades.csv'), index=False)


if __name__ == '__main__':
    main()
