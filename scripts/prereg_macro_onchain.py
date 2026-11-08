"""
PRE-REGISTERED TESTS (RESEARCH_FINDINGS.md "第三輪新方向 L / N", 2026-10-25).
2026 untouched. Data: CoinMetrics community (data/backtest_cache/onchain/;
stablecoin supply fetched here into stable_daily.csv). Price = PriceUSD.
Every signal is lagged one day. cost 0.14 %.

  H_L1 stablecoin supply: x = log(SplyCur_usdt + SplyCur_usdc), 30-day
       change, z vs trailing 365 d (>= 180); |z| > 1 -> dir = sign(z),
       hold 28 d, no overlap, BTC and ETH pooled. Dev 2018-01 .. 2025-12,
       halves split 2022-01-01. Pass = pooled mean > 0, p < 0.025, both
       halves > 0, BTC > 0 and ETH > 0.
  H_N1 hash ribbons: BTC HashRate 30-d SMA crosses above the 60-d SMA
       (yesterday below, today at/above) -> long 60 d. Dev 2012 .. 2025,
       halves split 2020-01-01. Pass = mean > 0, bootstrap p < 0.025, both
       halves > 0; fewer than 10 events = "cannot test".
"""
import os

import numpy as np
import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONC = os.path.join(ROOT, 'data', 'backtest_cache', 'onchain')
BASE = 'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics'
END = pd.Timestamp('2026-01-01')
COST, N_BOOT, ALPHA, SEED = 0.0014, 10000, 0.025, 20261025
L_DEV, L_SPLIT, L_HOLD = pd.Timestamp('2018-01-01'), pd.Timestamp('2022-01-01'), 28
N_DEV, N_SPLIT, N_HOLD = pd.Timestamp('2012-01-01'), pd.Timestamp('2020-01-01'), 60


def fetch_stable():
    path = os.path.join(ONC, 'stable_daily.csv')
    if os.path.exists(path):
        return pd.read_csv(path, parse_dates=['time']).set_index('time')
    frames = []
    for a in ('usdt', 'usdc'):
        rows, url = [], BASE
        params = {'assets': a, 'metrics': 'SplyCur', 'frequency': '1d', 'page_size': 10000, 'start_time': '2014-01-01'}
        while url:
            j = requests.get(url, params=params if url == BASE else None, timeout=120).json()
            rows += j['data']
            url = j.get('next_page_url')
        df = pd.DataFrame(rows)
        df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None).dt.normalize()
        frames.append(df.set_index('time')['SplyCur'].astype(float).rename(a))
    out = pd.concat(frames, axis=1).sort_index()
    out.to_csv(path)
    return out


def infer(x, rng):
    x = np.asarray(x, float)
    if len(x) < 10:
        return np.nan, np.nan, np.nan, len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, (N_BOOT, len(x))).mean(1)
    return x.mean(), t, (boot <= 0).mean(), len(x)


def price(asset):
    d = pd.read_csv(os.path.join(ONC, f'{asset}_daily.csv'), parse_dates=['time']).set_index('time')
    return d[d.index < END]


def trades_from_signal(p, sig, dev, hold, allow_short=True):
    """sig: series of +1/-1/0 (already lagged). Non-overlapping trades."""
    rows, last_exit = [], pd.Timestamp('2000-01-01')
    idx = p.index
    for i in range(len(idx) - hold):
        t, v = idx[i], sig.iloc[i]
        if t < dev or t < last_exit or not np.isfinite(v) or v == 0 or (v < 0 and not allow_short):
            continue
        rows.append((t, v, v * np.log(p.iloc[i + hold] / p.iloc[i]) - COST))
        last_exit = idx[i + hold]
    return pd.DataFrame(rows, columns=['time', 'dir', 'r'])


def main():
    rng = np.random.default_rng(SEED)
    st = fetch_stable()
    tot = np.log(st.fillna(0).sum(axis=1).replace(0, np.nan))
    x = tot.diff(30)
    z = ((x - x.rolling(365, min_periods=180).mean()) / x.rolling(365, min_periods=180).std()).shift(1)
    sig = np.sign(z).where(z.abs() > 1, 0)
    print(f'stablecoin supply {st.index.min().date()}..{st.index.max().date()}  latest USDT+USDC = {np.exp(tot.dropna().iloc[-1])/1e9:.0f} B')

    print('\n=== H_L1 stablecoin supply growth z, |z|>1 -> sign(z), 28d, BTC+ETH ===')
    parts = []
    for a in ('btc', 'eth'):
        p = price(a)['PriceUSD'].dropna()
        d = trades_from_signal(p, sig.reindex(p.index), L_DEV, L_HOLD)
        d['asset'] = a
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    res = {}
    for label, sub in [('pooled', d), ('btc', d[d.asset == 'btc']), ('eth', d[d.asset == 'eth']),
                       ('2018-21', d[d.time < L_SPLIT]), ('2022-25', d[d.time >= L_SPLIT])]:
        mean, t, p_, n = infer(sub.r, rng)
        res[label] = (mean, p_)
        print(f'  {label:8s} mean={mean*100:+6.2f}%  t={t:+5.2f}  p={p_:.4f}  trades={n}  long={int((sub.dir>0).sum())}')
    ok = (res['pooled'][0] > 0 and res['pooled'][1] < ALPHA and res['2018-21'][0] > 0 and res['2022-25'][0] > 0
          and res['btc'][0] > 0 and res['eth'][0] > 0)
    print(f'  -> H_L1 {"PASS" if ok else "FAIL"}')
    if ok:
        for lab, m in [('long', d.dir > 0), ('short', d.dir < 0)]:
            print(f'    {lab:5s} n={m.sum()}  mean={d[m].r.mean()*100:+.2f}%')
    d.to_csv(os.path.join(ROOT, 'scripts', 'stablecoin_L1_trades.csv'), index=False)

    print('\n=== H_N1 hash ribbons: 30d SMA crosses above 60d SMA -> long BTC 60d ===')
    b = price('btc')
    hr = b['HashRate']
    s30, s60 = hr.rolling(30).mean(), hr.rolling(60).mean()
    cross = ((s30 >= s60) & (s30.shift(1) < s60.shift(1))).astype(float).shift(1)
    d = trades_from_signal(b['PriceUSD'], cross.reindex(b.index), N_DEV, N_HOLD, allow_short=False)
    if len(d) < 10:
        print(f'  events={len(d)} -> cannot test')
    else:
        res = {}
        for label, sub in [('all', d), ('2012-19', d[d.time < N_SPLIT]), ('2020-25', d[d.time >= N_SPLIT])]:
            mean, t, p_, n = infer(sub.r, rng)
            res[label] = (mean, p_)
            print(f'  {label:8s} mean={mean*100:+6.2f}%  t={t:+5.2f}  p={p_:.4f}  events={n}  win={(sub.r>0).mean()*100:.0f}%')
        ok = res['all'][0] > 0 and res['all'][1] < ALPHA and res['2012-19'][0] > 0 and res['2020-25'][0] > 0
        print(f'  -> H_N1 {"PASS" if ok else "FAIL"}')
        # benchmark for context (not a criterion): unconditional 60d BTC return over the same dev window
        p = b['PriceUSD'][b.index >= N_DEV]
        print(f'  context: unconditional 60d log return mean over dev = {np.log(p.shift(-N_HOLD)/p).dropna().mean()*100:+.2f}%')
    d.to_csv(os.path.join(ROOT, 'scripts', 'hashribbon_N1_trades.csv'), index=False)


if __name__ == '__main__':
    main()
