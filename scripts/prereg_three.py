"""
PRE-REGISTERED TESTS (RESEARCH_FINDINGS.md, commit dccea7f), 2026-10-02.
50 coins (15-coin basket + 35 unseen), 1H, periods 2020-23 / 2024-25 / 2026,
0.14% round-trip cost.

  S1 CAP   capitulation / blow-off fade (stop beyond the candle, 2R, 48h)
  S2 LAG   BTC leads, lagging alts catch up (1-hour hold)
  S3 FUND  drift in the hour before an 8-hourly funding settlement

Each passes only if its mean (R for S1, net return for S2/S3) is > 0 in all
6 cells AND it beats its pre-registered baseline/control on the full sample.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr
from dev_coin_personality import ORIGINAL, MAJORS, load
from fetch_holdout_2026 import coins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
HOLD = os.path.join(CACHE, 'holdout_2026')
COST = 0.0014
BASKET = ORIGINAL + MAJORS


def period(t):
    return np.where(t < pd.Timestamp('2024-01-01'), '2020-23', np.where(t < pd.Timestamp('2026-01-01'), '2024-25', '2026'))


def load_full(b):
    dev = load(b)
    h = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
    df = pd.concat([dev[dev.timestamp < '2026-01-01'], h[h.timestamp >= '2026-01-01']])
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].drop_duplicates('timestamp').sort_values('timestamp')
    df = df.reset_index(drop=True)
    df['atr_prev'] = compute_atr(df).shift(1)
    df['volma_prev'] = df['volume'].rolling(20).mean().shift(1)
    return df


def load_funding(b):
    fdir = 'funding_basket' if b in BASKET else 'funding_universe'
    f = pd.concat([pd.read_csv(os.path.join(CACHE, fdir, f'{b}_USDT_funding.csv')),
                   pd.read_csv(os.path.join(HOLD, f'{b}_USDT_funding.csv'))])
    f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('min')
    return f.drop_duplicates('timestamp').set_index('timestamp')['funding_rate'].sort_index()


def summarize(name, d, val, extra_ok, extra_msg):
    print('=' * 110 + f'\n{name}')
    ok = True
    for (p, s), g in d.groupby(['period', 'sample']):
        m = g[val].mean()
        ok &= m > 0
        unit = 'R' if val == 'r' else '%'
        shown = m if val == 'r' else m * 100
        print(f"  {p} {s}-coin  n={len(g):5d}  mean {shown:+.4f}{unit}  win {(g[val] > 0).mean()*100:5.1f}%")
    print(f"  {extra_msg}")
    print(f"  -> {name.split()[0]} {'PASSES' if (ok and extra_ok) else 'FAILS'}  (all 6 cells > 0: {ok}; vs baseline: {extra_ok})")


# ---------------- S1 CAP ----------------
def cap_trade(df, i, sgn, stop_dist):
    c, h, l = df['close'].values, df['high'].values, df['low'].values
    entry = c[i]
    if i + 49 > len(c) or stop_dist <= 0:
        return None
    sl, tp = entry - sgn * stop_dist, entry + sgn * 2 * stop_dist
    px = c[i + 48]
    for j in range(i + 1, i + 49):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            px = sl
            break
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            px = tp
            break
    return (sgn * (px - entry) / entry - COST) / (stop_dist / entry)


def s1(frames, rng):
    rows, pools = [], {}
    for b, df in frames.items():
        o, c, h, l, v, a, vm = (df[k].values for k in ('open', 'close', 'high', 'low', 'volume', 'atr_prev', 'volma_prev'))
        last = -10**9
        mults = []
        for i in range(25, len(df)):
            if i - last < 24 or np.isnan(a[i]) or np.isnan(vm[i]) or a[i] <= 0:
                continue
            if abs(c[i] - o[i]) >= 4 * a[i] and v[i] >= 3 * vm[i]:
                sgn = 1 if c[i] < o[i] else -1
                extreme = l[i] if sgn > 0 else h[i]
                stop_dist = abs(c[i] - extreme) + 0.5 * a[i]
                r = cap_trade(df, i, sgn, stop_dist)
                if r is not None:
                    rows.append(dict(coin=b, time=df['timestamp'].iloc[i], sgn=sgn, r=r))
                    mults.append(stop_dist / a[i])
                    last = i
        valid = np.nonzero(~np.isnan(a) & (np.arange(len(df)) + 49 <= len(df)))[0]
        if mults:
            for sgn in (1, -1):
                picks = rng.choice(valid, size=min(1500, len(valid)), replace=False)
                pools[(b, sgn)] = np.array([x for x in (cap_trade(df, i, sgn, rng.choice(mults) * a[i]) for i in picks) if x is not None])
    d = pd.DataFrame(rows)
    d['period'], d['sample'] = period(d.time), np.where(d.coin.isin(BASKET), '15', '35')
    counts = d.groupby(['coin', 'sgn']).size()
    sims = np.array([np.concatenate([rng.choice(pools[k], n) for k, n in counts.items()]).mean() for _ in range(1000)])
    beat = (d.r.mean() > sims).mean() * 100
    summarize('S1 CAP (capitulation / blow-off fade)', d, 'r', beat >= 95,
              f"all: n={len(d)} avgR {d.r.mean():+.3f}; random baseline median {np.median(sims):+.3f}, real beats {beat:.1f}%  "
              f"| longs {d[d.sgn == 1].r.mean():+.3f} (n={int((d.sgn == 1).sum())}), shorts {d[d.sgn == -1].r.mean():+.3f}")


# ---------------- S2 LAG ----------------
def s2(frames):
    btc = frames['BTC'].set_index('timestamp')
    big = (btc['close'] - btc['open']).abs() >= 1.5 * btc['atr_prev']
    rb = btc['close'].pct_change()
    rows = []
    for b, df in frames.items():
        if b == 'BTC':
            continue
        x = df.set_index('timestamp')
        ra = x['close'].pct_change()
        rbb = rb.reindex(x.index)
        beta = (ra.rolling(720).cov(rbb) / rbb.rolling(720).var()).shift(1)
        fwd = x['close'].shift(-1) / x['close'] - 1
        bigx = big.reindex(x.index).fillna(False).astype(bool)
        sgn = np.sign(rbb)
        expected = beta * rbb
        lag = (sgn * ra) < 0.5 * (sgn * expected)
        base = bigx & (beta > 0) & fwd.notna() & beta.notna()
        net = sgn * fwd - COST
        for t in x.index[base]:
            rows.append(dict(coin=b, time=t, lagging=bool(lag[t]), net=net[t]))
    allx = pd.DataFrame(rows)
    allx['period'], allx['sample'] = period(allx.time), np.where(allx.coin.isin(BASKET), '15', '35')
    d = allx[allx.lagging]
    summarize('S2 LAG (BTC leads, lagging alts catch up, 1h hold)', d, 'net', d.net.mean() > allx.net.mean(),
              f"lagging alts mean {d.net.mean()*100:+.4f}% (n={len(d)}) vs control (all alts, same hours) {allx.net.mean()*100:+.4f}% (n={len(allx)})")


# ---------------- S3 FUND ----------------
def s3(frames):
    rows = []
    for b, df in frames.items():
        f = load_funding(b)
        t = f.index
        is8h = (t.hour % 8 == 0) & (t.minute == 0) & (pd.Series(t).diff().dt.total_seconds().values == 8 * 3600)
        f8 = f[is8h]
        close = df.set_index('timestamp')['close']
        entry = close.reindex(f8.index - pd.Timedelta(hours=2))   # bar T-2h closes at T-1h
        exit_ = close.reindex(f8.index - pd.Timedelta(hours=1))   # bar T-1h closes at T
        ret = exit_.values / entry.values - 1
        for T, fr, r in zip(f8.index, f8.values, ret):
            if np.isnan(r) or fr == 0:
                continue
            rows.append(dict(coin=b, time=T, f=fr, net=-np.sign(fr) * r - COST))
    allx = pd.DataFrame(rows)
    allx['period'], allx['sample'] = period(allx.time), np.where(allx.coin.isin(BASKET), '15', '35')
    d = allx[allx.f.abs() >= 0.0003]
    summarize('S3 FUND (fade the crowded side in the hour before an 8h settlement)', d, 'net', d.net.mean() > allx.net.mean(),
              f"|f|>=0.03% mean {d.net.mean()*100:+.4f}% (n={len(d)}) vs control (all settlements, sign of f) {allx.net.mean()*100:+.4f}% (n={len(allx)})"
              f"  | gross before cost {(d.net.mean() + COST)*100:+.4f}%")


def main():
    frames = {b: load_full(b) for b in coins()}
    rng = np.random.default_rng(1002)
    s1(frames, rng)
    s2(frames)
    s3(frames)


if __name__ == '__main__':
    main()
