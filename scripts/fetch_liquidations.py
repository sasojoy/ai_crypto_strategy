"""
Download Binance COIN-M liquidation snapshots (the only liquidation
history Binance publishes; USDT-M has none) for BTCUSD_PERP and
ETHUSD_PERP, daily zips 2023-06-25 .. 2024-10-14, into
data/backtest_cache/liquidations/raw/<SYM>/<date>.csv, then one merged
CSV per symbol. Re-runnable; existing days are skipped.
"""
import io
import os
import sys
import zipfile
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'backtest_cache', 'liquidations')
RAW = os.path.join(OUT, 'raw')
URL = 'https://data.binance.vision/data/futures/cm/daily/liquidationSnapshot/{sym}/{sym}-liquidationSnapshot-{d}.zip'
DAYS = pd.date_range('2023-06-25', '2024-10-14', freq='D')


def fetch(sym, d):
    path = os.path.join(RAW, sym, f'{d}.csv')
    if os.path.exists(path):
        return 'cached'
    try:
        with urllib.request.urlopen(URL.format(sym=sym, d=d), timeout=60) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 'missing'
        raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        raw = z.read(z.namelist()[0]).decode('utf-8')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(raw)
    return 'fetched'


def main():
    for sym in sys.argv[1:] or ['BTCUSD_PERP', 'ETHUSD_PERP']:
        st = {'fetched': 0, 'cached': 0, 'missing': 0}
        for d in DAYS:
            st[fetch(sym, d.strftime('%Y-%m-%d'))] += 1
        parts = [pd.read_csv(os.path.join(RAW, sym, f)) for f in sorted(os.listdir(os.path.join(RAW, sym)))]
        df = pd.concat(parts, ignore_index=True)
        df.to_csv(os.path.join(OUT, f'{sym}_liquidations.csv'), index=False)
        print(f'{sym}: {len(df)} rows, {st}, columns={list(df.columns)}', flush=True)


if __name__ == '__main__':
    main()
