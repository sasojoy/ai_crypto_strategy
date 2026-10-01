"""
Regime switching between strategy "experts" (user request 2026-10-01: keep
searching, use ALL history including 2026; goal = something that worked in
every period). Uses 2020-01 .. 2026-09, so there is no holdout left for
this -- it is an exploratory search, judged by consistency across years
and across the parameter grid rather than by one lucky setting.

Weekly return streams (week = Monday 00:00 UTC to the next Monday):
  V7      v7 signal, 1H close-entry proxy, 50 coins, sum of R per week
  BRK4H   4H breakout / mid-range stop / 3R, 50 coins, sum of R per week
  XSM7    cross-sectional momentum, 7-day rank, weekly, 50 coins
  XSR7    cross-sectional REVERSAL, 7-day rank (long losers, short winners)
  XSM28 / XSR28  the same with a 28-day rank
Each stream is volatility-normalized causally (trailing 26-week std,
lagged one week, target 1% per week) so they can be compared and mixed.

Meta rules (all reported, none tuned):
  BEST1  hold the single stream with the best trailing-L-week mean, if > 0;
         else cash
  POSEW  equal weight across streams whose trailing-L-week mean is > 0
  STATIC equal weight across all streams all the time (benchmark)
  L in {4, 8, 13, 26} weeks.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_coin_personality import ORIGINAL, MAJORS, load
from fetch_holdout_2026 import coins
from prereg_xs_momentum import weekly_inputs, backtest
import brk4h

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
HOLD = os.path.join(CACHE, 'holdout_2026')
LOOKBACKS = [int(x) for x in sys.argv[1].split(',')] if len(sys.argv) > 1 else [4, 8, 13, 26]


def week_of(t):
    t = pd.Timestamp(t)
    return t.normalize() - pd.Timedelta(days=t.dayofweek) - pd.Timedelta(days=1)  # the Sunday before


def full_daily_panel():
    basket = ORIGINAL + MAJORS
    closes, funding = {}, {}
    for b in coins():
        dev = load(b).set_index('timestamp')['close'].resample('1D').last()
        dev = dev[dev.index < '2026-01-01']
        h = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
        full = h.groupby(h['timestamp'].dt.floor('D')).size()
        hd = h.set_index('timestamp')['close'].resample('1D').last()
        hd = hd[(hd.index >= '2026-01-01') & (full.reindex(hd.index).fillna(0) == 24)]
        closes[b] = pd.concat([dev, hd])
        fdir = 'funding_basket' if b in basket else 'funding_universe'
        f1 = pd.read_csv(os.path.join(CACHE, fdir, f'{b}_USDT_funding.csv'))
        f2 = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_funding.csv'))
        f = pd.concat([f1, f2])
        f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
        funding[b] = f.drop_duplicates('timestamp').set_index('timestamp')['funding_rate'].sort_index()
    return pd.DataFrame(closes), funding


def xs_streams(px, funding):
    out = {}
    for lb in (7, 28):
        weeks = weekly_inputs(px, funding, lb)
        out[f'XSM{lb}'] = backtest(weeks, list(px.columns), lambda sc: list(sc.sort_values().index))
        out[f'XSR{lb}'] = backtest(weeks, list(px.columns), lambda sc: list(sc.sort_values(ascending=False).index))
    return out


def trade_streams():
    # V7: dev (prereg_vol_trend population) + 2026 (holdout_short_crowding trades, frozen cutoffs)
    from prereg_vol_trend import build as build_v7_dev
    v7d = build_v7_dev()[['coin', 'time', 'r']]
    v7h = pd.read_csv(os.path.join(ROOT, 'scripts', 'holdout_short_crowding_trades.csv'), parse_dates=['time'])[['coin', 'time', 'r']]
    v7 = pd.concat([v7d, v7h[v7h.time >= '2026-01-01']])
    # BRK4H: dev from the squeeze study's control arm + 2026 via brk4h.signals
    sq = pd.read_csv(os.path.join(ROOT, 'scripts', 'squeeze_breakout_trades.csv'), parse_dates=['time'])
    bd = sq[(sq.kind == 'control') & (sq.exit == 'fixed3R')][['coin', 'time', 'r']]
    rows = []
    for b in coins():
        h = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
        for t, sgn, status, r in brk4h.signals(brk4h.to_4h(h), pd.Timestamp('2026-01-01')):
            if status != 'OPEN':
                rows.append(dict(coin=b, time=t, r=r))
    brk = pd.concat([bd, pd.DataFrame(rows)])
    out = {}
    for name, d in (('V7', v7), ('BRK4H', brk)):
        out[name] = d.groupby(d.time.map(week_of)).r.sum()
    return out


def normalize(s, target=0.01):
    vol = s.rolling(26, min_periods=13).std().shift(1)
    return (s * target / vol).dropna()


def ann_stats(r):
    if len(r) < 4 or r.std() == 0:
        return np.nan, np.nan
    return r.mean() * 52 * 100, r.mean() / r.std() * np.sqrt(52)


def main():
    px, funding = full_daily_panel()
    raw = {**xs_streams(px, funding), **trade_streams()}
    streams = pd.DataFrame({k: normalize(v) for k, v in raw.items()})
    streams = streams[streams.index >= '2020-07-01'].fillna(0.0)
    years = sorted(set(streams.index.year))

    def by_year(r):
        cells = []
        for y in years:
            a, s = ann_stats(r[r.index.year == y])
            cells.append(f"{y}:{s:+5.2f}" if not np.isnan(s) else f"{y}:  n/a")
        q = [ann_stats(r[(r.index >= f'2026-{m:02d}-01') & (r.index < f'2026-{m+3:02d}-01')])[1] for m in (1, 4, 7)]
        a, s = ann_stats(r)
        return f"all Sharpe {s:+5.2f} ann {a:+6.1f}% | " + ' '.join(cells) + f" | 26Q1/Q2/Q3 {q[0]:+5.2f} {q[1]:+5.2f} {q[2]:+5.2f}"

    print('=' * 150 + '\nSINGLE STREAMS (vol-normalized to ~1%/week). Sharpe by year')
    for c in streams.columns:
        print(f"  {c:8s} {by_year(streams[c])}")
    print(f"  {'STATIC':8s} {by_year(streams.mean(axis=1))}")

    print('\n' + '=' * 150 + '\nMETA RULES (selection uses only weeks before the current one)')
    for L in LOOKBACKS:
        trail = streams.rolling(L).mean().shift(1)
        best = trail.fillna(-np.inf).idxmax(axis=1)  # first L weeks have no history -> cash below
        best_val = trail.max(axis=1)
        best1 = pd.Series([streams.at[w, best[w]] if (pd.notna(best_val[w]) and best_val[w] > 0) else 0.0
                           for w in streams.index], index=streams.index)
        pos = (trail > 0)
        posew = (streams * pos).sum(axis=1) / pos.sum(axis=1).replace(0, np.nan)
        posew = posew.fillna(0.0)
        print(f"  BEST1 L={L:2d}  {by_year(best1)}")
        print(f"  POSEW L={L:2d}  {by_year(posew)}")
        if L == 8:
            print('    BEST1 L=8 picks by year: ' + ' '.join(
                f"{y}:{best[(best.index.year == y) & (best_val > 0)].value_counts().idxmax() if ((best.index.year == y) & (best_val > 0)).any() else 'cash'}"
                for y in years))
    streams.to_csv(os.path.join(ROOT, 'scripts', 'regime_switch_streams.csv'))


if __name__ == '__main__':
    main()
