"""
Download free CoinMetrics community daily on-chain metrics for BTC and
ETH into data/backtest_cache/onchain/<asset>_daily.csv. Full history
(BTC from 2010/2011, ETH from 2015) to the latest day; the test scripts
cut at 2026-01-01 themselves.
"""
import os

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'backtest_cache', 'onchain')
BASE = 'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics'
METRICS = ['PriceUSD', 'CapMVRVCur', 'CapMrktCurUSD', 'FlowInExUSD', 'FlowOutExUSD', 'FlowInExNtv', 'FlowOutExNtv',
           'SplyExNtv', 'SplyCur', 'AdrActCnt', 'AdrBalCnt', 'TxCnt', 'TxTfrCnt', 'HashRate', 'FeeTotNtv',
           'IssTotNtv', 'volume_reported_spot_usd_1d']


def fetch(asset):
    rows, url = [], BASE
    params = {'assets': asset, 'metrics': ','.join(METRICS), 'frequency': '1d', 'page_size': 10000, 'start_time': '2010-01-01'}
    while url:
        r = requests.get(url, params=params if url == BASE else None, timeout=120)
        r.raise_for_status()
        j = r.json()
        rows += j['data']
        url = j.get('next_page_url')
    df = pd.DataFrame(rows)
    df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None).dt.normalize()
    for c in METRICS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.drop(columns=['asset']).set_index('time').sort_index()


def main():
    os.makedirs(OUT, exist_ok=True)
    for a in ['btc', 'eth']:
        df = fetch(a)
        df.to_csv(os.path.join(OUT, f'{a}_daily.csv'))
        print(f'{a}: {len(df)} days {df.index[0].date()}..{df.index[-1].date()}  missing: '
              + ', '.join(f'{c}={df[c].isna().mean()*100:.0f}%' for c in df.columns if df[c].isna().mean() > 0.05), flush=True)


if __name__ == '__main__':
    main()
