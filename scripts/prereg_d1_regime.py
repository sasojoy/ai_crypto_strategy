"""
PRE-REGISTERED P3 (RESEARCH_FINDINGS.md 2026-11-08): is the sign of the
D1 (24-bar run-up / ATR) effect on v7 R determined by the funding regime?

Data: scripts/entry_location_trades.csv (dev, D1 quintiles already
assigned) and holdout_entry_location_trades.csv (2026, frozen cuts from
entry_location_cuts.json). Regime per trade: BTC funding 30-day
annualised as of the day BEFORE entry (causal), on = > 10%.

Hypothesis: eff_off = meanR(Q5) - meanR(Q1) among gate-off trades < 0, and
interaction eff_off - eff_on < 0. Test: week-cluster bootstrap (resample
weeks, 10,000x), one-sided p < 0.05 for BOTH in dev, plus eff_off < 0 in
both 2020-23 and 2024-25. Holdout (only if dev passes): 2026 eff_off < 0,
cluster-bootstrap p < 0.05. Descriptive: D1 effect by ann30 quartile.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
THRESH, N_BOOT, ALPHA = 0.10, 10000, 0.05
SPLIT = pd.Timestamp('2024-01-01')


def btc_ann30():
    a = pd.read_csv(os.path.join(CACHE, 'funding_basket', 'BTC_USDT_funding.csv'))
    b = pd.read_csv(os.path.join(CACHE, 'holdout_2026', 'BTC_USDT_funding.csv'))
    f = pd.concat([a, b])
    f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.floor('s')
    f = f.drop_duplicates('timestamp').set_index('timestamp').sort_index()['funding_rate']
    daily = f.resample('1D').sum()
    return daily.rolling(30).mean() * 365


def load():
    with open(os.path.join(S, 'entry_location_cuts.json')) as fh:
        cuts = json.load(fh)['cuts']['runup24_atr']
    dev = pd.read_csv(os.path.join(S, 'entry_location_trades.csv'), parse_dates=['time'])
    dev['q'] = np.searchsorted(cuts, dev['runup24_atr'].values, side='right')
    hold = pd.read_csv(os.path.join(S, 'holdout_entry_location_trades.csv'), parse_dates=['time'])
    hold['q'] = np.searchsorted(cuts, hold['runup24_atr'].values, side='right')
    ann = btc_ann30()
    for d in (dev, hold):
        day_before = d['time'].dt.floor('D') - pd.Timedelta(days=1)
        d['ann30'] = ann.reindex(day_before).values
        d['on'] = d['ann30'] > THRESH
        d['week'] = (d['time'] - pd.to_timedelta((d['time'].dt.dayofweek + 1) % 7, unit='D')).dt.floor('D')
    return dev.dropna(subset=['ann30']), hold.dropna(subset=['ann30'])


def eff(d):
    return d.r[d.q == 4].mean() - d.r[d.q == 0].mean()


def week_aggregates(d):
    """Per-week sums/counts of R in (Q5, Q1) x (off, on) -> array (W, 8)."""
    cols = []
    for on in (False, True):
        for q in (4, 0):
            m = (d.on == on) & (d.q == q)
            g = d[m].groupby('week').r.agg(['sum', 'count'])
            cols += [g['sum'], g['count']]
    a = pd.concat(cols, axis=1).reindex(d.week.unique()).fillna(0.0)
    return a.values  # [s5off, n5off, s1off, n1off, s5on, n5on, s1on, n1on]


def _eff_from(agg, use_on):
    o = 4 if use_on else 0
    with np.errstate(invalid='ignore', divide='ignore'):
        return agg[..., o] / agg[..., o + 1] - agg[..., o + 2] / agg[..., o + 3]


def cluster_boot(d, kind, rng):
    """Week-cluster bootstrap (resample weeks with replacement, N_BOOT times).
    kind 'off' -> eff_off ; 'inter' -> eff_off - eff_on. Returns (real, one-sided p for stat < 0)."""
    agg = week_aggregates(d)
    W = len(agg)
    idx = rng.integers(0, W, (N_BOOT, W))
    tot = agg[idx].sum(axis=1)  # (N_BOOT, 8)
    real_tot = agg.sum(axis=0)
    if kind == 'off':
        stat, real = _eff_from(tot, False), _eff_from(real_tot, False)
    else:
        stat, real = _eff_from(tot, False) - _eff_from(tot, True), _eff_from(real_tot, False) - _eff_from(real_tot, True)
    stat = stat[np.isfinite(stat)]
    return float(real), float((stat >= 0).mean())


def describe(d, label):
    off, on = d[~d.on], d[d.on]
    print(f'  {label}: n={len(d)}  gate-off n={len(off)} eff_off={eff(off):+.3f}R  gate-on n={len(on)} eff_on={eff(on):+.3f}R  '
          f'(meanR off {off.r.mean():+.3f}, on {on.r.mean():+.3f})')


def main():
    rng = np.random.default_rng(20261108)
    dev, hold = load()
    print(f'DEV trades with regime: {len(dev)}  (gate-on share {dev.on.mean()*100:.0f}%)')
    describe(dev, 'dev pooled')
    for lab, m in (('2020-23', dev.time < SPLIT), ('2024-25', dev.time >= SPLIT)):
        describe(dev[m], lab)
    r1, p1 = cluster_boot(dev, 'off', rng)
    r2, p2 = cluster_boot(dev, 'inter', rng)
    cons = eff(dev[(dev.time < SPLIT) & ~dev.on]) < 0 and eff(dev[(dev.time >= SPLIT) & ~dev.on]) < 0
    passed = bool(r1 < 0 and p1 < ALPHA and r2 < 0 and p2 < ALPHA and cons)
    print(f'\n  eff_off = {r1:+.3f}R  cluster p={p1:.4f}   interaction off-on = {r2:+.3f}R  cluster p={p2:.4f}   both-period eff_off<0: {cons}')
    print(f'  -> DEV {"PASS" if passed else "FAIL"}')

    print('\n  descriptive: D1 effect (Q5-Q1) by ann30 quartile, dev')
    dev['ann_q'] = pd.qcut(dev['ann30'], 4, labels=['Q1 lowest', 'Q2', 'Q3', 'Q4 highest'])
    for lab, g in dev.groupby('ann_q', observed=True):
        print(f'    ann30 {lab:11s} range {g.ann30.min()*100:5.1f}%..{g.ann30.max()*100:5.1f}%  n={len(g)}  eff={eff(g):+.3f}R  meanR={g.r.mean():+.3f}')

    print(f'\n2026 ({"one-shot test" if passed else "descriptive, dev failed"}): trades {len(hold)} (gate-on share {hold.on.mean()*100:.0f}%)')
    describe(hold, '2026')
    if (~hold.on).sum() >= 50:
        rh, ph = cluster_boot(hold, 'off', rng)
        print(f'  2026 eff_off = {rh:+.3f}R  cluster p={ph:.4f}  -> {("PASS" if (rh < 0 and ph < ALPHA) else "FAIL") if passed else "descriptive"}')
    hold['ann_q'] = pd.cut(hold['ann30'], [-1, 0.05, 0.10, 0.20, 10], labels=['<5%', '5-10%', '10-20%', '>20%'])
    for lab, g in hold.groupby('ann_q', observed=True):
        print(f'    2026 ann30 {lab:6s} n={len(g)}  eff={eff(g):+.3f}R  meanR={g.r.mean():+.3f}')


if __name__ == '__main__':
    main()
