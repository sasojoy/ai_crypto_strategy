"""
DEV-WINDOW ONLY (< 2026-01-01). Do Fibonacci retracement levels get a
special price REACTION, compared with arbitrary neighbouring ratios?
(User request 2026-09-30.)

The earlier Fibonacci test (test #8 in RESEARCH_FINDINGS.md) used 0.618 as
an entry signal and found any ratio worked about as well. This asks the
more basic question directly, at scale: when price pulls back into a
swing and touches the level at ratio r, how often does it bounce -- and is
that probability specifically higher at 0.382 / 0.5 / 0.618 / 0.786 than
at the ratios right next to them?

Method (all pre-specified):
  - 1H bars, 5 symbols, dev window.
  - Swing extreme = fractal high/low (highest/lowest of W bars each side).
    It only becomes KNOWN W bars later (confirmation), so a level only
    counts if it is first touched AFTER confirmation -- no look-ahead.
  - Leg: for a swing high H, L = lowest low of the LEG_LOOKBACK bars before
    H; leg must be >= MIN_LEG_ATR x ATR. Mirror for swing lows.
  - Levels at every ratio 0.20..0.90 in 0.02 steps (36 levels, Fibonacci
    ones included: 0.382 is taken as 0.38, 0.618 as 0.62, 0.786 as 0.78).
  - A level is dropped if price already went through it before
    confirmation, or if the leg is invalidated (new extreme beyond H) before
    the touch.
  - After the first touch, from the NEXT bar: "bounce" if price moves
    K_ATR x ATR back in the swing's direction before moving K_ATR x ATR
    through the level; neither within MAX_BARS = dropped.
  - Test: each ratio's bounce rate minus the mean of its neighbours at
    +/-0.04 and +/-0.06 ("local bump"). Fibonacci ratios' bumps are
    ranked against the bumps of every non-Fibonacci ratio.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import SYMBOLS, load_1h, compute_atr

W = 12
LEG_LOOKBACK = 72
MIN_LEG_ATR = 4.0
K_ATR = 1.0
MAX_BARS = 48
SCAN_BARS = 240
RATIOS = np.round(np.arange(0.20, 0.901, 0.02), 2)
FIB = {0.38: '0.382', 0.50: '0.5', 0.62: '0.618', 0.78: '0.786'}


def legs(df):
    h, l, atr = df['high'].values, df['low'].values, df['atr'].values
    n = len(df)
    out = []
    for i in range(LEG_LOOKBACK, n - W):
        win_h, win_l = h[i - W:i + W + 1], l[i - W:i + W + 1]
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        if h[i] == win_h.max() and (win_h == h[i]).sum() == 1:
            lo = l[i - LEG_LOOKBACK:i].min()
            if h[i] - lo >= MIN_LEG_ATR * atr[i]:
                out.append((i, 'up', h[i], lo))       # retrace DOWN into an up-leg; bounce = up
        if l[i] == win_l.min() and (win_l == l[i]).sum() == 1:
            hi = h[i - LEG_LOOKBACK:i].max()
            if hi - l[i] >= MIN_LEG_ATR * atr[i]:
                out.append((i, 'down', l[i], hi))     # retrace UP into a down-leg; bounce = down
    return out


def outcomes(df, leg_list):
    h, l, c, atr = df['high'].values, df['low'].values, df['close'].values, df['atr'].values
    n = len(df)
    rows = []
    for i, kind, ext, other in leg_list:
        conf = i + W                     # extreme becomes known at close of bar i+W
        rng = abs(ext - other)
        a = atr[conf]
        if np.isnan(a) or a <= 0:
            continue
        seg_end = min(conf + 1 + SCAN_BARS, n)
        for r in RATIOS:
            if kind == 'up':
                level = ext - r * rng
                if l[i + 1:conf + 1].min() <= level:
                    continue             # already touched before we could know the leg
                touch = None
                for j in range(conf + 1, seg_end):
                    if h[j] > ext:
                        break            # new high: leg invalidated before touching
                    if l[j] <= level:
                        touch = j
                        break
                if touch is None:
                    continue
                up_t, dn_t = level + K_ATR * a, level - K_ATR * a
                res = None
                for j in range(touch + 1, min(touch + 1 + MAX_BARS, n)):
                    if l[j] <= dn_t:
                        res = 0
                        break
                    if h[j] >= up_t:
                        res = 1
                        break
            else:
                level = ext + r * rng
                if h[i + 1:conf + 1].max() >= level:
                    continue
                touch = None
                for j in range(conf + 1, seg_end):
                    if l[j] < ext:
                        break
                    if h[j] >= level:
                        touch = j
                        break
                if touch is None:
                    continue
                up_t, dn_t = level + K_ATR * a, level - K_ATR * a
                res = None
                for j in range(touch + 1, min(touch + 1 + MAX_BARS, n)):
                    if h[j] >= up_t:
                        res = 0
                        break
                    if l[j] <= dn_t:
                        res = 1
                        break
            if res is not None:
                rows.append((kind, r, res, df['timestamp'].iloc[touch]))
    return rows


def bumps(rate):
    out = {}
    for r in RATIOS:
        nb = [round(r + dx, 2) for dx in (-0.06, -0.04, 0.04, 0.06)]
        nb = [x for x in nb if x in rate.index]
        if len(nb) >= 3:
            out[r] = rate[r] - rate[nb].mean()
    return pd.Series(out)


def report(d, label):
    g = d.groupby('ratio')['bounce'].agg(['mean', 'count'])
    rate = g['mean']
    b = bumps(rate)
    non_fib = b[[r for r in b.index if r not in FIB]]
    print(f"\n{'=' * 90}\n{label}   touches={len(d)}   overall bounce rate {d['bounce'].mean()*100:.1f}%")
    line = []
    for r in RATIOS:
        tag = f"*{FIB[r]}" if r in FIB else f"{r:.2f}"
        line.append(f"{tag}:{rate[r]*100:4.1f}")
    for k in range(0, len(line), 6):
        print('   ' + '  '.join(line[k:k + 6]))
    for r, name in FIB.items():
        if r in b.index:
            pct = (b[r] > non_fib).mean() * 100
            print(f"   Fib {name:6s} bounce {rate[r]*100:5.1f}% (n={int(g.loc[r, 'count'])})  local bump {b[r]*100:+5.2f}pp  "
                  f"bigger than {pct:5.1f}% of non-Fib ratios' bumps")
    fib_mean = b[[r for r in FIB if r in b.index]].mean()
    print(f"   mean Fib bump {fib_mean*100:+.2f}pp   non-Fib bumps: mean {non_fib.mean()*100:+.2f}pp, "
          f"sd {non_fib.std()*100:.2f}pp")


def main():
    all_rows = []
    for s in SYMBOLS:
        df = load_1h(s)
        df['atr'] = compute_atr(df)
        lg = legs(df)
        rows = outcomes(df, lg)
        all_rows += [(s, *r) for r in rows]
        print(f"  {s}: {len(lg)} legs, {len(rows)} level touches", flush=True)
    d = pd.DataFrame(all_rows, columns=['symbol', 'kind', 'ratio', 'bounce', 'time'])
    d['ratio'] = d['ratio'].round(2)
    report(d, 'ALL (dev window, both directions)')
    report(d[d.kind == 'up'], 'UP-LEGS (pullback down, bounce up)')
    report(d[d.kind == 'down'], 'DOWN-LEGS (pullback up, bounce down)')
    report(d[d.time < pd.Timestamp('2024-01-01')], 'DISCOVERY 2020-2023')
    report(d[d.time >= pd.Timestamp('2024-01-01')], 'CONFIRMATION 2024-2025')
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fib_reaction_touches.csv')
    d.to_csv(out, index=False)
    print(f'\nSaved {out}')


if __name__ == '__main__':
    main()
