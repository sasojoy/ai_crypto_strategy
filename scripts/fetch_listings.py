"""
Fetches daily OHLCV + funding for NEW Binance USDT-M perpetual listings,
for the pre-registered new-listing short test (RESEARCH_FINDINGS.md,
commit d7e610e).

  python scripts/fetch_listings.py dev      onboarded 2021-01-01 .. 2025-06-30
  python scripts/fetch_listings.py holdout  onboarded 2025-07-01 .. 2026-06-15
                                           (ONLY after the dev test passes)

Per coin: the first 130 days of daily bars from listing, and funding over
the same span. Output: data/backtest_cache/listings/<cohort>/
"""
import os
import sys
import time

import ccxt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COHORTS = {'dev': ('2021-01-01', '2025-06-30'), 'holdout': ('2025-07-01', '2026-06-15')}
DAYS = 130


def main(cohort):
    lo, hi = (pd.Timestamp(x) for x in COHORTS[cohort])
    out = os.path.join(ROOT, 'data', 'backtest_cache', 'listings', cohort)
    os.makedirs(out, exist_ok=True)
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    markets = ex.load_markets()
    meta = []
    for m in markets.values():
        info = m.get('info', {})
        if not (m.get('swap') and m['quote'] == 'USDT' and info.get('underlyingType') == 'COIN'
                and info.get('contractType') == 'PERPETUAL'):
            continue
        onboard = pd.Timestamp(int(info.get('onboardDate', 0)), unit='ms')
        if lo <= onboard <= hi:
            meta.append((m['base'], m['symbol'], onboard))
    meta = sorted(set(meta), key=lambda x: x[2])
    pd.DataFrame(meta, columns=['base', 'symbol', 'onboard']).to_csv(os.path.join(out, 'listings.csv'), index=False)
    print(f'{cohort}: {len(meta)} listings', flush=True)
    for base, sym, onboard in meta:
        since = int((onboard - pd.Timedelta(days=1)).timestamp() * 1000)
        until = since + (DAYS + 2) * 86_400_000
        path = os.path.join(out, f'{base}_1d.csv')
        if not os.path.exists(path):
            bars = ex.fetch_ohlcv(sym, '1d', since=since, limit=DAYS)
            px = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            px['timestamp'] = pd.to_datetime(px['timestamp'], unit='ms')
            px.to_csv(path, index=False)
        fpath = os.path.join(out, f'{base}_funding.csv')
        if not os.path.exists(fpath):
            # Funding intervals can be 1h/4h/8h, so page until the whole span is covered.
            rows, s = [], since
            while s < until:
                fr = ex.fetch_funding_rate_history(sym, since=s, limit=1000)
                if not fr:
                    break
                rows += [(x['timestamp'], x['fundingRate']) for x in fr]
                if fr[-1]['timestamp'] + 1 <= s:
                    break
                s = fr[-1]['timestamp'] + 1
            f = pd.DataFrame(rows, columns=['timestamp', 'funding_rate']).drop_duplicates('timestamp')
            f['timestamp'] = pd.to_datetime(f['timestamp'], unit='ms')
            f.to_csv(fpath, index=False)
        time.sleep(0.15)
    print('done', flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
