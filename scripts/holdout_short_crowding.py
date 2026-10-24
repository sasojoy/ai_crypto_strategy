"""
HOLDOUT TEST (2026-01-01 onward), pre-registered in RESEARCH_FINDINGS.md
(commit 3ac5767) before the holdout data was fetched. Run ONCE.

Short-crowding risk reallocation for the v7 signal: shorts in the
short-crowded tercile get 0.5x risk, renormalized among shorts (mean short
risk = 1); longs unchanged.

Everything calibrated on the dev window and frozen:
  volume cutoff  = each coin's 67th percentile of dev-window signal
                   volume ratios (the top-tercile gate)
  crowding T3    = each coin's 67th percentile of 2020-23 short crowding
Pass (both required):
  (1) reallocated total R > baseline total R in the 15-coin basket AND in
      the 35 unseen coins, separately;
  (2) pooled 50 coins: crowded shorts' avgR < other shorts' avgR.
Only signals from 2026-01-01 whose 7-day holding window is complete.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi, find_triggers
from dev_momentum_continuation import flip
from dev_coin_personality import ORIGINAL, MAJORS, load
from dev_momentum_universe import load_universe_1h
from dev_momentum_partial_tp import simulate
from dev_momentum_pullback_entry import MAX_HOLD
from dev_short_crowding_risk import build as build_dev

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
HOLD = os.path.join(CACHE, 'holdout_2026')
HOLDOUT_START = pd.Timestamp('2026-01-01')


def prep(df):
    df = df.copy()
    df['rsi'] = compute_rsi(df['close'])
    df['atr'] = compute_atr(df)
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    return df


def frozen_thresholds(bases, loader, fund_dir):
    vol_cut = {}
    for b in bases:
        df = prep(loader(b))
        vr = [df['vol_ratio'].iloc[i] for i, _ in find_triggers(df) if not np.isnan(df['vol_ratio'].iloc[i])]
        vol_cut[b] = np.quantile(vr, 2 / 3)
    dev = build_dev(bases, loader, fund_dir)
    s = dev[(dev.sgn == -1) & (dev.period == 'disc')]
    crowd_cut = s.groupby('coin')['crowd'].quantile(2 / 3).to_dict()
    return vol_cut, crowd_cut


def holdout_trades(b, vol_cut, crowd_cut):
    df = prep(pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
              .sort_values('timestamp').reset_index(drop=True))
    f = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_funding.csv'))
    f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
    f = f.sort_values('timestamp')
    f['f24'] = f['funding_rate'].rolling(3).mean()
    c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
    rows = []
    for i, rev in find_triggers(df):
        t = pd.Timestamp(ts[i])
        if t < HOLDOUT_START or i + 1 + MAX_HOLD > len(df) or np.isnan(atr[i]):
            continue
        if not df['vol_ratio'].iloc[i] > vol_cut[b]:
            continue
        sgn = 1 if flip(rev) == 'long' else -1
        prior = f[f['timestamp'] <= t + pd.Timedelta(hours=1)]
        f24 = prior['f24'].iloc[-1] if len(prior) else np.nan
        crowded = bool(sgn == -1 and b in crowd_cut and not np.isnan(f24) and -f24 > crowd_cut[b])
        rows.append(dict(coin=b, time=t, sgn=sgn, crowded=crowded, r=simulate(c, h, l, i, sgn, atr[i])))
    return rows


def evaluate(d, label):
    longs, shorts = d[d.sgn == 1], d[d.sgn == -1]
    w = np.where(shorts.crowded, 0.5, 1.0)
    base = d.r.sum()
    new = longs.r.sum() + ((shorts.r * w).sum() / w.mean() if len(shorts) else 0.0)
    print(f"  {label:16s} signals {len(d):4d} (longs {len(longs)}, shorts {len(shorts)}, crowded shorts {int(shorts.crowded.sum())})"
          f"  baseline {base:+7.1f}R  (longs {longs.r.sum():+6.1f}, shorts {shorts.r.sum():+6.1f})  -> reallocated {new:+7.1f}R")
    return new > base


def main():
    basket = ORIGINAL + MAJORS
    ufund = os.path.join(CACHE, 'funding_universe')
    others = sorted(f.split('_USDT_')[0] for f in os.listdir(ufund) if f.endswith('_funding.csv'))
    vc15, cc15 = frozen_thresholds(basket, load, os.path.join(CACHE, 'funding_basket'))
    vc35, cc35 = frozen_thresholds(others, load_universe_1h, ufund)
    d15 = pd.DataFrame([r for b in basket for r in holdout_trades(b, vc15, cc15)])
    d35 = pd.DataFrame([r for b in others for r in holdout_trades(b, vc35, cc35)])
    print(f"holdout window: {min(d15.time.min(), d35.time.min())} .. {max(d15.time.max(), d35.time.max())} (signal times)")
    ok15 = evaluate(d15, '15-coin basket')
    ok35 = evaluate(d35, '35 unseen coins')
    allx = pd.concat([d15, d35])
    sh = allx[allx.sgn == -1]
    gap_c, gap_o = sh.loc[sh.crowded, 'r'].mean(), sh.loc[~sh.crowded, 'r'].mean()
    ok_gap = gap_c < gap_o
    print(f"  pooled shorts: crowded n={int(sh.crowded.sum())} avgR={gap_c:+.3f}   others n={int((~sh.crowded).sum())} avgR={gap_o:+.3f}")
    print(f"\n  (1) basket improved: {ok15}   35 unseen improved: {ok35}   (2) crowded shorts worse: {ok_gap}")
    print(f"  HOLDOUT {'PASSES' if (ok15 and ok35 and ok_gap) else 'FAILS'}")
    allx.to_csv(os.path.join(ROOT, 'scripts', 'holdout_short_crowding_trades.csv'), index=False)


if __name__ == '__main__':
    main()
