"""
DEV-WINDOW ONLY (< 2026-01-01). Pullback limit entry for the v7 signal
(user goal 2026-09-30: fix the strategy on a fixed basket, then optimize
mechanics -- lower losses / higher win rate).

Instead of buying at the signal close, rest a limit order k x ATR better
than the signal price for W hours; if it never fills, the signal is
skipped. The known danger is adverse selection: signals that never pull
back are often the best winners, and a limit order misses exactly those.
So the scoring unit is PER SIGNAL (a missed signal scores 0), not per
filled trade.

Basket: 15 liquid coins (dev_coin_personality.py). Signal: v7 locked spec,
1H close trigger, coin's own top volume tercile. Every filled trade risks
1 unit (1R = 1% equity at 1% risk), 0.14% friction (kept although a limit
fill would pay maker fees -- conservative), max hold 168h from fill.

Grid (fixed before running): k in {0.25, 0.5, 0.75, 1.0} ATR x W in
{3, 6, 12} hours x stop/target anchoring:
  keep  SL/TP stay where the market-entry version puts them (signal price
        -2 / +4 ATR) -> a better fill means a smaller stop and a bigger
        target, i.e. reward:risk improves to (4+k):(2-k)
  refit SL/TP recomputed from the fill price (-2 / +4 ATR)
1H-bar conservatism: the fill bar counts as a stop-out if it also touches
the stop; a target touched on the fill bar is ignored.

Judged on: total R per signal in 2020-23 AND 2024-25, and in how many of
the 15 coins the variant beats market entry.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import compute_atr, compute_rsi, find_triggers, ROUND_TRIP_FRICTION
from dev_momentum_continuation import flip
from dev_coin_personality import ORIGINAL, MAJORS, load

SPLIT = pd.Timestamp('2024-01-01')
MAX_HOLD = 168
KS = [0.25, 0.5, 0.75, 1.0]
WS = [3, 6, 12]


def run_trade(c, h, l, start, sgn, entry, sl, tp, fill_bar_check=False):
    """Walk from bar `start`. If fill_bar_check, bar `start` is the fill bar:
    only the stop is checked there."""
    end = min(start + MAX_HOLD + 1, len(c))
    j0 = start
    if fill_bar_check:
        if (l[start] <= sl) if sgn > 0 else (h[start] >= sl):
            return (sgn * (sl - entry) / entry - ROUND_TRIP_FRICTION) / (abs(entry - sl) / entry), 'SL'
        j0 = start + 1
    exit_price, reason = c[end - 1], 'TIMEOUT'
    for j in range(j0, end):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            exit_price, reason = sl, 'SL'
            break
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            exit_price, reason = tp, 'TP'
            break
    return (sgn * (exit_price - entry) / entry - ROUND_TRIP_FRICTION) / (abs(entry - sl) / entry), reason


def signals(df):
    c, atr = df['close'].values, df['atr'].values
    rows = []
    for i, rev in find_triggers(df):
        if np.isnan(df['vol_ratio'].iloc[i]) or np.isnan(atr[i]) or i + MAX_HOLD + 13 >= len(df):
            continue
        rows.append((i, 1 if flip(rev) == 'long' else -1, df['vol_ratio'].iloc[i]))
    s = pd.DataFrame(rows, columns=['i', 'sgn', 'vol_ratio'])
    return s[pd.qcut(s['vol_ratio'].rank(method='first'), 3, labels=False) == 2]


def main():
    rows = []
    for b in ORIGINAL + MAJORS:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        c, h, l, atr, ts = df['close'].values, df['high'].values, df['low'].values, df['atr'].values, df['timestamp'].values
        for s in signals(df).itertuples():
            i, sgn, a = s.i, s.sgn, atr[s.i]
            base_sl, base_tp = c[i] - sgn * 2 * a, c[i] + sgn * 4 * a
            r0, why0 = run_trade(c, h, l, i + 1, sgn, c[i], base_sl, base_tp)
            rec = dict(coin=b, time=pd.Timestamp(ts[i]), sgn=sgn, market=r0, market_win=r0 > 0)
            for k in KS:
                limit = c[i] - sgn * k * a
                for w in WS:
                    fill = None
                    for j in range(i + 1, i + 1 + w):
                        if (h[j] >= base_tp) if sgn > 0 else (l[j] <= base_tp):
                            break  # ran to the market version's target without pulling back: missed
                        if (l[j] <= limit) if sgn > 0 else (h[j] >= limit):
                            fill = j
                            break
                    for anchor in ('keep', 'refit'):
                        key = f'k{k}_w{w}_{anchor}'
                        if fill is None:
                            rec[key] = np.nan
                            continue
                        if anchor == 'keep':
                            sl, tp = base_sl, base_tp
                        else:
                            sl, tp = limit - sgn * 2 * a, limit + sgn * 4 * a
                        rec[key] = run_trade(c, h, l, fill, sgn, limit, sl, tp, fill_bar_check=True)[0]
            rows.append(rec)
        print(f'  {b}: done', flush=True)
    d = pd.DataFrame(rows)
    d['period'] = np.where(d.time < SPLIT, 'disc', 'conf')

    def per_signal(col, mask):
        x = d.loc[mask, col]
        return x.fillna(0).sum(), x.notna().mean() * 100, x.dropna()

    print('\n' + '=' * 120)
    print('PER SIGNAL (missed = 0). totalR = sum of R over all signals = equity % at 1% risk. '
          'fill% / win% / avgR are over FILLED trades.')
    print(f"{'variant':20s} | {'2020-23 totalR':>14} {'fill%':>6} {'win%':>6} {'avgR':>7} | {'2024-25 totalR':>14} {'fill%':>6} {'win%':>6} {'avgR':>7} | coins better")
    cols = ['market'] + [f'k{k}_w{w}_{a}' for a in ('keep', 'refit') for k in KS for w in WS]
    for col in cols:
        cells = []
        for p in ('disc', 'conf'):
            tot, fill, x = per_signal(col, d.period == p)
            cells.append(f"{tot:+14.1f} {fill:6.1f} {(x > 0).mean()*100:6.1f} {x.mean():+7.3f}")
        if col == 'market':
            better = '-'
        else:
            by = d.groupby('coin').apply(lambda g: g[col].fillna(0).sum() - g['market'].sum())
            better = f"{(by > 0).sum()}/15"
        print(f"{col:20s} | {cells[0]} | {cells[1]} | {better}")

    # what did the misses look like?
    print('\n' + '=' * 120 + '\nADVERSE SELECTION CHECK: market-entry result of signals the limit order MISSED vs FILLED')
    for col in ('k0.5_w6_keep', 'k1.0_w12_keep'):
        miss = d[col].isna()
        print(f"  {col:16s} missed n={miss.sum():5d} market avgR {d.loc[miss, 'market'].mean():+.3f} win {d.loc[miss, 'market_win'].mean()*100:.1f}%   "
              f"| filled n={(~miss).sum():5d} market avgR {d.loc[~miss, 'market'].mean():+.3f} win {d.loc[~miss, 'market_win'].mean()*100:.1f}%")
    d.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pullback_entry_trades.csv'), index=False)


if __name__ == '__main__':
    main()
