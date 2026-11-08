"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向A：時段結構", 2026-10-17).
DEV WINDOW ONLY (< 2026-01-01). 50 coins = 15-coin basket + 35 unseen.

Hourly log return per coin (close / prev close, Binance 1H bars, UTC),
equal-weighted across available coins per hour -> one "market" series.

  H_A1  (a priori)  US session 13:00-21:00 UTC (bars 13..20) mean > rest.
  H_A2  (data-driven, OOS) rank 24 hours by EW mean in 2020-23; top-8 =
        good, bottom-8 = bad (frozen); in 2024-25 good - bad > 0.

Test statistic: daily gap series (in-set mean - out-of-set mean, EW),
one-sided t-test and 10,000x daily block bootstrap (p = share of
bootstrap means <= 0). Pass (each): gap > 0, p < 0.025, same sign in
2020-23 and 2024-25 (H_A1), same sign in the 15-coin and 35-coin subsamples.
Only after a pass: economic value (hold EW long in good hours only vs
buy-and-hold, taker 0.14% / maker 0.04% per daily round trip) and
descriptive hour-of-day volatility / weekday / funding-boundary tables.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_coin_personality import ORIGINAL, MAJORS, load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
SPLIT = pd.Timestamp('2024-01-01')
N_BOOT = 10000
ALPHA = 0.025
US_HOURS = list(range(13, 21))
SEED = 20261017


def build():
    basket = ORIGINAL + MAJORS
    others = sorted(set(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv')) - set(MAJORS))
    cols = {}
    for b in basket + others:
        df = load(b).set_index('timestamp')
        cols[b] = np.log(df['close']).diff()
    r = pd.DataFrame(cols)
    r = r[(r.index >= '2020-01-01') & (r.index < '2026-01-01')]
    sample = {b: ('15' if b in basket else '35') for b in r.columns}
    return r, sample


def ew(r, cols):
    return r[cols].mean(axis=1)


def daily_gap(m, hours_in):
    """m: EW hourly return series. One gap per day: mean(in) - mean(out)."""
    d = pd.DataFrame({'r': m, 'h': m.index.hour, 'day': m.index.floor('D')})
    d['in'] = d['h'].isin(hours_in)
    g = d.groupby('day').apply(lambda x: x.loc[x['in'], 'r'].mean() - x.loc[~x['in'], 'r'].mean())
    return g.dropna()


def test(gaps, rng):
    g = gaps.values
    n = len(g)
    mean = g.mean()
    t = mean / (g.std(ddof=1) / np.sqrt(n))
    boot = rng.choice(g, size=(N_BOOT, n), replace=True).mean(axis=1)
    p = (boot <= 0).mean()
    return mean, t, p, n


def report(name, m_all, m15, m35, hours_in, rng, split_required):
    print(f'\n=== {name}  hours_in={hours_in} ===')
    out = {}
    for label, m in [('all', m_all), ('15', m15), ('35', m35)]:
        for per, mask in [('2020-23', m.index < SPLIT), ('2024-25', m.index >= SPLIT), ('full', np.ones(len(m), bool))]:
            mean, t, p, n = test(daily_gap(m[mask], hours_in), rng)
            out[(label, per)] = (mean, p)
            print(f'  {label:>3} {per:8} gap/hour={mean*1e4:+7.2f} bp  t={t:+5.2f}  p={p:.4f}  days={n}')
    return out


def economic(m_all, hours_in):
    print('\n  Economic value (EW long in good hours only vs buy-and-hold, dev window):')
    d = pd.DataFrame({'r': m_all, 'h': m_all.index.hour})
    strat = d['r'].where(d['h'].isin(hours_in), 0.0)
    days = (d.index[-1] - d.index[0]).days / 365.25
    bh = d['r'].sum() / days
    for cost_name, cost in [('no cost', 0.0), ('taker 0.14%', 0.0014), ('maker 0.04%', 0.0004)]:
        n_days = d.index.floor('D').nunique()
        ann = (strat.sum() - cost * n_days) / days
        daily = strat.groupby(d.index.floor('D')).sum() - cost
        sharpe = daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else float('nan')
        print(f'    {cost_name:12} ann log-return={ann*100:+6.1f}%  Sharpe={sharpe:+.2f}   (buy-and-hold {bh*100:+6.1f}%)')


def descriptive(m_all, r):
    print('\n  Descriptive: hour-of-day (dev window, EW market series)')
    d = pd.DataFrame({'r': m_all, 'h': m_all.index.hour, 'wd': m_all.index.dayofweek})
    tab = d.groupby('h')['r'].agg(mean=lambda x: x.mean() * 1e4, med_abs=lambda x: x.abs().median() * 1e4)
    for h, row in tab.iterrows():
        print(f'    h={h:02d}  mean={row["mean"]:+6.2f} bp  med|r|={row["med_abs"]:6.1f} bp')
    print('  Weekday (0=Mon): mean bp / median |r| bp')
    tab = d.groupby('wd')['r'].agg(mean=lambda x: x.mean() * 1e4, med_abs=lambda x: x.abs().median() * 1e4)
    for wd, row in tab.iterrows():
        print(f'    wd={wd}  mean={row["mean"]:+6.2f}  med|r|={row["med_abs"]:6.1f}')
    print('  Funding boundary (settlement at 00/08/16 UTC): hour ending at settlement vs hour after')
    before = d[d['h'].isin([23, 7, 15])]['r']
    after = d[d['h'].isin([0, 8, 16])]['r']
    print(f'    hour before settlement mean={before.mean()*1e4:+6.2f} bp   hour after mean={after.mean()*1e4:+6.2f} bp')


def main():
    rng = np.random.default_rng(SEED)
    r, sample = build()
    c15 = [c for c in r.columns if sample[c] == '15']
    c35 = [c for c in r.columns if sample[c] == '35']
    m_all, m15, m35 = ew(r, list(r.columns)), ew(r, c15), ew(r, c35)
    print(f'coins: {len(r.columns)} (15-basket {len(c15)}, unseen {len(c35)}); hours {len(r)}; {r.index[0]} .. {r.index[-1]}')

    # H_A1 -- a priori US session
    a1 = report('H_A1 US session 13-21 UTC', m_all, m15, m35, US_HOURS, rng, True)
    pass_a1 = (a1[('all', 'full')][0] > 0 and a1[('all', 'full')][1] < ALPHA
               and a1[('all', '2020-23')][0] > 0 and a1[('all', '2024-25')][0] > 0
               and a1[('15', 'full')][0] > 0 and a1[('35', 'full')][0] > 0)
    print(f'  -> H_A1 {"PASS" if pass_a1 else "FAIL"}')

    # H_A2 -- rank hours on 2020-23, confirm on 2024-25
    disc = m_all[m_all.index < SPLIT]
    by_hour = disc.groupby(disc.index.hour).mean().sort_values(ascending=False)
    good, bad = sorted(by_hour.index[:8].tolist()), sorted(by_hour.index[-8:].tolist())
    print(f'\n=== H_A2 ranked on 2020-23: good={good} bad={bad} ===')
    conf = {}
    for label, m in [('all', m_all), ('15', m15), ('35', m35)]:
        mc = m[m.index >= SPLIT]
        d = pd.DataFrame({'r': mc, 'h': mc.index.hour, 'day': mc.index.floor('D')})
        g = d.groupby('day').apply(lambda x: x.loc[x['h'].isin(good), 'r'].mean() - x.loc[x['h'].isin(bad), 'r'].mean()).dropna()
        mean, t, p, n = test(g, rng)
        conf[label] = (mean, p)
        print(f'  {label:>3} 2024-25 good-bad gap/hour={mean*1e4:+7.2f} bp  t={t:+5.2f}  p={p:.4f}  days={n}')
    pass_a2 = conf['all'][0] > 0 and conf['all'][1] < ALPHA and conf['15'][0] > 0 and conf['35'][0] > 0
    print(f'  -> H_A2 {"PASS" if pass_a2 else "FAIL"}')

    if pass_a1:
        economic(m_all, US_HOURS)
    if pass_a2:
        economic(m_all, good)
    descriptive(m_all, r)


if __name__ == '__main__':
    main()
