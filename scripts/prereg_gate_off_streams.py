"""
PRE-REGISTERED P1 (RESEARCH_FINDINGS.md 2026-11-08): which frozen weekly
streams have a positive mean return in GATE-OFF weeks (BTC funding 30-day
annualised <= 10%)?

Streams (raw weekly, no normalisation): XSM7 XSR7 XSM28 XSR28 V7 BRK4H
(scripts/regime_switch_raw_frozen.csv), BETA (recomputed exactly as
prereg_funding_gate.weekly_streams: 50-coin equal-weight log return minus
funding paid), K1 (scripts/xs_funding_H_K1_weekly.csv + holdout).
Dev = gate-off weeks 2020-07-05 .. 2025-12-28. Pass: mean > 0, bootstrap
one-sided p < 0.05/8, and mean > 0 in both 2020-23 and 2024-25 gate-off
subsets. Holdout (passers only, run by the same script with --holdout):
2026-01..2026-09 gate-off weeks, mean > 0, p < 0.05.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGS, sys.argv = sys.argv[1:], sys.argv[:1]

from dev_regime_switch import full_daily_panel, week_of  # noqa: E402
from prereg_funding_gate import gate_from, THRESH  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
DEV0, DEV1, SPLIT = pd.Timestamp('2020-07-05'), pd.Timestamp('2025-12-28'), pd.Timestamp('2024-01-01')
H0, H1 = pd.Timestamp('2026-01-01'), pd.Timestamp('2026-09-30')
STREAMS = ['XSM7', 'XSR7', 'XSM28', 'XSR28', 'V7', 'BRK4H', 'BETA', 'K1']
ALPHA = 0.05 / len(STREAMS)
N_BOOT = 10000


def beta_stream(px, funding):
    cols = list(px.columns)
    wk = px[cols].resample('W-SUN').last()
    ret = np.log(wk).diff().shift(-1)
    fpaid = pd.DataFrame({b: funding[b].groupby(funding[b].index.map(week_of)).sum() for b in cols}).reindex(ret.index).fillna(0.0)
    return (ret - fpaid.where(ret.notna())).mean(axis=1).dropna()


def streams():
    px, funding = full_daily_panel()
    raw = pd.read_csv(os.path.join(S, 'regime_switch_raw_frozen.csv'), index_col=0, parse_dates=True)
    k1 = pd.concat([pd.read_csv(os.path.join(S, 'xs_funding_H_K1_weekly.csv'), index_col=0, parse_dates=True).iloc[:, 0],
                    pd.read_csv(os.path.join(S, 'holdout_xs_funding_weekly.csv'), index_col=0, parse_dates=True).iloc[:, 0]])
    k1 = k1[~k1.index.duplicated()]
    d = raw.copy()
    d['BETA'] = beta_stream(px, funding)
    d['K1'] = k1
    d = d[STREAMS]
    gate = gate_from(funding, 'BTC', d.index)
    d['ann30'] = gate
    d['on'] = (gate > THRESH).fillna(False)
    return d


def sh(x):
    return np.nan if len(x) < 8 or x.std() == 0 else x.mean() / x.std() * np.sqrt(52)


def boot_p(x, rng):
    x = np.asarray(x, dtype=float)
    return (rng.choice(x, (N_BOOT, len(x))).mean(1) <= 0).mean()


def run(d, lo, hi, alpha, label, rng, need_split):
    d = d[(d.index >= lo) & (d.index <= hi)]
    off = d[~d.on]
    print(f'\n=== {label}: weeks {d.index[0].date()}..{d.index[-1].date()} n={len(d)}  gate-off {len(off)}  gate-on {int(d.on.sum())}  alpha={alpha:.4f}')
    print(f'{"stream":6s} {"off n":>5s} {"off mean":>9s} {"Sharpe":>7s} {"p":>7s} | {"20-23":>7s} {"24-25":>7s} | {"on Sharpe":>9s} {"on-off":>8s}  verdict')
    out = {}
    for s in STREAMS:
        x = off[s].dropna()
        if len(x) < 8:
            print(f'{s:6s} too few weeks ({len(x)})')
            out[s] = False
            continue
        p = boot_p(x.values, rng)
        a, b = x[x.index < SPLIT], x[x.index >= SPLIT]
        on = d.loc[d.on, s].dropna()
        cons = (a.mean() > 0 and b.mean() > 0) if need_split else True
        ok = bool(x.mean() > 0 and p < alpha and cons)
        out[s] = ok
        print(f'{s:6s} {len(x):5d} {x.mean():+9.4f} {sh(x):+7.2f} {p:7.4f} | {sh(a) if len(a) >= 8 else np.nan:+7.2f} {sh(b) if len(b) >= 8 else np.nan:+7.2f} '
              f'| {sh(on):+9.2f} {sh(on) - sh(x):+8.2f}  {"PASS" if ok else "FAIL"}')
    return out


def main():
    rng = np.random.default_rng(20261108)
    d = streams()
    d.to_csv(os.path.join(S, 'gate_off_streams_weekly.csv'))
    dev = run(d, DEV0, DEV1, ALPHA, 'DEV', rng, need_split=True)
    print('\nDEV SUMMARY: ' + ', '.join(f'{k} {"PASS" if v else "FAIL"}' for k, v in dev.items()))
    if '--holdout' in ARGS:
        passers = [k for k, v in dev.items() if v]
        print(f'\nHOLDOUT 2026 (one shot) for passers: {passers if passers else "none -> descriptive only"}')
        hold = run(d, H0, H1, 0.05, '2026', rng, need_split=False)
        for s in STREAMS:
            tag = ('PASS' if hold[s] else 'FAIL') if s in passers else 'descriptive'
            print(f'  {s:6s} 2026 gate-off -> {tag}')


if __name__ == '__main__':
    main()
