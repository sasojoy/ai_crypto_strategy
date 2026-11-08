"""
DEV-WINDOW ONLY (< 2026-01-01). EXPLORATORY volume study around the
momentum-continuation entry (user request 2026-09-30: "look at volume
before and after entry, see if any pattern shows up").

Population and exits: same as dev_momentum_loss_templates.py (locked-spec
RSI cross + top volume tercile, 1H; v7 exits SL=2xATR / TP=4xATR).

Volume is normalized per trade by the mean volume of the 20 bars BEFORE the
trigger bar (i-20..i-1), so "1.0" means "an ordinary hour for this coin
right now". Directional volume signs each bar's volume by whether that bar
closed in the trade's direction.

Three parts:
  A. Profile: mean log(volume ratio) at offsets -24..+12 for eventual
     winners (TP) vs losers (SL). Descriptive only -- post-entry offsets
     here are NOT tradable as a filter (unknown at entry).
  B. Pre-entry features (known at entry), terciles per symbol, checked in
     DISCOVERY (2020-2023) and CONFIRMATION (2024-2025) separately.
  C. Post-entry as an EARLY-EXIT rule, done causally: at the close of bar
     i+k (k = 1,2,3,6), among trades still open, bucket by volume over
     i+1..i+k, and compare "hold to the original exit" vs "exit now at
     close". A bucket where exiting now beats holding in BOTH periods is a
     candidate management rule.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import MAX_HOLD_BARS, ROUND_TRIP_FRICTION
from dev_momentum_tighter_tp import build_candidates, SL_MULT

TP_MULT = 4.0
SPLIT = pd.Timestamp('2024-01-01')
PRE, POST = 24, 12
EXIT_CHECK_BARS = [1, 2, 3, 6]


def simulate(close, high, low, atr, i, sgn):
    entry = close[i]
    end = min(i + 1 + MAX_HOLD_BARS, len(close))
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None
    sl = entry - sgn * SL_MULT * atr[i]
    tp = entry + sgn * TP_MULT * atr[i]
    for j in range(i + 1, end):
        if (low[j] <= sl) if sgn > 0 else (high[j] >= sl):
            return 'SL', j, sl
        if (high[j] >= tp) if sgn > 0 else (low[j] <= tp):
            return 'TP', j, tp
    return 'TIMEOUT', end - 1, close[end - 1]


def r_of(entry, exit_price, sgn, atr):
    return (sgn * (exit_price - entry) / entry - ROUND_TRIP_FRICTION) / (SL_MULT * atr / entry)


def build():
    candidates, frames = build_candidates()
    rows, prof, sprof = [], [], []
    offsets = np.arange(-PRE, POST + 1)
    for row in candidates.itertuples():
        df = frames[row.symbol]
        i = row.idx
        if i < PRE + 20 or i + POST >= len(df):
            continue
        o, c, h, l, v, atr = (df[k].values for k in ('open', 'close', 'high', 'low', 'volume', 'atr'))
        sgn = 1 if row.direction == 'long' else -1
        sim = simulate(c, h, l, atr, i, sgn)
        if sim is None:
            continue
        base = v[i - 20:i].mean()
        if base <= 0:
            continue
        reason, j_exit, px = sim
        vr = v[i + offsets] / base
        bar_dir = np.sign(c[i + offsets] - o[i + offsets]) * sgn
        prof.append(np.log(np.maximum(vr, 1e-6)))
        sprof.append(bar_dir * vr)

        pre6, pre24 = v[i - 6:i].mean() / base, v[i - 24:i].mean() / base
        dir_pre12 = (v[i - 12:i] * (np.sign(c[i - 12:i] - o[i - 12:i]) * sgn > 0)).sum() / max(v[i - 12:i].sum(), 1e-9)
        rec = dict(symbol=row.symbol, direction=row.direction, entry_time=row.entry_time, reason=reason,
                   r=r_of(c[i], px, sgn, atr[i]), exit_bars=j_exit - i,
                   trig_vol=v[i] / base, pre6_vs_base=pre6, pre24_vs_base=pre24,
                   pre_ramp=pre6 / max(pre24, 1e-9), pre_max_spike=(v[i - 24:i] / base).max(),
                   pre_dir_share=dir_pre12)
        # causal early-exit snapshots
        for k in EXIT_CHECK_BARS:
            still_open = j_exit > i + k
            rec[f'open_{k}'] = still_open
            if still_open:
                rec[f'post_vol_{k}'] = v[i + 1:i + k + 1].mean() / base
                w = v[i + 1:i + k + 1]
                rec[f'post_dir_{k}'] = (w * (np.sign(c[i + 1:i + k + 1] - o[i + 1:i + k + 1]) * sgn > 0)).sum() / max(w.sum(), 1e-9)
                rec[f'r_exit_{k}'] = r_of(c[i], c[i + k], sgn, atr[i])
        rows.append(rec)
    d = pd.DataFrame(rows)
    d['period'] = np.where(d['entry_time'] < SPLIT, 'disc', 'conf')
    return d, np.array(prof), np.array(sprof), offsets


def terciles(s, by):
    return s.groupby(by).transform(lambda x: pd.qcut(x.rank(method='first'), 3, labels=['T1_low', 'T2_mid', 'T3_high'])).astype(str)


def part_a(d, prof, sprof, offsets):
    print('=' * 100 + '\nA. VOLUME PROFILE  winners(TP) vs losers(SL): mean log vol-ratio (0 = ordinary hour), and directional vol')
    win, lose = (d['reason'] == 'TP').values, (d['reason'] == 'SL').values
    print(f"   winners n={win.sum()}  losers n={lose.sum()}   (offsets > 0 are AFTER entry: descriptive only)")
    print(f"{'offset':>6} {'win logV':>8} {'lose logV':>9} {'diff':>6} {'t':>6} {'win dirV':>8} {'lose dirV':>9} {'diff':>6} {'t':>6}")
    show = list(range(-24, -6, 6)) + list(range(-6, POST + 1))
    for off in show:
        k = np.where(offsets == off)[0][0]
        a, b = prof[win, k], prof[lose, k]
        sa, sb = sprof[win, k], sprof[lose, k]
        t1 = (a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b))
        t2 = (sa.mean() - sb.mean()) / np.sqrt(sa.var() / len(sa) + sb.var() / len(sb))
        mark = '  <- entry bar' if off == 0 else ''
        print(f"{off:6d} {a.mean():+8.3f} {b.mean():+9.3f} {a.mean()-b.mean():+6.3f} {t1:+6.1f} "
              f"{sa.mean():+8.3f} {sb.mean():+9.3f} {sa.mean()-sb.mean():+6.3f} {t2:+6.1f}{mark}")


def cell_line(label, sub):
    return f"{label:14s} n={len(sub):4d} win={(sub.r > 0).mean()*100:5.1f}% avgR={sub.r.mean():+.3f}"


def part_b(d):
    print('\n' + '=' * 100 + '\nB. PRE-ENTRY VOLUME FEATURES (known at entry). Terciles per symbol. disc=2020-23, conf=2024-25')
    for p in ('disc', 'conf'):
        sub = d[d.period == p]
        print(f"   baseline {p}: n={len(sub)} win={(sub.r > 0).mean()*100:.1f}% avgR={sub.r.mean():+.3f}")
    feats = {'trig_vol': 'trigger-bar volume', 'pre6_vs_base': 'last 6h volume', 'pre24_vs_base': 'last 24h volume',
             'pre_ramp': 'ramp (6h / 24h)', 'pre_max_spike': 'biggest spike in 24h',
             'pre_dir_share': 'share of 12h vol in trade dir'}
    for f, desc in feats.items():
        b = terciles(d[f], d['symbol'])
        print(f"\n  {f} ({desc})")
        for t in ('T1_low', 'T2_mid', 'T3_high'):
            parts = [cell_line(p, d[(b == t) & (d.period == p)]) for p in ('disc', 'conf')]
            both_bad = all(d[(b == t) & (d.period == p)].r.mean() < d[d.period == p].r.mean() for p in ('disc', 'conf'))
            both_good = all(d[(b == t) & (d.period == p)].r.mean() > d[d.period == p].r.mean() for p in ('disc', 'conf'))
            tag = '  [below baseline in both]' if both_bad else ('  [above baseline in both]' if both_good else '')
            print(f"    {t:8s} | " + ' | '.join(parts) + tag)


def part_c(d):
    print('\n' + '=' * 100 + '\nC. POST-ENTRY VOLUME AS AN EARLY-EXIT RULE (causal: evaluated at close of bar i+k, trades still open)')
    print('   hold-exit = avgR(hold to original exit) - avgR(exit now at close).  NEGATIVE => exiting early would have helped')
    for k in EXIT_CHECK_BARS:
        o = d[d[f'open_{k}'] == True].copy()
        for f, name in ((f'post_vol_{k}', 'volume'), (f'post_dir_{k}', 'dir-share')):
            b = terciles(o[f], o['symbol'])
            print(f"\n  k={k}h  post-entry {name} (still open: {len(o)} of {len(d)})")
            for t in ('T1_low', 'T2_mid', 'T3_high'):
                cells = []
                gaps = []
                for p in ('disc', 'conf'):
                    s = o[(b == t) & (o.period == p)]
                    gap = s.r.mean() - s[f'r_exit_{k}'].mean()
                    gaps.append(gap)
                    cells.append(f"{p} n={len(s):4d} hold={s.r.mean():+.3f} exitNow={s[f'r_exit_{k}'].mean():+.3f} hold-exit={gap:+.3f}")
                tag = '  [EXIT EARLY helps in both]' if all(g < 0 for g in gaps) else ''
                print(f"    {t:8s} | " + ' | '.join(cells) + tag)


def main():
    print('Building population (dev window only)...')
    d, prof, sprof, offsets = build()
    print(f"Trades: {len(d)}  win {(d.r > 0).mean()*100:.1f}%  avgR {d.r.mean():+.3f}\n")
    part_a(d, prof, sprof, offsets)
    part_b(d)
    part_c(d)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'volume_profile_trades.csv')
    d.to_csv(out, index=False)
    print(f'\nSaved {out}')


if __name__ == '__main__':
    main()
