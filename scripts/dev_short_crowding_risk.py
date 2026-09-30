"""
DEV-WINDOW ONLY (< 2026-01-01). Turns the pre-registered short-crowding
finding (prereg_short_crowding.py, passed p=0.0003 on 35 unseen coins) into
a RISK REALLOCATION rule, the way v6 / volume scaling were tested: never
drop a signal, give short signals in the short-crowded tercile (T3) half
risk and spread the freed risk so average risk is unchanged.

Rule (fixed, not tuned): T3 shorts weight 0.5, everything else 1.0, then
renormalized so the mean weight is 1 --
  B (primary)   renormalize within SHORTS only (freed risk goes to the
                other shorts). Largely implied by the H1 numbers already
                seen -- reported for completeness, not as new evidence.
  A (secondary) renormalize across ALL signals (freed risk also goes to
                longs) -- NOT implied by H1, depends on long-side quality.
Metric: normalized total R = sum(w*r)/mean(w) vs baseline sum(r), for
2020-23 and 2024-25, on the 15-coin basket (where the pattern was found)
and the 35 unseen coins; plus coins improved.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi
from dev_coin_personality import ORIGINAL, MAJORS, load
from dev_momentum_universe import load_universe_1h
from dev_momentum_pullback_entry import signals
from dev_momentum_partial_tp import simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
SPLIT = pd.Timestamp('2024-01-01')


def build(bases, loader, fund_dir):
    rows = []
    for b in bases:
        df = loader(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        f = pd.read_csv(os.path.join(fund_dir, f'{b}_USDT_funding.csv'))
        f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
        f['f24'] = f['funding_rate'].rolling(3).mean()
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        s = signals(df).copy()
        s['close_time'] = ts[s['i']] + np.timedelta64(1, 'h')
        s = pd.merge_asof(s.sort_values('close_time'), f[['timestamp', 'f24']].sort_values('timestamp'),
                          left_on='close_time', right_on='timestamp', direction='backward')
        for r in s.itertuples():
            if np.isnan(r.f24):
                continue
            rows.append(dict(coin=b, time=pd.Timestamp(ts[r.i]), sgn=r.sgn, crowd=-r.f24,
                             r=simulate(c, h, l, r.i, r.sgn, atr[r.i])))
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, 'disc', 'conf')
    d['T3'] = False
    for coin, g in d[d.sgn == -1].groupby('coin'):
        ref = g.loc[g.period == 'disc', 'crowd']
        if len(ref) >= 6:
            d.loc[g.index, 'T3'] = g['crowd'] > ref.quantile(2 / 3)
    return d


def report(d, label):
    print('=' * 110 + f'\n{label}: {d.coin.nunique()} coins, {len(d)} signals '
          f'(longs {int((d.sgn == 1).sum())}, shorts {int((d.sgn == -1).sum())}, crowded shorts {int(d.T3.sum())})')
    for p in ('disc', 'conf'):
        x = d[d.period == p]
        base = x.r.sum()
        longs, shorts = x[x.sgn == 1], x[x.sgn == -1]
        # B: within shorts
        ws = np.where(shorts.T3, 0.5, 1.0)
        b_total = longs.r.sum() + (shorts.r * ws).sum() / ws.mean()
        # A: across all signals
        wa = np.where(x.T3, 0.5, 1.0)
        a_total = (x.r * wa).sum() / wa.mean()
        print(f"  {p}: baseline {base:+8.1f}R  (longs {longs.r.sum():+7.1f}, shorts {shorts.r.sum():+7.1f}) | "
              f"B within-shorts {b_total:+8.1f}R ({(b_total/base-1)*100:+.1f}%) | "
              f"A all-signals {a_total:+8.1f}R ({(a_total/base-1)*100:+.1f}%)")

    def per_coin(g, mode):
        if mode == 'B':
            s = g[g.sgn == -1]
            if s.empty:
                return 0.0
            w = np.where(s.T3, 0.5, 1.0)
            return (s.r * w).sum() / w.mean() - s.r.sum()
        w = np.where(g.T3, 0.5, 1.0)
        return (g.r * w).sum() / w.mean() - g.r.sum()
    for mode in ('B', 'A'):
        gains = d.groupby('coin').apply(lambda g: per_coin(g, mode))
        print(f"  coins improved ({mode}): {(gains > 0).sum()}/{len(gains)}")


def main():
    basket = ORIGINAL + MAJORS
    d15 = build(basket, load, os.path.join(CACHE, 'funding_basket'))
    ufund = os.path.join(CACHE, 'funding_universe')
    others = sorted(f.split('_USDT_')[0] for f in os.listdir(ufund) if f.endswith('_funding.csv'))
    d35 = build(others, load_universe_1h, ufund)
    report(d15, '15-coin basket (pattern found here)')
    report(d35, '35 unseen coins')


if __name__ == '__main__':
    main()
