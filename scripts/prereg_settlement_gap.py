"""
PRE-REGISTERED TESTS (RESEARCH_FINDINGS.md "新方向I：資金費率結算前後的價格漂移"
and "新方向J：CME 週末缺口回補", 2026-10-24). DEV WINDOW 2020-01 .. 2025-12,
2026 untouched. Hourly closes from universe_5m resampled to 1h (dev) or
holdout_2026 1h (holdout). P(T) = close of the last 1h bar ending at or
before T.

Direction I (50 coins, 8h funding settlements at 00/08/16 UTC):
  extreme settlement: |rate| above the 90th percentile of the coin's own
  trailing 90 settlements' |rate| (causal, >= 60) and |rate| > 0.01 %.
  s = sign(rate).
  H_I1  pre:  mean of -s * log(P(T) / P(T-1h)) > 0
  H_I2  post: mean of +s * log(P(T+1h) / P(T)) > 0
  Flagged coins are averaged per settlement time first (one observation
  per T). One-sided t and 10,000x bootstrap, alpha 0.025. Pass = mean > 0,
  p < 0.025, same sign in 2020-23 and 2024-25, same sign in the 15-coin
  basket and the 35 unseen coins. Gross returns; H_I2 is only "tradable"
  if the mean exceeds 14 bp.

Direction J (BTC from 2020, ETH from 2021-02-08):
  CME close = Friday 16:00 America/Chicago, open = Sunday 17:00 Chicago.
  gap = log(P(open) / P(close)); only |gap| > 0.5 %.
  H_J1  mean of -sign(gap) * log(P(open + 48h) / P(open)) > 0
  H_J2  touch(gap level = P(close)) - touch(mirror level, log = log P(open)
        + gap) within open .. next Friday close, by 1h high/low; mean > 0
  BTC and ETH averaged per weekend first. alpha 0.025. Pass = mean > 0,
  p < 0.025, same sign in 2020-23 and 2024-25, BTC > 0 and ETH > 0.
Breakdowns only after a pass. Nothing is re-tuned.
"""
import os
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
U5M, HOLD = os.path.join(CACHE, 'universe_5m'), os.path.join(CACHE, 'holdout_2026')
BASKET = set(ORIGINAL + MAJORS)
SPLIT = pd.Timestamp('2024-01-01')
PCT, FWIN, FMIN, RATE_MIN = 0.90, 90, 60, 1e-4
GAP_MIN, FILL_H = 0.005, 48
ETH_CME = pd.Timestamp('2021-02-08')
N_BOOT, ALPHA, SEED = 10000, 0.025, 20261024
CHI = ZoneInfo('America/Chicago')


def coins():
    return sorted(f.split('_USDT_5m')[0] for f in os.listdir(U5M) if f.endswith('_5m.csv'))


def hourly(base, holdout):
    """1h bars indexed by bar START; columns close/high/low."""
    if holdout:
        p = pd.read_csv(os.path.join(HOLD, f'{base}_USDT_1h.csv'), parse_dates=['timestamp']).set_index('timestamp')
        return p[['close', 'high', 'low']].sort_index()
    p = pd.read_csv(os.path.join(U5M, f'{base}_USDT_5m.csv'), parse_dates=['timestamp']).set_index('timestamp')
    return p.resample('1h').agg({'close': 'last', 'high': 'max', 'low': 'min'}).dropna()


def funding(base, holdout):
    if holdout:
        f = pd.read_csv(os.path.join(HOLD, f'{base}_USDT_funding.csv'))
    else:
        fdir = 'funding_basket' if base in BASKET else 'funding_universe'
        f = pd.read_csv(os.path.join(CACHE, fdir, f'{base}_USDT_funding.csv'))
    f['timestamp'] = pd.to_datetime(f['timestamp'], format='mixed').dt.round('h')
    return f.drop_duplicates('timestamp').set_index('timestamp')['funding_rate'].sort_index()


def price_at(h, times):
    """P(T) = close of the bar starting at T-1h (the bar that ends at T)."""
    return h['close'].reindex(pd.DatetimeIndex(times) - pd.Timedelta(hours=1)).values


def settlement_rows(base, holdout, start, end):
    h, f = hourly(base, holdout), funding(base, holdout)
    f = f[(f.index >= start) & (f.index < end)]
    f = f[f.index.hour.isin([0, 8, 16])]
    thr = f.abs().rolling(FWIN, min_periods=FMIN).quantile(PCT).shift(1)
    ext = f[(f.abs() > thr) & (f.abs() > RATE_MIN)]
    if ext.empty:
        return pd.DataFrame(columns=['coin', 'time', 'rate', 'pre', 'post'])
    T = ext.index
    p0, p1, p2 = price_at(h, T - pd.Timedelta(hours=1)), price_at(h, T), price_at(h, T + pd.Timedelta(hours=1))
    s = np.sign(ext.values)
    d = pd.DataFrame({'coin': base, 'time': T, 'rate': ext.values,
                      'pre': -s * np.log(p1 / p0), 'post': s * np.log(p2 / p1)})
    return d.dropna()


def cme_rows(base, holdout, start, end):
    h = hourly(base, holdout)
    lo = max(start, ETH_CME) if base == 'ETH' else start
    fridays = pd.date_range(lo, end, freq='W-FRI')
    rows = []
    for fri in fridays:
        close_t = pd.Timestamp(fri.year, fri.month, fri.day, 16, tzinfo=CHI).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        sun = fri + pd.Timedelta(days=2)
        open_t = pd.Timestamp(sun.year, sun.month, sun.day, 17, tzinfo=CHI).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        nxt = fri + pd.Timedelta(days=7)
        next_close = pd.Timestamp(nxt.year, nxt.month, nxt.day, 16, tzinfo=CHI).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        if next_close >= end or close_t < start:
            continue
        pc, po, p48 = price_at(h, [close_t])[0], price_at(h, [open_t])[0], price_at(h, [open_t + pd.Timedelta(hours=FILL_H)])[0]
        if not (np.isfinite(pc) and np.isfinite(po) and np.isfinite(p48)):
            continue
        gap = np.log(po / pc)
        if abs(gap) <= GAP_MIN:
            continue
        win = h[(h.index >= open_t) & (h.index < next_close)]
        if len(win) < 24 * 4:
            continue
        mirror = po * np.exp(gap)
        if gap > 0:   # gap up: gap level below open, mirror above
            touch_gap, touch_mir = (win['low'] <= pc).any(), (win['high'] >= mirror).any()
        else:
            touch_gap, touch_mir = (win['high'] >= pc).any(), (win['low'] <= mirror).any()
        rows.append((base, open_t, gap, -np.sign(gap) * np.log(p48 / po), float(touch_gap) - float(touch_mir)))
    return pd.DataFrame(rows, columns=['coin', 'time', 'gap', 'fill48', 'touch_diff'])


def infer(x, rng):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 20:
        return np.nan, np.nan, np.nan, len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, (N_BOOT, len(x))).mean(1)
    return x.mean(), t, (boot <= 0).mean(), len(x)


def agg_by_time(d, col, groups):
    """One observation per time per group: mean across the flagged coins/assets."""
    out = {}
    for label, mask in groups:
        g = d[mask].groupby('time')[col].mean()
        out[label] = g
    return out


def report(series_by_group, name, rng, alpha, periods, unit=1e4, unit_name='bp'):
    print(f'\n=== {name} ===')
    res = {}
    for label, g in series_by_group.items():
        for per, mask in periods(g):
            mean, t, p, n = infer(g[mask], rng)
            res[(label, per)] = (mean, p)
            print(f'  {label:>6} {per:8} mean={mean*unit:+8.2f} {unit_name}  t={t:+5.2f}  p={p:.4f}  n={n}')
    return res


def dev_periods(g):
    return [('2020-23', g.index < SPLIT), ('2024-25', g.index >= SPLIT), ('full', g.index == g.index)]


def decide(res, alpha, subgroups):
    """Pass = overall mean > 0 and p < alpha, every sub-period > 0, every subgroup's overall mean > 0.
    Returns (overall (mean, p), period names) on pass, else (None, period names)."""
    pers = [k[1] for k in res if k[0] == 'all']
    overall = 'full' if 'full' in pers else pers[-1]
    sub_pers = [p for p in pers if p != 'full']
    full = res[('all', overall)]
    ok = (full[0] > 0 and full[1] < alpha and all(res[('all', p)][0] > 0 for p in sub_pers)
          and all(res[(g, overall)][0] > 0 for g in subgroups))
    return (full if ok else None), pers


def run_I(holdout, start, end, rng, alpha, periods, out_csv):
    d = pd.concat([settlement_rows(b, holdout, start, end) for b in coins()], ignore_index=True)
    d['sample'] = np.where(d.coin.isin(BASKET), '15', '35')
    print(f'\n[I] extreme settlements: coin-events={len(d)}  times={d.time.nunique()}  {d.time.min()}..{d.time.max()}  '
          f'positive-rate share={(d.rate > 0).mean()*100:.0f}%')
    groups = [('all', d.time == d.time), ('15', d['sample'] == '15'), ('35', d['sample'] == '35')]
    passed = {}
    for col, name in [('pre', 'H_I1 hour BEFORE an extreme settlement, -sign(rate) x return'),
                      ('post', 'H_I2 hour AFTER an extreme settlement, +sign(rate) x return')]:
        res = report(agg_by_time(d, col, groups), name, rng, alpha, periods)
        full, pers = decide(res, alpha, ('15', '35'))
        ok = full is not None
        print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}' + ('  (tradable: mean > 14 bp)' if ok and col == 'post' and full[0] > 0.0014 else ''))
        passed[col] = ok
        if ok:
            for lab, m in [('rate > 0', d.rate > 0), ('rate < 0', d.rate < 0)]:
                mean, t, p, n = infer(d[m].groupby('time')[col].mean(), rng)
                print(f'    {lab:9s} n={n}  mean={mean*1e4:+.2f} bp  t={t:+.2f}')
            for hr in (0, 8, 16):
                m = d.time.dt.hour == hr
                mean, t, p, n = infer(d[m].groupby('time')[col].mean(), rng)
                print(f'    {hr:02d} UTC    n={n}  mean={mean*1e4:+.2f} bp  t={t:+.2f}')
    d.to_csv(out_csv, index=False)
    return passed


def run_J(holdout, start, end, rng, alpha, periods, out_csv):
    d = pd.concat([cme_rows(b, holdout, start, end) for b in ('BTC', 'ETH')], ignore_index=True)
    print(f'\n[J] CME weekend gaps |gap|>0.5%: rows={len(d)}  weekends={d.time.nunique()}  BTC={int((d.coin=="BTC").sum())}  '
          f'ETH={int((d.coin=="ETH").sum())}  gap-up share={(d.gap > 0).mean()*100:.0f}%  median |gap|={d.gap.abs().median()*100:.2f}%')
    groups = [('all', d.time == d.time), ('BTC', d.coin == 'BTC'), ('ETH', d.coin == 'ETH')]
    passed = {}
    for col, name, unit, un in [('fill48', 'H_J1 48h move toward the Friday close, -sign(gap) x return', 1e4, 'bp'),
                                ('touch_diff', 'H_J2 touch(gap level) - touch(mirror level) within the week', 100, 'pct-pts')]:
        res = report(agg_by_time(d, col, groups), name, rng, alpha, periods, unit, un)
        full, pers = decide(res, alpha, ('BTC', 'ETH'))
        ok = full is not None
        print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}')
        passed[col] = ok
        if ok:
            for lab, m in [('gap up', d.gap > 0), ('gap down', d.gap < 0), ('|gap|>1.5%', d.gap.abs() > 0.015)]:
                mean, t, p, n = infer(d[m].groupby('time')[col].mean(), rng)
                print(f'    {lab:10s} n={n}  mean={mean*unit:+.2f} {un}  t={t:+.2f}')
    d.to_csv(out_csv, index=False)
    return passed


def main():
    rng = np.random.default_rng(SEED)
    start, end = pd.Timestamp('2020-01-01'), pd.Timestamp('2026-01-01')
    pI = run_I(False, start, end, rng, ALPHA, dev_periods, os.path.join(ROOT, 'scripts', 'settlement_drift_events.csv'))
    pJ = run_J(False, start, end, rng, ALPHA, dev_periods, os.path.join(ROOT, 'scripts', 'cme_gap_weekends.csv'))
    print(f'\npassed: I={[k for k, v in pI.items() if v]}  J={[k for k, v in pJ.items() if v]}')


if __name__ == '__main__':
    main()
