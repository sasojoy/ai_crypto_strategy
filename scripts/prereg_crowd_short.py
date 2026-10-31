"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向H：群眾做多擁擠→只做空", 2026-10-24).
DEV WINDOW ONLY: 2021-12-01 .. 2025-12-31 (2026 untouched). 50 coins.

Claim under test: after the crowd is crowded LONG, the coin falls over the
next 5 days. The all-account long/short ratio (direction E) has already
been seen on both the dev window and 2026, so a short-only version of it
cannot be tested on the same data. Instead the same claim is tested on
three crowding indicators that have NOT been used in this form before:

  H_H1  funding crowding: 3-day mean of the 8h funding rate (9 settlements),
        z vs its own trailing 90 days (causal, >= 60 d); z > 1 AND the
        3-day mean > 0.01 % (above the default rate)  -> short
  H_H2  OI build-up into a rally: z of the 5-day log change of open
        interest (daily last) > 1 AND the same 5-day price return > 0 -> short
  H_H3  aggressive buying: daily mean of log(5-min taker buy/sell volume
        ratio), 3-day mean, z > 1 -> short

Common: signal from day d data (metrics up to 23:55 UTC, funding settled
by d), entry at the close of day d, SHORT ONLY, hold 5 days, no re-entry
while in a trade. net = -log(c[d+5]/c[d]) + funding received over the
hold - 0.14 %; price = -log(c[d+5]/c[d]) - 0.14 % (no funding).

Reference, NOT a test: H_E2 short side (all-account ratio z > 1 -> short)
was +92.4 bp in dev and +75.7 bp in 2026, already seen.

Inference per hypothesis: one-sided t-test and 10,000x bootstrap on net,
alpha = 0.05 / 3 = 0.0167. Pass = net mean > 0, p < alpha, same sign in
2021-23 and 2024-25, same sign in the 15-coin basket and the 35 unseen
coins, AND price mean > 0 (otherwise it is carry, not reversal).
After a pass only: by year, overlap with the all-account ratio signal
(share of entries with z_all > 1) and the sub-sample with z_all <= 1.
Nothing is re-tuned.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MET = os.path.join(ROOT, 'data', 'backtest_cache', 'metrics')
START, END = pd.Timestamp('2021-12-01'), pd.Timestamp('2026-01-01')
SPLIT = pd.Timestamp('2024-01-01')
ZWIN, ZMIN, ZCUT, HOLD = 90, 60, 1.0, 5
COST, FUND_MIN = 0.0014, 1e-4
N_BOOT, ALPHA, SEED = 10000, 0.05 / 3, 20261024
NAMES = {'H1': 'H_H1 funding crowding (3d mean z>1 & >0.01%), short 5d',
         'H2': 'H_H2 OI build-up into a rally (5d dOI z>1 & ret5>0), short 5d',
         'H3': 'H_H3 aggressive taker buying (3d mean log ratio z>1), short 5d'}


def zscore(x):
    sd = x.rolling(ZWIN, min_periods=ZMIN).std().replace(0, np.nan)
    return (x - x.rolling(ZWIN, min_periods=ZMIN).mean()) / sd


def signals(base, px, fund, end):
    """Boolean short signals per day plus the all-account ratio z (for overlap only)."""
    c = px[base].dropna()
    c = c[c.index < end]
    m = pd.read_csv(os.path.join(MET, f'{base}USDT.csv'), parse_dates=['create_time'])
    m = m[m.create_time < end].set_index('create_time').sort_index()
    f8 = fund[base]
    f8 = f8[f8.index < end]
    f3 = f8.resample('1D').mean().rolling(3).mean().reindex(c.index)
    oi = np.log(m['sum_open_interest'].replace(0, np.nan).resample('1D').last()).reindex(c.index)
    tk = np.log(m['sum_taker_long_short_vol_ratio'].replace(0, np.nan)).resample('1D').mean().reindex(c.index)
    la = np.log(m['count_long_short_ratio'].replace(0, np.nan)).resample('1D').last().reindex(c.index)
    s = pd.DataFrame(index=c.index)
    s['H1'] = (zscore(f3) > ZCUT) & (f3 > FUND_MIN)
    s['H2'] = (zscore(oi.diff(5)) > ZCUT) & (np.log(c).diff(5) > 0)
    s['H3'] = zscore(tk.rolling(3).mean()) > ZCUT
    s['z_all'] = zscore(la)
    return c, s


def trades(base, c, s, fund, col, start):
    fd = fund[base].resample('1D').sum().reindex(c.index).fillna(0.0)
    rows, last_exit = [], pd.Timestamp('2000-01-01')
    idx = c.index
    for i in range(len(idx) - HOLD):
        t = idx[i]
        if t < start or t < last_exit or not bool(s[col].iloc[i]):
            continue
        price = -np.log(c.iloc[i + HOLD] / c.iloc[i]) - COST
        net = price + fd.iloc[i + 1:i + HOLD + 1].sum()
        rows.append((base, t, price, net, s['z_all'].iloc[i]))
        last_exit = idx[i + HOLD]
    return pd.DataFrame(rows, columns=['coin', 'time', 'price', 'r', 'z_all'])


def infer(x, rng):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return np.nan, np.nan, np.nan, len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, (N_BOOT, len(x))).mean(1)
    return x.mean(), t, (boot <= 0).mean(), len(x)


def build(start, end, px_from):
    px, fund = full_daily_panel()
    px = px[(px.index >= px_from) & (px.index < end)]
    basket = set(ORIGINAL + MAJORS)
    coins = [b for b in px.columns if os.path.exists(os.path.join(MET, f'{b}USDT.csv'))]
    out = {}
    for h in NAMES:
        parts = []
        for b in coins:
            c, s = signals(b, px, fund, end)
            parts.append(trades(b, c, s, fund, h, start))
        d = pd.concat(parts, ignore_index=True)
        d['sample'] = np.where(d.coin.isin(basket), '15', '35')
        out[h] = d
    print(f'coins={len(coins)}  px {px.index[0].date()}..{px.index[-1].date()}  entries from {start.date()}')
    return out


def report(d, name, rng, alpha, periods):
    print(f'\n=== {name} ===')
    res = {}
    for label, sub in [('all', d), ('15', d[d['sample'] == '15']), ('35', d[d['sample'] == '35'])]:
        for per, mask in periods(sub):
            s = sub[mask]
            mean, t, p, n = infer(s.r, rng)
            res[(label, per)] = (mean, p, s.price.mean() if len(s) else np.nan)
            print(f'  {label:>3} {per:8} net={mean*1e4:+7.1f} bp  price={res[(label, per)][2]*1e4:+7.1f} bp  '
                  f't={t:+5.2f}  p={p:.4f}  trades={n}  win={(s.r>0).mean()*100:.0f}%')
    return res


def dev_periods(sub):
    return [('2021-23', sub.time < SPLIT), ('2024-25', sub.time >= SPLIT), ('full', sub.time == sub.time)]


def main():
    rng = np.random.default_rng(SEED)
    out = build(START, END, START)
    passed = []
    for h, name in NAMES.items():
        d = out[h]
        res = report(d, name, rng, ALPHA, dev_periods)
        f = res[('all', 'full')]
        ok = (f[0] > 0 and f[1] < ALPHA and f[2] > 0
              and res[('all', '2021-23')][0] > 0 and res[('all', '2024-25')][0] > 0
              and res[('15', 'full')][0] > 0 and res[('35', 'full')][0] > 0)
        print(f'  -> {h} {"PASS" if ok else "FAIL"}')
        if ok:
            passed.append(h)
            for y, g in d.groupby(d.time.dt.year):
                print(f'    {y}: n={len(g)}  net={g.r.mean()*1e4:+.1f} bp  price={g.price.mean()*1e4:+.1f} bp  win={(g.r>0).mean()*100:.0f}%')
            ov = d.z_all > ZCUT
            print(f'    overlap with all-account ratio z>1: {ov.mean()*100:.0f}% of entries')
            for lab, m in [('z_all > 1', ov), ('z_all <= 1', ~ov & d.z_all.notna())]:
                mean, t, p, n = infer(d[m].r, rng)
                print(f'    {lab:10s} n={n}  net={mean*1e4:+.1f} bp  t={t:+.2f}')
        d.to_csv(os.path.join(ROOT, 'scripts', f'crowd_short_{h}_trades.csv'), index=False)
    print(f'\npassed: {passed or "none"}')


if __name__ == '__main__':
    main()
