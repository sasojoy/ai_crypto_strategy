"""
FORWARD TRACKER: v7 signal + open-interest risk reallocation
(pre-registered 2026-10-03, RESEARCH_FINDINGS.md). Frozen rules -- do not edit.

Uses the SAME trades as forward_tracker.py (v7, 50 coins, frozen rules, from
2026-10-01): run that first. For each trade:
  dOI = OI at the trigger bar's close / OI at its open - 1, from the daily
        5-minute `metrics` files on data.binance.vision (nearest snapshot at
        or before, within 15 minutes). Files appear ~1 day late; trades whose
        file is not out yet are "pending".
Tracks: OI-fell vs OI-rose average R, and a reallocated book where OI-rose
trades carry 0.5x risk and OI-fell trades 1x, renormalized to mean risk 1.
Final verdict at >= 1,500 closed trades with dOI: OI-fell avgR > OI-rose
avgR (within-coin permutation, one-sided p < 0.05) AND reallocated total R
> flat total R.
"""
import io
import os
import sys
import zipfile

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forward_tracker import OUT as FWD

CACHE = os.path.join(FWD, 'metrics_cache')
URL = 'https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip'
FINAL_N = 1500
N_PERM = 10000


def day_metrics(sym, day):
    path = os.path.join(CACHE, f'{sym}-{day}.csv')
    if os.path.exists(path):
        return pd.read_csv(path, parse_dates=['create_time'])
    r = requests.get(URL.format(s=sym, d=day), timeout=30)
    if r.status_code != 200:
        return None  # not published yet
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        m = pd.read_csv(z.open(z.namelist()[0]), usecols=['create_time', 'sum_open_interest'])
    m.to_csv(path, index=False)
    return pd.read_csv(path, parse_dates=['create_time'])


def oi_at(sym, t):
    frames = [day_metrics(sym, d.strftime('%Y-%m-%d')) for d in {t.normalize(), (t - pd.Timedelta(minutes=15)).normalize()}]
    if any(f is None for f in frames):
        return None
    m = pd.concat(frames).drop_duplicates('create_time').sort_values('create_time')
    m = m[(m.create_time <= t) & (m.create_time >= t - pd.Timedelta(minutes=15))]
    return float(m.sum_open_interest.iloc[-1]) if len(m) else np.nan


def run():
    os.makedirs(CACHE, exist_ok=True)
    d = pd.read_csv(os.path.join(FWD, 'forward_trades.csv'), parse_dates=['time'])
    doi = []
    for r in d.itertuples():
        a, b = oi_at(f'{r.coin}USDT', r.time), oi_at(f'{r.coin}USDT', r.time + pd.Timedelta(hours=1))
        doi.append(np.nan if a is None or b is None or not a or np.isnan(a) or np.isnan(b) else b / a - 1)
    d['doi'] = doi
    d.to_csv(os.path.join(FWD, 'forward_trades_oi.csv'), index=False)
    x = d[(d.status != 'OPEN') & d.doi.notna()].copy()
    pending = int(((d.status != 'OPEN') & d.doi.isna()).sum())
    lines = [f"已結束且有OI資料 {len(x)} 筆（OI資料待出 {pending} 筆）"]
    if len(x) >= 2:
        x['fell'] = x.doi <= 0
        fell, rose = x[x.fell].r, x[~x.fell].r
        w = np.where(x.fell, 1.0, 0.5)
        realloc = (x.r * w).sum() / w.mean()
        lines.append(f"  OI減少 {len(fell)} 筆 平均 {fell.mean():+.3f}R｜OI增加 {len(rose)} 筆 平均 {rose.mean():+.3f}R")
        lines.append(f"  原版總計 {x.r.sum():+.1f}R｜依OI調整押注 {realloc:+.1f}R")
        if len(x) >= FINAL_N and len(fell) and len(rose):
            rng = np.random.default_rng(3)
            real = fell.mean() - rose.mean()
            lab, rv = x.fell.values, x.r.values
            idx = [np.flatnonzero(x.coin.values == c) for c in x.coin.unique()]
            hits = 0
            for _ in range(N_PERM):
                sh = lab.copy()
                for ix in idx:
                    sh[ix] = rng.permutation(sh[ix])
                hits += (rv[sh].mean() - rv[~sh].mean()) >= real
            ok = hits / N_PERM < 0.05 and realloc > x.r.sum()
            lines.append(f"  ★ 已達 {FINAL_N} 筆，最終判定：{'確認' if ok else '未確認'}（p={hits / N_PERM:.3f}）")
        else:
            lines.append(f"  進度 {len(x)}/{FINAL_N} 筆（期中只看不判定）")
    msg = '\n'.join(lines)
    print(msg)
    return msg


if __name__ == '__main__':
    run()
