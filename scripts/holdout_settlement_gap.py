"""
ONE-SHOT 2026 HOLDOUT for directions I / J (registered 2026-10-24 with the
dev test). Run only for what passed dev:
    python scripts/holdout_settlement_gap.py I J
Data: holdout_2026 1h bars and funding, entries 2026-01-01 .. 2026-09-30.
Pass (fixed before running): mean > 0 with one-sided bootstrap p < 0.05;
I additionally the 35 unseen coins > 0; J additionally BTC and ETH both > 0.
The dev-window criteria (two periods) do not apply; a single 2026 period.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prereg_settlement_gap as P  # noqa: E402

START, END = pd.Timestamp('2026-01-01'), pd.Timestamp('2026-10-01')


def one_period(g):
    return [('2026', g.index == g.index)]


def main():
    which = [a for a in sys.argv[1:] if a in ('I', 'J')]
    if not which:
        raise SystemExit('pass I and/or J (whatever passed dev)')
    rng = np.random.default_rng(P.SEED)
    if 'I' in which:
        P.run_I(True, START, END, rng, 0.05, one_period, os.path.join(P.ROOT, 'scripts', 'holdout_settlement_drift_events.csv'))
    if 'J' in which:
        P.run_J(True, START, END, rng, 0.05, one_period, os.path.join(P.ROOT, 'scripts', 'holdout_cme_gap_weekends.csv'))


if __name__ == '__main__':
    main()
