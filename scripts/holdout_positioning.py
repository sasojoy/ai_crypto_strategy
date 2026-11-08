"""
ONE-SHOT 2026 HOLDOUT for H_E2 "fade the crowd" (RESEARCH_FINDINGS.md
"新方向E", passed the dev window on 2026-10-24). Rule exactly as in
prereg_positioning.py: all-account long/short ratio, log, z vs trailing
90 days (causal), |z| > 1 -> position -sign(z) at the daily close, hold
5 days, no re-entry while in a trade, return = dir * log return -
funding paid - 0.14 %. Entries from 2026-01-01; the z window may use
late-2025 data (that is history, not the holdout). 50 coins, metrics to
2026-09-30, prices from the holdout_2026 panel.

Pass (fixed before running): pooled mean net > 0 with one-sided
bootstrap p < 0.05, AND the 35 unseen coins' mean > 0. Run once.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prereg_positioning as P  # noqa: E402
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from dev_regime_switch import full_daily_panel  # noqa: E402

HSTART = pd.Timestamp('2026-01-01')


def main():
    rng = np.random.default_rng(P.SEED)
    P.END = pd.Timestamp('2026-12-31')  # let the signal and price series run into 2026
    px, fund = full_daily_panel()
    px = px[px.index >= pd.Timestamp('2025-06-01')]
    basket = set(ORIGINAL + MAJORS)
    coins = [b for b in px.columns if os.path.exists(os.path.join(P.MET, f'{b}USDT.csv'))]
    parts = []
    for b in coins:
        z = P.daily_metrics(b)
        t = P.ts_trades(b, z, px, fund, 'all_acct', -1)
        parts.append(t[t.time >= HSTART])
    d = pd.concat(parts, ignore_index=True)
    d['sample'] = np.where(d.coin.isin(basket), '15', '35')
    print(f'holdout trades={len(d)}  {d.time.min().date()}..{d.time.max().date()}  coins={d.coin.nunique()}')
    res = {}
    for label, sub in [('all', d), ('15', d[d['sample'] == '15']), ('35', d[d['sample'] == '35'])]:
        mean, t, p, n = P.infer(sub.r, rng)
        res[label] = mean
        print(f'  {label:>3} mean={mean*1e4:+7.1f} bp  t={t:+5.2f}  p={p:.4f}  trades={n}  win={(sub.r>0).mean()*100:.0f}%')
        if label == 'all':
            p_all = p
    for lab, m in [('long', d.dir > 0), ('short', d.dir < 0)]:
        print(f'    {lab:5s} n={m.sum()}  mean={d[m].r.mean()*1e4:+.1f} bp')
    for q, g in d.groupby(d.time.dt.quarter):
        print(f'    2026Q{q}: n={len(g)}  mean={g.r.mean()*1e4:+.1f} bp')
    ok = res['all'] > 0 and p_all < 0.05 and res['35'] > 0
    print(f'  -> {"PASS" if ok else "FAIL"}')
    d.to_csv(os.path.join(P.ROOT, 'scripts', 'holdout_positioning_trades.csv'), index=False)


if __name__ == '__main__':
    main()
