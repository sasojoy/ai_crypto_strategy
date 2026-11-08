"""
Download Binance USDT-M futures 5-minute klines for the 50-coin research
set (15-coin basket + 35 unseen) from the public archive
(data.binance.vision, monthly zips), 2020-01 .. 2025-12, into
data/backtest_cache/universe_5m/<BASE>_USDT_5m.csv (UTC timestamps, same
column layout as the 1H caches: timestamp,open,high,low,close,volume).

Months that do not exist (coin listed later) are skipped. Re-runnable:
a month already in the per-coin raw folder is not fetched again.
"""
import io
import os
import sys
import zipfile
import urllib.request

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
OUT = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_5m')
RAW = os.path.join(OUT, 'raw')
BASE_URL = 'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{sym}-5m-{ym}.zip'
MONTHS = [f'{y}-{m:02d}' for y in range(2020, 2026) for m in range(1, 13)]
COLS = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume',
        'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore']


def coins():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    return basket + others


def fetch_month(sym, ym):
    path = os.path.join(RAW, sym, f'{ym}.csv')
    if os.path.exists(path):
        return 'cached'
    url = BASE_URL.format(sym=sym, ym=ym)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 'missing'
        raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        raw = z.read(name).decode('utf-8')
    first = raw.split('\n', 1)[0]
    df = pd.read_csv(io.StringIO(raw), header=0 if first.startswith('open_time') else None, names=COLS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df[['open_time', 'open', 'high', 'low', 'close', 'volume']].to_csv(path, index=False)
    return 'fetched'


def main():
    os.makedirs(OUT, exist_ok=True)
    for base in coins():
        sym = f'{base}USDT'
        out_path = os.path.join(OUT, f'{base}_USDT_5m.csv')
        status = {'fetched': 0, 'cached': 0, 'missing': 0}
        for ym in MONTHS:
            status[fetch_month(sym, ym)] += 1
        parts = []
        d = os.path.join(RAW, sym)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                parts.append(pd.read_csv(os.path.join(d, f)))
        if not parts:
            print(f'{base}: no data', flush=True)
            continue
        df = pd.concat(parts, ignore_index=True)
        # open_time is ms since epoch (older files) or, from 2025, microseconds; normalise
        unit = 'us' if df['open_time'].iloc[-1] > 1e14 else 'ms'
        df['timestamp'] = pd.to_datetime(df['open_time'].astype('int64'), unit=unit)
        df = df.drop_duplicates('timestamp').sort_values('timestamp')
        df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].to_csv(out_path, index=False)
        print(f'{base}: {len(df)} bars  {df.timestamp.iloc[0]} .. {df.timestamp.iloc[-1]}  {status}', flush=True)


if __name__ == '__main__':
    main()
