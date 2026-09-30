"""
DEV-WINDOW ONLY (< 2026-01-01). Runs the v7 momentum-continuation signal on
the 45-coin universe (scripts/fetch_4h_universe.py 1h), user request
2026-09-30: "v7 surely doesn't make money on every coin -- and small coins'
volume spikes mean something different from big coins'".

Signal: the locked spec on 1H closes -- RSI(14) cross of 30/70 (8-bar
cooldown), momentum direction, volume ratio in the coin's own top tercile,
SL 2xATR / TP 4xATR, 0.14% friction. v7 proper enters intra-hour on 1m data
(v3 anticipatory entry); that needs 1m history we don't have for these
coins, so this uses the close-of-bar entry (v1-style) as the proxy.

Questions (all pre-specified):
  1. Per coin: does it make money? (n, win, avgR, PF, both periods)
  2. Size groups: coins split into terciles by 2023 median daily quote
     volume (known before the 2024-25 period). Does the edge differ by
     size, and does the VOLUME filter itself (top vs middle/bottom
     tercile) work differently for small coins?
  3. Can you PICK coins? Rank coins by 2020-23 avgR; do the top half
     still beat the bottom half in 2024-25? (Spearman of per-coin avgR
     between periods.) If not, "only trade the coins it works on" is
     hindsight.
  4. Cup-and-handle (4H universe run) split by the same size groups.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import SYMBOLS, load_1h, compute_atr, compute_rsi, find_triggers, MAX_HOLD_BARS, ROUND_TRIP_FRICTION
from dev_momentum_continuation import flip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U1H = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_1h')
CUP_CSV = os.path.join(ROOT, 'scripts', 'cup_handle_trades_4H_universe.csv')
SPLIT = pd.Timestamp('2024-01-01')
SL_MULT, TP_MULT = 2.0, 4.0
MIN_N_PER_PERIOD = 15


def load_universe_1h(base):
    df = pd.read_csv(os.path.join(U1H, f'{base}_USDT_1h.csv'), parse_dates=['timestamp'])
    return df[df['timestamp'] < pd.Timestamp('2026-01-01')].sort_values('timestamp').reset_index(drop=True)


def simulate_r(c, h, l, atr, i, sgn):
    entry = c[i]
    end = min(i + 1 + MAX_HOLD_BARS, len(c))
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None
    sl, tp = entry - sgn * SL_MULT * atr[i], entry + sgn * TP_MULT * atr[i]
    exit_price = c[end - 1]
    for j in range(i + 1, end):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            exit_price = sl
            break
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            exit_price = tp
            break
    return (sgn * (exit_price - entry) / entry - ROUND_TRIP_FRICTION) / (SL_MULT * atr[i] / entry)


def coin_trades(sym, df):
    df = df.copy()
    df['rsi'] = compute_rsi(df['close'])
    df['atr'] = compute_atr(df)
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    c, h, l, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
    rows = []
    for i, rev_dir in find_triggers(df):
        vr = df['vol_ratio'].iloc[i]
        if np.isnan(vr):
            continue
        direction = flip(rev_dir)
        r = simulate_r(c, h, l, atr, i, 1 if direction == 'long' else -1)
        if r is not None:
            rows.append(dict(symbol=sym, time=df['timestamp'].iloc[i], direction=direction, vol_ratio=vr, r=r))
    t = pd.DataFrame(rows)
    if len(t) >= 3:
        t['vol_tercile'] = pd.qcut(t['vol_ratio'].rank(method='first'), 3, labels=['low', 'mid', 'high']).astype(str)
    q = df[(df['timestamp'] >= '2023-01-01') & (df['timestamp'] < '2024-01-01')]
    turnover = (q['close'] * q['volume']).groupby(q['timestamp'].dt.date).sum().median() if len(q) else np.nan
    return t, turnover


def line(sub):
    if len(sub) == 0:
        return '   n=   0'
    pf = sub.r[sub.r > 0].sum() / -sub.r[sub.r < 0].sum() if (sub.r < 0).any() else np.inf
    return f"n={len(sub):5d} win={(sub.r > 0).mean()*100:5.1f}% avgR={sub.r.mean():+.3f} PF={pf:4.2f}"


def main():
    bases = sorted(f.split('_USDT_')[0] for f in os.listdir(U1H) if f.endswith('_1h.csv'))
    all_t, turnover = [], {}
    for b in bases:
        t, to = coin_trades(f'{b}/USDT', load_universe_1h(b))
        all_t.append(t)
        turnover[f'{b}/USDT'] = to
    ref = []
    for s in SYMBOLS:
        t, to = coin_trades(s, load_1h(s))
        ref.append(t)
        turnover[s] = to
    u = pd.concat(all_t, ignore_index=True)
    ref = pd.concat(ref, ignore_index=True)
    u['period'] = np.where(u.time < SPLIT, 'disc', 'conf')
    ref['period'] = np.where(ref.time < SPLIT, 'disc', 'conf')

    to = pd.Series({k: v for k, v in turnover.items() if k in set(u.symbol)})
    size = pd.qcut(to.rank(method='first'), 3, labels=['small', 'mid', 'large']).astype(str)
    u['size'] = u.symbol.map(size)
    sig = u[u.vol_tercile == 'high']
    rsig = ref[ref.vol_tercile == 'high']

    print('=' * 100 + '\nBASELINE: v7 signal (top volume tercile), close-of-bar entry, SL2/TP4')
    for label, d in (('original 5 coins', rsig), ('45 new coins', sig)):
        print(f"  {label:18s} all: {line(d)} | 2020-23: {line(d[d.period == 'disc'])} | 2024-25: {line(d[d.period == 'conf'])}")

    print('\n' + '=' * 100 + '\nBY SIZE (2023 median daily quote volume terciles; top-volume-tercile signals)')
    for g in ('large', 'mid', 'small'):
        d = sig[sig['size'] == g]
        coins = sorted(size[size == g].index.str.replace('/USDT', ''))
        print(f"  {g:6s} all: {line(d)} | 2020-23: {line(d[d.period == 'disc'])} | 2024-25: {line(d[d.period == 'conf'])}")
        print(f"         coins: {', '.join(coins)}")

    print('\n' + '=' * 100 + '\nDOES THE VOLUME FILTER WORK BY SIZE?  avgR of ALL triggers by the coin\'s own volume tercile')
    for g in ('large', 'mid', 'small'):
        d = u[u['size'] == g]
        parts = []
        for vt in ('low', 'mid', 'high'):
            x = d[d.vol_tercile == vt]
            parts.append(f"{vt}: {x.r.mean():+.3f} (n={len(x)}) [{x[x.period == 'disc'].r.mean():+.3f} / {x[x.period == 'conf'].r.mean():+.3f}]")
        print(f"  {g:6s} " + '   '.join(parts))
    print('         format: avgR all (n) [2020-23 / 2024-25]')

    print('\n' + '=' * 100 + '\nPER COIN (top-volume-tercile signals), sorted by 2020-23 avgR')
    pc = []
    for s, g in sig.groupby('symbol'):
        dd, cc = g[g.period == 'disc'], g[g.period == 'conf']
        pc.append(dict(coin=s.replace('/USDT', ''), size=size[s], n_disc=len(dd), avgR_disc=dd.r.mean(),
                       n_conf=len(cc), avgR_conf=cc.r.mean(), avgR_all=g.r.mean()))
    pc = pd.DataFrame(pc).sort_values('avgR_disc', ascending=False)
    print(pc.round(3).to_string(index=False))
    n_pos = (pc.avgR_all > 0).sum()
    print(f"\n  coins net positive over the whole dev window: {n_pos}/{len(pc)}")

    print('\n' + '=' * 100 + f'\nCAN WE PICK COINS?  (coins with >= {MIN_N_PER_PERIOD} signals in each period)')
    ok = pc[(pc.n_disc >= MIN_N_PER_PERIOD) & (pc.n_conf >= MIN_N_PER_PERIOD)].copy()
    rho, p = spearmanr(ok.avgR_disc, ok.avgR_conf)
    print(f"  {len(ok)} coins. Spearman(2020-23 avgR, 2024-25 avgR) = {rho:+.3f} (p={p:.3f})")
    top = ok.nlargest(len(ok) // 2, 'avgR_disc')
    bot = ok.drop(top.index)
    for label, grp in (('top half by 2020-23', top), ('bottom half by 2020-23', bot)):
        cs = set(grp.coin + '/USDT')
        d = sig[sig.symbol.isin(cs) & (sig.period == 'conf')]
        print(f"  {label:24s} -> their 2024-25 result: {line(d)}")

    if os.path.exists(CUP_CSV):
        cup = pd.read_csv(CUP_CSV, parse_dates=['time'])
        cup['size'] = cup.symbol.map(size)
        print('\n' + '=' * 100 + '\nCUP-AND-HANDLE (4H universe run) BY SIZE, ATR exits  [all / with breakout volume >= 1.5x]')
        for g in ('large', 'mid', 'small'):
            d = cup[cup['size'] == g].rename(columns={'r_atr': 'r'})
            v = d[d.vol_ratio >= 1.5]
            print(f"  {g:6s} all: {line(d)}   | vol>=1.5x: {line(v)}  [2020-23 {v[v.time < SPLIT].r.mean():+.3f} / 2024-25 {v[v.time >= SPLIT].r.mean():+.3f}]")

    pc.to_csv(os.path.join(ROOT, 'scripts', 'momentum_universe_per_coin.csv'), index=False)


if __name__ == '__main__':
    main()
