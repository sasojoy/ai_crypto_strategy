"""
ONE-SHOT 2026 HOLDOUT for direction H (RESEARCH_FINDINGS.md "新方向H",
registered 2026-10-24 together with the dev test). Run only for the
hypotheses that passed the dev window, passed on the command line:
    python scripts/holdout_crowd_short.py H1 H3
Rule exactly as in prereg_crowd_short.py; entries from 2026-01-01,
metrics to 2026-09-30, prices from the holdout_2026 panel, the z window
may use late-2025 data. Pass (fixed before running): net mean > 0 with
one-sided bootstrap p < 0.05, the 35 unseen coins' net mean > 0, and
price mean > 0. Run once.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prereg_crowd_short as P  # noqa: E402

HSTART, HEND = pd.Timestamp('2026-01-01'), pd.Timestamp('2026-10-01')


def main():
    hyps = [a for a in sys.argv[1:] if a in P.NAMES]
    if not hyps:
        raise SystemExit('pass the hypotheses that passed dev, e.g. H1 H3')
    rng = np.random.default_rng(P.SEED)
    out = P.build(HSTART, HEND, pd.Timestamp('2025-06-01'))
    for h in hyps:
        d = out[h]
        res = P.report(d, P.NAMES[h] + ' -- 2026 HOLDOUT', rng, 0.05, lambda s: [('2026', s.time == s.time)])
        f = res[('all', '2026')]
        ok = f[0] > 0 and f[1] < 0.05 and res[('35', '2026')][0] > 0 and f[2] > 0
        print(f'  -> {h} {"PASS" if ok else "FAIL"}')
        for q, g in d.groupby(d.time.dt.quarter):
            print(f'    2026Q{q}: n={len(g)}  net={g.r.mean()*1e4:+.1f} bp  price={g.price.mean()*1e4:+.1f} bp')
        d.to_csv(os.path.join(P.ROOT, 'scripts', f'holdout_crowd_short_{h}_trades.csv'), index=False)


if __name__ == '__main__':
    main()
