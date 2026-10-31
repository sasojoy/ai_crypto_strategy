"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向E：持倉比", 2026-10-24).
DEV WINDOW ONLY: 2021-12-01 .. 2025-12-31 (2026 untouched). 50 coins.

Data: data/backtest_cache/metrics/<SYM>USDT.csv (Binance 5-minute
positioning metrics): sum_toptrader_long_short_ratio (top traders'
POSITION ratio), count_toptrader_long_short_ratio (top traders' ACCOUNT
ratio), count_long_short_ratio (all accounts), sum_taker_long_short_vol_ratio.
Signal value for day d = last row at or before 23:55 UTC of day d. Entry
= daily close of day d (close of the 23:00 1H bar). Only the OI filter
of these metrics has been used before; the ratios are untested.

Per coin, each ratio is log-transformed and z-scored against its own
trailing 90-day mean/std (causal, >= 60 days of history).

  H_E1  follow top traders (time series): when |z_top_pos| > 1, position
        sign(z_top_pos), hold 5 days, no re-entry while in a trade.
        Return = dir * log(c[d+5]/c[d]) - funding paid over the hold
        (dir * sum of 8h rates) - 0.14 %. mean > 0.
  H_E2  fade the crowd (time series): same with dir = -sign(z_all_acct)
        when |z_all_acct| > 1.
  H_E3  cross-sectional (weekly): every Sunday close, rank the 50 coins
        by z_top_pos; long the top 20 %, short the bottom 20 %, each side
        0.5, 0.07 % per side on weight change, actual funding. Weekly
        return series; pass = annualised net return > 0 in BOTH 2021-23
        and 2024-25, for the 50-coin set AND the 35 unseen coins, and
        full-period Sharpe above 95 % of 1,000 random weekly rankings.

Inference for H_E1/H_E2: trade returns averaged per coin x entry-day
first, then one-sided t-test and 10,000x bootstrap (Bonferroni alpha
0.025). Pass = mean > 0, p < 0.025, same sign in 2021-23 and 2024-25,
same sign in the 15-coin basket and the 35 unseen coins. Breakdowns
(by side, by year, the other two ratios as descriptive signals) are
printed only after a pass. Nothing is re-tuned.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402
from prereg_xs_momentum import backtest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MET = os.path.join(ROOT, 'data', 'backtest_cache', 'metrics')
START, END = pd.Timestamp('2021-12-01'), pd.Timestamp('2026-01-01')
SPLIT = pd.Timestamp('2024-01-01')
ZWIN, ZMIN, ZCUT, HOLD = 90, 60, 1.0, 5
COST = 0.0014
N_BOOT, ALPHA, SEED = 10000, 0.025, 20261024
RATIOS = {'top_pos': 'sum_toptrader_long_short_ratio', 'top_acct': 'count_toptrader_long_short_ratio',
          'all_acct': 'count_long_short_ratio', 'taker': 'sum_taker_long_short_vol_ratio'}


def daily_metrics(base):
    m = pd.read_csv(os.path.join(MET, f'{base}USDT.csv'), parse_dates=['create_time'])
    m = m[m.create_time < END].set_index('create_time').sort_index()
    d = m[list(RATIOS.values())].resample('1D').last()
    d.columns = list(RATIOS.keys())
    z = pd.DataFrame(index=d.index)
    for k in RATIOS:
        x = np.log(d[k].replace(0, np.nan))
        z[k] = (x - x.rolling(ZWIN, min_periods=ZMIN).mean()) / x.rolling(ZWIN, min_periods=ZMIN).std()
    return z


def ts_trades(base, z, px, fund, col, sign):
    c = px[base].dropna()
    c = c[(c.index >= START) & (c.index < END)]
    zz = z[col].reindex(c.index)
    fd = fund[base].resample('1D').sum().reindex(c.index).fillna(0.0)
    rows, last_exit = [], pd.Timestamp('2000-01-01')
    idx = c.index
    for i in range(len(idx) - HOLD):
        t = idx[i]
        if t < last_exit or not np.isfinite(zz.iloc[i]) or abs(zz.iloc[i]) <= ZCUT:
            continue
        d = sign * np.sign(zz.iloc[i])
        r = d * np.log(c.iloc[i + HOLD] / c.iloc[i]) - d * fd.iloc[i + 1:i + HOLD + 1].sum() - COST
        rows.append((base, t, d, zz.iloc[i], r))
        last_exit = idx[i + HOLD]
    return pd.DataFrame(rows, columns=['coin', 'time', 'dir', 'z', 'r'])


def infer(x, rng):
    x = np.asarray(x, float)
    if len(x) < 30:
        return np.nan, np.nan, np.nan, len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, (N_BOOT, len(x))).mean(1)
    return x.mean(), t, (boot <= 0).mean(), len(x)


def run_ts(d, name, rng):
    print(f'\n=== {name} ===')
    res = {}
    for label, sub in [('all', d), ('15', d[d['sample'] == '15']), ('35', d[d['sample'] == '35'])]:
        for per in ['2021-23', '2024-25', 'full']:
            s = sub if per == 'full' else sub[sub.period == per]
            mean, t, p, n = infer(s.r, rng)
            res[(label, per)] = (mean, p)
            print(f'  {label:>3} {per:8} mean={mean*1e4:+7.1f} bp  t={t:+5.2f}  p={p:.4f}  trades={n}')
    ok = (res[('all', 'full')][0] > 0 and res[('all', 'full')][1] < ALPHA
          and res[('all', '2021-23')][0] > 0 and res[('all', '2024-25')][0] > 0
          and res[('15', 'full')][0] > 0 and res[('35', 'full')][0] > 0)
    print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}')
    if ok:
        for lab, m in [('long', d.dir > 0), ('short', d.dir < 0)]:
            print(f'    {lab:5s} n={m.sum()}  mean={d[m].r.mean()*1e4:+.1f} bp')
        for y, g in d.groupby(d.time.dt.year):
            print(f'    {y}: n={len(g)}  mean={g.r.mean()*1e4:+.1f} bp  win={(g.r>0).mean()*100:.0f}%')
    return ok


def main():
    rng = np.random.default_rng(SEED)
    px, fund = full_daily_panel()
    px = px[(px.index >= START) & (px.index < END)]
    basket = set(ORIGINAL + MAJORS)
    coins = [b for b in px.columns if os.path.exists(os.path.join(MET, f'{b}USDT.csv'))]
    zs = {b: daily_metrics(b) for b in coins}
    print(f'coins={len(coins)}  days={len(px)}  {px.index[0].date()}..{px.index[-1].date()}')

    for name, col, sign in [('H_E1 follow top-trader position ratio, 5-day hold, net', 'top_pos', +1),
                            ('H_E2 fade all-account ratio, 5-day hold, net', 'all_acct', -1)]:
        d = pd.concat([ts_trades(b, zs[b], px, fund, col, sign) for b in coins], ignore_index=True)
        d['sample'] = np.where(d.coin.isin(basket), '15', '35')
        d['period'] = np.where(d.time < SPLIT, '2021-23', '2024-25')
        d['day'] = d.time
        g = d.groupby(['coin', 'day', 'sample', 'period'], as_index=False).r.mean()
        g['time'] = g.day
        g['dir'] = 0
        ok = run_ts(g.assign(dir=d.groupby(['coin', 'day']).dir.first().values), name, rng)
        d.to_csv(os.path.join(ROOT, 'scripts', f'positioning_{col}_trades.csv'), index=False)

    print('\n=== H_E3 cross-sectional weekly on top-trader position z ===')
    zpanel = pd.DataFrame({b: zs[b]['top_pos'] for b in coins}).reindex(px.index)
    from prereg_xs_momentum import weekly_inputs
    res = {}
    for label, cs in [('50', coins), ('35', [b for b in coins if b not in basket])]:
        weeks = []
        for s, score, fwd, fsum in weekly_inputs(px[cs], {b: fund[b] for b in cs}, 7):
            # replace the momentum score with the positioning z known at the Sunday close
            zsc = zpanel.loc[s, cs].dropna()
            keep = [c for c in zsc.index if c in fwd.index]
            weeks.append((s, zsc[keep], fwd[keep], fsum[keep]))
        r = backtest(weeks, cs, lambda sc: list(sc.sort_values().index))
        for per, m in [('2021-23', r.index < SPLIT), ('2024-25', r.index >= SPLIT)]:
            res[(label, per)] = r[m].mean() * 52 * 100
        rand = []
        for _ in range(1000):
            rr = backtest(weeks, cs, lambda sc: list(sc.sample(frac=1, random_state=int(rng.integers(1e9))).index))
            rand.append(rr.mean() / rr.std() * np.sqrt(52))
        sh = r.mean() / r.std() * np.sqrt(52)
        res[(label, 'sh')] = (sh, np.percentile(rand, 95))
        print(f'  {label} coins: ann 2021-23 {res[(label, "2021-23")]:+.1f}%  2024-25 {res[(label, "2024-25")]:+.1f}%  Sharpe {sh:+.2f} (random p95 {res[(label, "sh")][1]:+.2f})')
    ok3 = all(res[(l, p)] > 0 for l in ('50', '35') for p in ('2021-23', '2024-25')) and res[('50', 'sh')][0] > res[('50', 'sh')][1]
    print(f'  -> H_E3 {"PASS" if ok3 else "FAIL"}')


if __name__ == '__main__':
    main()
