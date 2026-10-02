"""
Downloads Binance USD-M futures `metrics` (5-minute open interest, long/short
ratios, taker buy/sell ratio) from the public archive data.binance.vision,
one zip per coin per day, and stores one CSV per coin.

  python scripts/fetch_metrics.py basket   15-coin basket
  python scripts/fetch_metrics.py others   the 35 unseen universe coins

Output: data/backtest_cache/metrics/<BASE>USDT.csv (days missing from the
archive are skipped and listed).
"""
import io
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS
from fetch_holdout_2026 import coins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'backtest_cache', 'metrics')
URL = 'https://data.binance.vision/data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip'
START, END = pd.Timestamp('2021-12-01'), pd.Timestamp('2026-09-30')
SESSION = requests.Session()


def one_day(sym, day):
    r = SESSION.get(URL.format(s=sym, d=day.strftime('%Y-%m-%d')), timeout=30)
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return pd.read_csv(z.open(z.namelist()[0]))


def fetch_coin(base):
    sym = f'{base}USDT'
    path = os.path.join(OUT, f'{sym}.csv')
    if os.path.exists(path):
        return base, 'cached'
    days = pd.date_range(START, END, freq='D')
    with ThreadPoolExecutor(max_workers=4) as ex:  # 4, not 8: an 8-worker run was reaped under memory pressure
        parts = list(ex.map(lambda d: one_day(sym, d), days))
    got = [p for p in parts if p is not None]
    if not got:
        return base, 'no data'
    df = pd.concat(got, ignore_index=True)
    df.to_csv(path, index=False)
    return base, f'{len(got)}/{len(days)} days'


def main():
    os.makedirs(OUT, exist_ok=True)
    which = sys.argv[1]
    bases = ORIGINAL + MAJORS if which == 'basket' else [c for c in coins() if c not in ORIGINAL + MAJORS]
    for b in bases:
        print(*fetch_coin(b), flush=True)


if __name__ == '__main__':
    main()
