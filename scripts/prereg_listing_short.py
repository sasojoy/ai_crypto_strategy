"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md, commit d7e610e).
New strategy candidate 4: short newly listed Binance USDT-M perpetuals.

  entry   short at the close of the 8th daily bar (7 full days after the
          first bar)
  stop    +50% from entry, checked on daily highs, filled at the stop
  exit    close of day 90 after entry (30-day variant: descriptive only)
  costs   0.14% round trip + actual funding (short receives positive,
          pays negative), summed over the holding period
  R       return / 0.5
Control: equal-weight short of the 15-coin basket over the SAME dates.
Pass, for EACH cohort (listed 2021-2023; listed 2024-2025H1): mean > 0,
mean excess vs control > 0, median > 0, mean after dropping the best 5%
> 0.

  python scripts/prereg_listing_short.py dev
  python scripts/prereg_listing_short.py holdout   (only after dev passes)
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_coin_personality import ORIGINAL, MAJORS, load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY_BAR = 7
STOP = 0.5
FRICTION = 0.0014


def basket_closes(cohort):
    cols = {}
    for b in ORIGINAL + MAJORS:
        if cohort == 'dev':
            s = load(b).set_index('timestamp')['close'].resample('1D').last()
        else:
            hold = pd.read_csv(os.path.join(ROOT, 'data', 'backtest_cache', 'holdout_2026', f'{b}_USDT_1h.csv'),
                               parse_dates=['timestamp'])
            dev = load(b)
            s = pd.concat([dev, hold[hold.timestamp > dev.timestamp.max()]]).set_index('timestamp')['close'].resample('1D').last()
        cols[b] = s
    return pd.DataFrame(cols)


def trade(px, fund, hold_days):
    if len(px) < ENTRY_BAR + hold_days + 1:
        return None
    entry = px['close'].iloc[ENTRY_BAR]
    stop = entry * (1 + STOP)
    exit_i, exit_px, stopped = ENTRY_BAR + hold_days, px['close'].iloc[ENTRY_BAR + hold_days], False
    for j in range(ENTRY_BAR + 1, ENTRY_BAR + hold_days + 1):
        if px['high'].iloc[j] >= stop:
            exit_i, exit_px, stopped = j, stop, True
            break
    t_in = px['timestamp'].iloc[ENTRY_BAR] + pd.Timedelta(days=1)
    t_out = px['timestamp'].iloc[exit_i] + pd.Timedelta(days=1)
    f = fund[(fund['timestamp'] > t_in) & (fund['timestamp'] <= t_out)]['funding_rate'].sum()
    ret = (entry - exit_px) / entry - FRICTION + f
    return dict(entry_day=px['timestamp'].iloc[ENTRY_BAR].normalize(), exit_day=px['timestamp'].iloc[exit_i].normalize(),
                ret=ret, funding=f, stopped=stopped)


def main(cohort):
    d_dir = os.path.join(ROOT, 'data', 'backtest_cache', 'listings', cohort)
    meta = pd.read_csv(os.path.join(d_dir, 'listings.csv'), parse_dates=['onboard'])
    bk = basket_closes(cohort)
    rows = []
    skipped = [r.base for r in meta.itertuples() if not os.path.exists(os.path.join(d_dir, f'{r.base}_1d.csv'))]
    if skipped:
        print(f"  {len(skipped)} listings have no data (contract not currently fetchable): {', '.join(skipped)}")
    for r in meta.itertuples():
        if r.base in skipped:
            continue
        px = pd.read_csv(os.path.join(d_dir, f'{r.base}_1d.csv'), parse_dates=['timestamp'])
        fund = pd.read_csv(os.path.join(d_dir, f'{r.base}_funding.csv'), parse_dates=['timestamp'])
        for hold in (90, 30):
            t = trade(px, fund, hold)
            if t is None:
                continue
            a, b = bk.loc[bk.index == t['entry_day']], bk.loc[bk.index == t['exit_day']]
            ctrl = np.nanmean(1 - b.values[0] / a.values[0]) if len(a) and len(b) else np.nan
            rows.append(dict(base=r.base, onboard=r.onboard, hold=hold, ctrl=ctrl, **t))
    d = pd.DataFrame(rows)
    d['excess'] = d['ret'] - d['ctrl']
    if cohort == 'dev':
        d['group'] = np.where(d.onboard < '2024-01-01', 'listed 2021-23', 'listed 2024-25H1')
    else:
        d['group'] = 'holdout 2025H2-26'
    ok = True
    for hold in (90, 30):
        print('=' * 110 + f'\nHOLD {hold} DAYS' + ('  (primary)' if hold == 90 else '  (descriptive only)'))
        for g, x in d[d.hold == hold].groupby('group'):
            trimmed = np.sort(x.ret.values)[:-max(1, int(round(len(x) * 0.05)))].mean()
            checks = [x.ret.mean() > 0, x.excess.mean() > 0, x.ret.median() > 0, trimmed > 0]
            if hold == 90:
                ok &= all(checks)
            print(f"  {g:18s} n={len(x):3d}  mean {x.ret.mean()*100:+6.1f}%  median {x.ret.median()*100:+6.1f}%  "
                  f"win {(x.ret > 0).mean()*100:4.1f}%  stopped {x.stopped.mean()*100:4.1f}%  "
                  f"excess vs basket {x.excess.mean()*100:+6.1f}%  trimmed {trimmed*100:+6.1f}%  "
                  f"funding {x.funding.mean()*100:+5.2f}%  avgR {x.ret.mean()/STOP:+.2f}  {'PASS' if all(checks) else 'x'}")
            q = np.percentile(x.ret * 100, [10, 25, 50, 75, 90])
            print(f"      return percentiles 10/25/50/75/90: {np.round(q, 1)}")
    if cohort == 'holdout':
        # Pre-registered holdout criteria (RESEARCH_FINDINGS.md): L30 primary, H30 secondary.
        x = d[d.hold == 30]
        trim = lambda v: np.sort(v)[:-max(1, int(round(len(v) * 0.05)))].mean()
        l30 = [x.ret.mean() > 0, x.ret.median() > 0, trim(x.ret.values) > 0, x.excess.mean() > 0]
        e = x.excess.dropna()
        h30 = [e.mean() > 0, e.median() > 0, trim(e.values) > 0]
        print('\n' + '=' * 110 + '\nHOLDOUT VERDICTS (30-day hold)')
        print(f"  L30 short:  n={len(x)} mean {x.ret.mean()*100:+.1f}%  median {x.ret.median()*100:+.1f}%  "
              f"trimmed {trim(x.ret.values)*100:+.1f}%  excess {x.excess.mean()*100:+.1f}%  -> {'PASSES' if all(l30) else 'FAILS'}")
        print(f"  H30 hedged: n={len(e)} mean {e.mean()*100:+.1f}%  median {e.median()*100:+.1f}%  "
              f"trimmed {trim(e.values)*100:+.1f}%  -> {'PASSES' if all(h30) else 'FAILS'}")
        print(x.groupby(x.onboard.dt.to_period('Q')).agg(n=('ret', 'size'), mean=('ret', 'mean'), excess=('excess', 'mean')).round(3).to_string())
        return
    print(f"\n  LISTING SHORT ({cohort}) {'PASSES' if ok else 'FAILS'}")
    d.to_csv(os.path.join(ROOT, 'scripts', f'listing_short_{cohort}.csv'), index=False)


if __name__ == '__main__':
    main(sys.argv[1])
