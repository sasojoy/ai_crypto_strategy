"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "完整系統的走動式驗證", 2026-10-18).

Answers the user's objection that the "no directional edge" verdict came
from testing bare signals with frozen parameters and no supporting
machinery. This test is of a COMPLETE SYSTEM whose every free choice is
made by a mechanical rule on past data only (anchored walk-forward), with
the supporting machinery that was missing before:

  * sleeves: the 6 frozen weekly streams (V7, BRK4H, XSM7, XSR7, XSM28,
    XSR28; scripts/regime_switch_raw_frozen.csv, costs included) plus a
    7th sleeve BETA = equal-weight long of the 50 coins, net of funding
  * sleeve vol-normalisation: trailing 26-week std, lagged, 1 %/week
  * regime gate on the directional sleeves (V7, BRK4H, BETA) from the
    BTC funding rate (today's finding: directional money is paid by
    leveraged longs in frenzies): none / relative (30-day mean funding
    above its trailing 52-week median) / absolute (> 10 % annualised)
  * meta rule: STATIC (equal weight), POSEW (equal weight across sleeves
    with positive trailing-L mean), BEST1 (single best sleeve if > 0)
  * L in {8, 13, 17, 20, 26, 30, 39, 52}
  * portfolio vol targeting: 20 % annualised, trailing 26-week std,
    lagged, leverage capped at 5x

Config grid = STATIC x 3 gates + {POSEW, BEST1} x 8 L x 3 gates = 51.
Folds: half-years 2022-H1 .. 2026-H2 (to 2026-09-20). For each fold the
config with the highest Sharpe on ALL weeks before the fold (from
2020-07-01) is selected and traded through the fold. Nothing is chosen
on the fold itself. The OOS series is the concatenation of the folds.

PASS (all three, fixed before running):
  P1  OOS Sharpe (2022-01 .. 2026-09) > 0.5
  P2  at least 4 of the 5 calendar years 2022..2026 positive
  P3  OOS Sharpe >= 95th percentile of the random-config benchmark
      (a config drawn at random for each fold, 2,000 draws)
Also printed, not judged on: STATIC-none benchmark, per-fold chosen
config with its in-sample vs realised Sharpe, the per-fold oracle.

Known limit (cannot be fixed with existing data): the 7 sleeves were
themselves designed on 2020-2025 data. This walk-forward is clean only
with respect to the system-level choices (gate, meta rule, L, sizing).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_regime_switch import full_daily_panel, normalize, week_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
FROZEN = os.path.join(ROOT, 'scripts', 'regime_switch_raw_frozen.csv')
START = pd.Timestamp('2020-07-01')
LAST_WEEK = pd.Timestamp('2026-09-20')
DIRECTIONAL = ['V7', 'BRK4H', 'BETA']
LOOKBACKS = [8, 13, 17, 20, 26, 30, 39, 52]
GATES = ['none', 'rel', 'abs10']
TARGET_ANN = 0.20
LEV_CAP = 5.0
N_RANDOM = 2000
SEED = 20261018
FOLDS = [(pd.Timestamp(f'{y}-{m:02d}-01'), pd.Timestamp(f'{y + (m == 7)}-{(1 if m == 7 else 7):02d}-01'))
         for y in range(2022, 2027) for m in (1, 7)]
FOLDS = [(a, min(b, LAST_WEEK + pd.Timedelta(days=1))) for a, b in FOLDS if a <= LAST_WEEK]


def beta_sleeve(px, funding):
    """Equal-weight long of all coins with data, weekly log return net of funding paid."""
    wk_close = px.resample('W-SUN').last()
    ret = np.log(wk_close).diff().shift(-1)  # week starting after Sunday s: log(c[s+7]/c[s])
    fpaid = {}
    for b, f in funding.items():
        fpaid[b] = f.groupby(f.index.map(week_of)).sum()
    fpaid = pd.DataFrame(fpaid).reindex(ret.index).fillna(0.0)
    net = (ret - fpaid.where(ret.notna()))
    return net.mean(axis=1).dropna()


def funding_gate_series(funding, weeks):
    f = funding['BTC']
    daily = f.resample('1D').sum()
    ann30 = daily.rolling(30).mean() * 365
    at_week = ann30.reindex(weeks, method='ffill')  # value known at the Sunday (week label), before the week starts
    rel = at_week > at_week.rolling(52, min_periods=52).median()
    rel = rel.where(at_week.rolling(52, min_periods=52).median().notna(), True)
    return {'none': pd.Series(True, index=weeks), 'rel': rel.astype(bool), 'abs10': (at_week > 0.10).astype(bool)}, at_week


def combine(streams, meta, L, gate_on):
    allowed = pd.DataFrame(True, index=streams.index, columns=streams.columns)
    for c in DIRECTIONAL:
        allowed[c] = gate_on.values
    if meta == 'STATIC':
        w = allowed.astype(float)
    else:
        trail = streams.rolling(L).mean().shift(1)
        if meta == 'POSEW':
            w = ((trail > 0) & allowed).astype(float)
        else:  # BEST1
            masked = trail.where(allowed, -np.inf).fillna(-np.inf)
            best = masked.idxmax(axis=1)
            bval = masked.max(axis=1)
            w = pd.DataFrame(0.0, index=streams.index, columns=streams.columns)
            for t in streams.index:
                if np.isfinite(bval[t]) and bval[t] > 0:
                    w.at[t, best[t]] = 1.0
    n = w.sum(axis=1).replace(0, np.nan)
    return (streams * w).sum(axis=1) / n.fillna(1.0) * (n.notna()).astype(float)


def sharpe(r):
    r = r.dropna()
    if len(r) < 8 or r.std() == 0:
        return np.nan
    return r.mean() / r.std() * np.sqrt(52)


def vol_target(r):
    vol = r.rolling(26, min_periods=13).std().shift(1)
    lev = (TARGET_ANN / np.sqrt(52) / vol).clip(upper=LEV_CAP)
    return (r * lev).dropna()


def main():
    raw = pd.read_csv(FROZEN, index_col=0, parse_dates=True)
    px, funding = full_daily_panel()
    raw['BETA'] = beta_sleeve(px, funding)
    raw = raw[(raw.index >= '2020-01-01') & (raw.index <= LAST_WEEK)]
    streams = pd.DataFrame({k: normalize(raw[k]) for k in raw.columns})
    streams = streams[streams.index >= START].fillna(0.0)
    gates, fund_ann = funding_gate_series(funding, streams.index)
    print(f'weeks {streams.index[0].date()} .. {streams.index[-1].date()} n={len(streams)}  sleeves={list(streams.columns)}')
    print('gate on-fraction: ' + ', '.join(f'{k}={v.mean()*100:.0f}%' for k, v in gates.items()))

    configs = [('STATIC', 0, g) for g in GATES] + [(m, L, g) for m in ('POSEW', 'BEST1') for L in LOOKBACKS for g in GATES]
    series = {cfg: combine(streams, cfg[0], cfg[1], gates[cfg[2]]) for cfg in configs}
    print(f'configs={len(configs)}')

    rng = np.random.default_rng(SEED)
    oos, rows, rand_parts = [], [], []
    rand_idx = rng.integers(0, len(configs), size=(N_RANDOM, len(FOLDS)))
    for k, (a, b) in enumerate(FOLDS):
        is_sh = {cfg: sharpe(s[(s.index >= START) & (s.index < a)]) for cfg, s in series.items()}
        chosen = max(is_sh, key=lambda c: (np.nan_to_num(is_sh[c], nan=-9), -c[1]))
        fold = series[chosen][(series[chosen].index >= a) & (series[chosen].index < b)]
        oos.append(fold)
        oracle = max(sharpe(s[(s.index >= a) & (s.index < b)]) for s in series.values())
        rows.append((a.date(), chosen, is_sh[chosen], sharpe(fold), fold.sum() * 100, oracle))
        rand_parts.append(np.stack([series[configs[i]][(series[configs[i]].index >= a) & (series[configs[i]].index < b)].values for i in range(len(configs))]))

    oos = pd.concat(oos)
    print('\n=== per fold: chosen config (in-sample Sharpe on all prior weeks) -> realised ===')
    for a, cfg, s_is, s_oos, ret, orc in rows:
        print(f'  {a}  {cfg[0]:6s} L={cfg[1]:2d} gate={cfg[2]:5s}  IS={s_is:+5.2f}  OOS={s_oos:+5.2f}  ret={ret:+6.1f}%  (fold oracle {orc:+5.2f})')

    # random-config benchmark: concatenated OOS Sharpe for each draw
    rand_sh = []
    for d in range(N_RANDOM):
        parts = [rand_parts[k][rand_idx[d, k]] for k in range(len(FOLDS))]
        r = pd.Series(np.concatenate(parts))
        rand_sh.append(r.mean() / r.std() * np.sqrt(52) if r.std() > 0 else np.nan)
    rand_sh = np.array(rand_sh)
    static = series[('STATIC', 0, 'none')]
    static = static[(static.index >= FOLDS[0][0]) & (static.index < FOLDS[-1][1])]

    sh = sharpe(oos)
    p95 = np.nanpercentile(rand_sh, 95)
    years = {y: oos[oos.index.year == y].sum() * 100 for y in range(2022, 2027)}
    print('\n=== OOS 2022-01 .. 2026-09 (unscaled, sleeves at 1%/week vol) ===')
    print(f'  Sharpe={sh:+.2f}  ann={oos.mean()*52*100:+.1f}%  weeks={len(oos)}  positive weeks={(oos>0).mean()*100:.0f}%')
    print('  by year (sum of weekly returns): ' + ', '.join(f'{y}:{v:+.1f}%' for y, v in years.items()))
    print(f'  STATIC-none benchmark Sharpe={sharpe(static):+.2f}; random-config benchmark: median={np.nanmedian(rand_sh):+.2f}  p95={p95:+.2f}  share above ours={(rand_sh >= sh).mean()*100:.1f}%')
    vt = vol_target(oos)
    eq = vt.cumsum()
    print(f'  vol-targeted 20%: ann={vt.mean()*52*100:+.1f}%  realised vol={vt.std()*np.sqrt(52)*100:.1f}%  max drawdown={(eq - eq.cummax()).min()*100:+.1f}%  '
          + 'by year ' + ', '.join(f'{y}:{vt[vt.index.year == y].sum()*100:+.1f}%' for y in range(2022, 2027)))
    p1, p2, p3 = sh > 0.5, sum(v > 0 for v in years.values()) >= 4, sh >= p95
    print(f'\n  P1 Sharpe>0.5: {"PASS" if p1 else "FAIL"}   P2 >=4/5 years positive: {"PASS" if p2 else "FAIL"}   P3 beats 95% of random configs: {"PASS" if p3 else "FAIL"}')
    print(f'  -> {"PASS" if (p1 and p2 and p3) else "FAIL"}')
    pd.DataFrame({'oos': oos, 'vt': vt}).to_csv(os.path.join(ROOT, 'scripts', 'walkforward_system_oos.csv'))


if __name__ == '__main__':
    main()
