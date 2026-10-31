"""
DEV-WINDOW ONLY (< 2026-01-01). Turns dev_momentum_volume_profile.py's one
consistent pre-entry finding -- volume already building in the 6h before
the trigger (pre6_vs_base, top tercile) did better in BOTH 2020-23 and
2024-25 -- into CONTINUOUS risk scaling, the same playbook that worked for
v5/v6/extension (scale risk, never drop signals).

Pre-registered before running:
  - Primary feature: pre6_vs_base (mean volume of the 6 bars before the
    trigger / mean of the 20 bars before the trigger). Secondary: pre_ramp.
    Both monotonic in the profile study, so plain rank scaling.
  - Risk = 1% + rank x 2% (avg ~2%), rank = the trade's percentile within
    its symbol's DISCOVERY-period (2020-23) distribution. Anchors are
    frozen from discovery and applied unchanged to 2024-25, so the
    confirmation period is genuinely out-of-sample for the anchors
    (stricter than the extension study, which ranked on the full window).
  - Compared against: flat 2%; v6-style ADX scaling (same anchoring); and
    ADX + volume combined (average of the two ranks) since live v7
    already scales by ADX.
  - Control: shuffle the feature within symbol 1000x; the real scaling must
    beat most shuffles on 2024-25 total return.
  - v7 exits (SL=2xATR / TP=4xATR).

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_momentum_volume_profile import build
from dev_momentum_tighter_tp import build_candidates
from dev_momentum_adx_trend_filter import compute_adx

MIN_RISK, MAX_RISK = 0.01, 0.03
N_SHUFFLE = 1000


def attach_adx(d):
    _, frames = build_candidates()
    parts = []
    for s, df in frames.items():
        parts.append(pd.DataFrame({'symbol': s, 'entry_time': df['timestamp'], 'adx': compute_adx(df).values}))
    return d.merge(pd.concat(parts), on=['symbol', 'entry_time'], how='left')


def disc_anchored_rank(d, col):
    """Percentile of each trade's value within its symbol's DISCOVERY-period values."""
    out = pd.Series(np.nan, index=d.index)
    for s, g in d.groupby('symbol'):
        ref = np.sort(g.loc[g.period == 'disc', col].dropna().values)
        out.loc[g.index] = np.searchsorted(ref, g[col].values, side='right') / len(ref)
    return out.clip(0, 1)


def summarize(d, risk, label):
    eq = d['r'] * risk * 100
    out = []
    for p in ('disc', 'conf', 'all'):
        m = (d.period == p) if p != 'all' else np.ones(len(d), bool)
        e = eq[m]
        pf = e[e > 0].sum() / -e[e < 0].sum()
        q = d.loc[m].assign(e=e, q=pd.to_datetime(d.loc[m, 'entry_time']).dt.to_period('Q')).groupby('q')['e']
        qpass = (q.apply(lambda x: x[x > 0].sum() > -x[x < 0].sum())).sum()
        out.append(f"{p}: total {e.sum():+7.1f}%  PF {pf:.3f}  avgRisk {risk[m].mean()*100:.2f}%  Q>1 {qpass}/{q.ngroups}")
    print(f"  {label:22s} " + ' | '.join(out))
    return eq


def main():
    print('Building population + volume features + ADX (dev window only)...')
    d = attach_adx(build()[0]).reset_index(drop=True)
    d = d.dropna(subset=['adx']).reset_index(drop=True)
    print(f"Trades: {len(d)}  (disc {int((d.period == 'disc').sum())}, conf {int((d.period == 'conf').sum())})\n")

    ranks = {
        'vol6h': disc_anchored_rank(d, 'pre6_vs_base'),
        'ramp': disc_anchored_rank(d, 'pre_ramp'),
        'adx': disc_anchored_rank(d, 'adx'),
    }
    schemes = {
        'flat 2%': pd.Series(0.02, index=d.index),
        'ADX (v6-style)': MIN_RISK + ranks['adx'] * (MAX_RISK - MIN_RISK),
        'vol 6h build-up': MIN_RISK + ranks['vol6h'] * (MAX_RISK - MIN_RISK),
        'vol ramp 6h/24h': MIN_RISK + ranks['ramp'] * (MAX_RISK - MIN_RISK),
        'ADX + vol 6h': MIN_RISK + (ranks['adx'] + ranks['vol6h']) / 2 * (MAX_RISK - MIN_RISK),
    }
    print('=' * 110 + '\nRESULTS (linear sum of equity %, v7 exits). disc=2020-23 (anchors fitted here), conf=2024-25 (out-of-sample for anchors)')
    eqs = {name: summarize(d, risk, name) for name, risk in schemes.items()}

    print('\n' + '=' * 110 + '\nPER SYMBOL, conf 2024-25 total %')
    conf = d.period == 'conf'
    print(pd.DataFrame({name: eq[conf].groupby(d.loc[conf, 'symbol']).sum() for name, eq in eqs.items()}).round(1).to_string())

    print('\n' + '=' * 110 + f'\nSHUFFLE CONTROL ({N_SHUFFLE}x, feature shuffled within symbol, anchors refit each time) -- conf 2024-25 total')
    rng = np.random.default_rng(11)
    for name, col, base_name in (('vol 6h build-up', 'pre6_vs_base', None), ('vol ramp 6h/24h', 'pre_ramp', None),
                                 ('ADX + vol 6h', 'pre6_vs_base', 'adx')):
        real = eqs[name][conf].sum()
        sims = []
        for _ in range(N_SHUFFLE):
            sh = d.copy()
            sh[col] = sh.groupby('symbol')[col].transform(lambda x: rng.permutation(x.values))
            rk = disc_anchored_rank(sh, col)
            if base_name:
                rk = (ranks['adx'] + rk) / 2
            risk = MIN_RISK + rk * (MAX_RISK - MIN_RISK)
            sims.append((d['r'] * risk * 100)[conf].sum())
        sims = np.array(sims)
        ref = ' (vs ADX alone {:+.1f}%)'.format(eqs['ADX (v6-style)'][conf].sum()) if base_name else ''
        print(f"  {name:18s} real {real:+.1f}%   shuffled median {np.median(sims):+.1f}%   real beats {(real > sims).mean()*100:.1f}% of shuffles{ref}")


if __name__ == '__main__':
    main()
