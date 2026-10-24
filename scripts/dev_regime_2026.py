"""
DESCRIPTIVE regime study (uses the 2026 holdout data, which has already
been spent by holdout_short_crowding.py -- this does NOT test or tune any
rule, it only describes). Question (2026-09-30): the v7 signal averaged
-0.22R per trade in 2026 Q2 and Q3 across 50 coins. What changed in the
market, and when?

15-coin basket, quarterly 2024Q1 .. 2026Q3 (dev caches before 2026, the
holdout_2026 fetch from 2026). Per quarter:
  market: median 1H ATR%, 24h variance ratio, lag-1 autocorr of 1H
          returns, mean pairwise corr of daily returns, median funding,
          BTC quarterly return and median 1H ADX
  signals: RSI crosses, share passing each coin's FROZEN dev volume cutoff,
          n / win / avgR (v7 close-entry proxy, SL 2 / TP 4 ATR)
  follow-through of v7 signals, in ATR units, in the trade direction:
          mean max favourable excursion (MFE) within 24h and 7d, mean
          directional return after 6h and 24h, share stopped out within 6h
"""
import os
import sys
from itertools import combinations

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import find_triggers
from dev_momentum_continuation import flip
from dev_coin_personality import ORIGINAL, MAJORS, load
from dev_momentum_partial_tp import simulate
from dev_momentum_pullback_entry import MAX_HOLD
from dev_momentum_adx_trend_filter import compute_adx
from holdout_short_crowding import prep, HOLD

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')
START = pd.Timestamp('2024-01-01')


def full_series(b):
    dev = load(b)
    hold = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
    df = pd.concat([dev[dev.timestamp < '2026-01-01'], hold[hold.timestamp >= '2026-01-01']])
    return prep(df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)[
        ['timestamp', 'open', 'high', 'low', 'close', 'volume']])


def funding_series(b):
    f1 = pd.read_csv(os.path.join(CACHE, 'funding_basket', f'{b}_USDT_funding.csv'))
    f2 = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_funding.csv'))
    f = pd.concat([f1, f2])
    f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
    return f.drop_duplicates('timestamp').set_index('timestamp')['funding_rate'].sort_index()


def vr24(close):
    lr = np.log(close).diff().dropna()
    return np.log(close).diff(24).dropna().var() / (24 * lr.var())


def main():
    coins = ORIGINAL + MAJORS
    market, sigs, daily = [], [], {}
    for b in coins:
        df = full_series(b)
        dev = df[df.timestamp < '2026-01-01']
        vr_dev = [dev['vol_ratio'].iloc[i] for i, _ in find_triggers(dev) if not np.isnan(dev['vol_ratio'].iloc[i])]
        vol_cut = np.quantile(vr_dev, 2 / 3)
        df['adx'] = compute_adx(df)
        df['q'] = df.timestamp.dt.to_period('Q')
        daily[b] = df.set_index('timestamp')['close'].resample('1D').last().pct_change()
        fund = funding_series(b)
        for q, g in df[df.timestamp >= START].groupby('q'):
            lr = np.log(g['close']).diff()
            fq = fund[(fund.index >= q.start_time) & (fund.index <= q.end_time)]
            market.append(dict(coin=b, q=q, atr_pct=(g['atr'] / g['close']).median() * 100, vr24=vr24(g['close']),
                               ac1=lr.autocorr(1), funding=fq.median() * 100 if len(fq) else np.nan,
                               adx=g['adx'].median(), ret=g['close'].iloc[-1] / g['close'].iloc[0] - 1))
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        for i, rev in find_triggers(df):
            t = pd.Timestamp(ts[i])
            if t < START or np.isnan(atr[i]) or i + 1 + MAX_HOLD > len(df):
                continue
            sgn = 1 if flip(rev) == 'long' else -1
            passed = df['vol_ratio'].iloc[i] > vol_cut
            rec = dict(coin=b, q=t.to_period('Q'), sgn=sgn, passed=passed)
            if passed:
                a = atr[i]
                fav24 = (h[i + 1:i + 25].max() - c[i]) / a if sgn > 0 else (c[i] - l[i + 1:i + 25].min()) / a
                fav7d = (h[i + 1:i + 169].max() - c[i]) / a if sgn > 0 else (c[i] - l[i + 1:i + 169].min()) / a
                sl = c[i] - sgn * 2 * a
                early_stop = (l[i + 1:i + 7] <= sl).any() if sgn > 0 else (h[i + 1:i + 7] >= sl).any()
                rec.update(r=simulate(c, h, l, i, sgn, a), mfe24=fav24, mfe7d=fav7d,
                           dir6=sgn * (c[i + 6] - c[i]) / a, dir24=sgn * (c[i + 24] - c[i]) / a, stop6=early_stop)
            sigs.append(rec)
    m, s = pd.DataFrame(market), pd.DataFrame(sigs)

    dd = pd.DataFrame(daily)
    corr_q = {}
    for q, g in dd[dd.index >= START].groupby(dd[dd.index >= START].index.to_period('Q')):
        cm = g.corr()
        corr_q[q] = np.mean([cm.loc[a, b] for a, b in combinations(coins, 2)])

    pd.set_option('display.width', 220)
    btc = m[m.coin == 'BTC'].set_index('q')
    mk = m.groupby('q').agg(atr_pct=('atr_pct', 'median'), vr24=('vr24', 'median'), ac1=('ac1', 'median'),
                            funding=('funding', 'median'), adx=('adx', 'median'))
    mk['coin_corr'] = pd.Series(corr_q)
    mk['btc_ret%'] = btc['ret'] * 100
    mk['btc_adx'] = btc['adx']
    print('=' * 120 + '\nMARKET (15 coins, medians across coins)')
    print(mk.round(4).to_string())

    p = s[s.passed]
    sg = s.groupby('q').agg(rsi_crosses=('passed', 'size'), pass_pct=('passed', 'mean'))
    sg['pass_pct'] *= 100
    pg = p.groupby('q').agg(n=('r', 'size'), win=('r', lambda x: (x > 0).mean() * 100), avgR=('r', 'mean'),
                            mfe24=('mfe24', 'mean'), mfe7d=('mfe7d', 'mean'), dir6=('dir6', 'mean'),
                            dir24=('dir24', 'mean'), stop6=('stop6', 'mean'))
    pg['stop6'] *= 100
    pg['long_avgR'] = p[p.sgn == 1].groupby('q').r.mean()
    pg['short_avgR'] = p[p.sgn == -1].groupby('q').r.mean()
    print('\n' + '=' * 120 + '\nV7 SIGNALS (frozen dev volume cutoff). MFE / dir in ATR units in the trade direction; stop6 = % stopped within 6h')
    print(sg.join(pg).round(3).to_string())


if __name__ == '__main__':
    main()
