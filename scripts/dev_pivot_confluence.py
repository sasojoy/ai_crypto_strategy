"""
DEVELOPMENT-WINDOW ONLY (< 2026-01-01). Tests a third-party signal the user
saw (2026-09-30): "pivot-point confluence retest".

Rule as published on the signal card (NEAR example):
  - Classic pivot PP = (H+L+C)/3 of the PREVIOUS day / week / month.
  - When >= 2 of those PPs sit within a small tolerance of each other, the
    span between them is a "confluence zone".
  - Long ("support confirmed"): price approaches the zone from above, a 5m
    bar dips into it, and that 5m bar closes bullish ABOVE the zone.
    Short ("resistance confirmed") is the mirror image.
  - The card's "invalidation boundary" is the far edge of the zone (not an
    auto stop), and it gives no take-profit.

Because the card specifies neither a real stop nor a target, we test the
entry against several exit models:
  card_*        stop exactly at the far zone edge (the card's literal
                boundary), target at 1R / 2R / 3R
  zone+0.5atr_* stop 0.5 x 1H-ATR beyond the zone edge
  atr*_*        plain ATR stop from entry, independent of the zone

Methodology follows RESEARCH_FINDINGS.md: dev window only, 0.14% round-trip
friction, trades whose max-hold window is not complete are excluded (not
counted as timeouts), and each exit model is compared to a matched random-
entry baseline (same symbol/direction mix, same exit rule, stop distances
drawn from the real signals' own distribution for zone-based stops).
The zone tolerance is also varied (control grid) to check the result is
not an artifact of one arbitrary setting.

Uses 1m bars (data/backtest_cache/*_1m_devwindow.csv) both to build the 5m
bars / pivots and to walk each trade minute by minute (same-minute SL+TP
touch is resolved as SL, conservatively).

Not part of the deployed app; safe to delete after use.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
OUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       f"pivot_confluence_trades_{sys.argv[1] if len(sys.argv) > 1 else 6}.csv")

SYMBOLS = ['BTC_USDT', 'ETH_USDT', 'SOL_USDT', 'NEAR_USDT', 'AVAX_USDT']
DEV_END = pd.Timestamp('2026-01-01')
ROUND_TRIP_FRICTION = 0.0014
RISK_PER_TRADE = 0.01
MAX_HOLD_MIN = 48 * 60
APPROACH_BARS = int(sys.argv[1]) if len(sys.argv) > 1 else 6  # 5m bars fully above/below the zone before the touch
ATR_LEN = 14
TOLS = [0.001, 0.002, 0.003]
MAIN_TOL = 0.002
POOL_PER_SIDE = 5000       # random-entry pool size per symbol per direction
N_SEEDS = 500

# name -> (stop base, stop ATR mult, target in R)
EXITS = {
    'card_1R':          ('zone', 0.0, 1.0),
    'card_2R':          ('zone', 0.0, 2.0),
    'card_3R':          ('zone', 0.0, 3.0),
    'zone+0.5atr_1.5R': ('zone', 0.5, 1.5),
    'zone+0.5atr_2R':   ('zone', 0.5, 2.0),
    'atr1.0_1.5R':      ('atr',  1.0, 1.5),
    'atr1.0_2R':        ('atr',  1.0, 2.0),
    'atr1.5_2R':        ('atr',  1.5, 2.0),
}


def load_1m(sym):
    df = pd.read_csv(os.path.join(CACHE, f'{sym}_1m_devwindow.csv'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y-%m-%d %H:%M:%S')
    df = df[df['timestamp'] < DEV_END].drop_duplicates('timestamp').sort_values('timestamp')
    return df.set_index('timestamp')


def prev_period_pp(m, rule):
    agg = m.resample(rule, label='left', closed='left').agg({'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    pp = (agg['high'] + agg['low'] + agg['close']) / 3.0
    return pp.shift(1)  # indexed by period start: the PP that is "live" during that period


def build_bars(m):
    b5 = m.resample('5min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    idx = b5.index

    pp_d = prev_period_pp(m, 'D')
    pp_w = prev_period_pp(m, 'W-MON')
    assert (pp_w.index.weekday == 0).all(), 'weekly bins must start on Monday'
    pp_m = prev_period_pp(m, 'MS')

    day_key = idx.normalize()
    week_key = day_key - pd.to_timedelta(idx.weekday, unit='D')
    month_key = idx.to_period('M').to_timestamp()
    b5['pp_d'] = pp_d.reindex(day_key).values
    b5['pp_w'] = pp_w.reindex(week_key).values
    b5['pp_m'] = pp_m.reindex(month_key).values

    h1 = m.resample('1h', label='left', closed='left').agg(
        {'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    prev_c = h1['close'].shift(1)
    tr = pd.concat([h1['high'] - h1['low'], (h1['high'] - prev_c).abs(), (h1['low'] - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(ATR_LEN).mean().shift(1)  # last COMPLETED hour only
    b5['atr'] = atr.reindex(idx.floor('h')).values
    b5['day'] = day_key
    return b5


def confluence_zone(b5, tol):
    levels = np.sort(b5[['pp_d', 'pp_w', 'pp_m']].values, axis=1)  # NaNs sort last
    a, b, c = levels[:, 0], levels[:, 1], levels[:, 2]
    with np.errstate(invalid='ignore'):
        ab = np.abs(b - a) / b <= tol
        bc = np.abs(c - b) / c <= tol
    zbot = np.where(ab, a, np.where(bc, b, np.nan))
    ztop = np.where(ab & bc, c, np.where(ab, b, np.where(bc, c, np.nan)))
    return zbot, ztop


def find_signals(b5, tol):
    zbot, ztop = confluence_zone(b5, tol)
    o, h, l, c = (b5[k].values for k in ('open', 'high', 'low', 'close'))
    prev_low_min = pd.Series(l).shift(1).rolling(APPROACH_BARS).min().values
    prev_high_max = pd.Series(h).shift(1).rolling(APPROACH_BARS).max().values
    ok = np.isfinite(zbot) & np.isfinite(b5['atr'].values)
    with np.errstate(invalid='ignore'):
        long_sig = ok & (prev_low_min > ztop) & (l <= ztop) & (l >= zbot * (1 - tol)) & (c > ztop) & (c > o)
        short_sig = ok & (prev_high_max < zbot) & (h >= zbot) & (h <= ztop * (1 + tol)) & (c < zbot) & (c < o)

    rows = []
    for mask, direction in ((long_sig, 'long'), (short_sig, 'short')):
        sel = pd.DataFrame({'i': np.nonzero(mask)[0]})
        sel['day'] = b5['day'].values[sel['i']]
        sel = sel.drop_duplicates('day')  # first trigger per UTC day per direction
        for i in sel['i']:
            rows.append((i, direction, zbot[i], ztop[i]))
    return rows, np.isfinite(zbot)


def walk(H, L, C, j0, entry, sl, tp, direction):
    end = j0 + MAX_HOLD_MIN
    if end > len(H):
        return None  # max-hold window incomplete -> exclude, don't call it a timeout
    h, l = H[j0:end], L[j0:end]
    if direction == 'long':
        sl_hit, tp_hit = l <= sl, h >= tp
    else:
        sl_hit, tp_hit = h >= sl, l <= tp
    i_sl = np.argmax(sl_hit) if sl_hit.any() else MAX_HOLD_MIN
    i_tp = np.argmax(tp_hit) if tp_hit.any() else MAX_HOLD_MIN
    if i_sl == MAX_HOLD_MIN and i_tp == MAX_HOLD_MIN:
        exit_price, reason = C[end - 1], 'TIMEOUT'
    elif i_sl <= i_tp:
        exit_price, reason = sl, 'SL'
    else:
        exit_price, reason = tp, 'TP'
    ret = (exit_price - entry) / entry if direction == 'long' else (entry - exit_price) / entry
    pnl = ret - ROUND_TRIP_FRICTION
    sl_dist = abs(entry - sl) / entry
    return reason, pnl, pnl / sl_dist, sl_dist


def stop_and_target(entry, direction, exit_spec, zbot, ztop, atr, sl_dist_override=None):
    base, mult, r_mult = exit_spec
    if sl_dist_override is not None:
        dist = sl_dist_override * entry
    elif base == 'zone':
        edge = zbot if direction == 'long' else ztop
        dist = abs(entry - edge) + mult * atr
    else:
        dist = mult * atr
    if not np.isfinite(dist) or dist <= 0:
        return None
    if direction == 'long':
        return entry - dist, entry + r_mult * dist
    return entry + dist, entry - r_mult * dist


def stats(r):
    r = np.asarray(r, dtype=float)
    if len(r) == 0:
        return dict(n=0, win=np.nan, pf=np.nan, avg_r=np.nan, sum_r=np.nan)
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=(r > 0).mean() * 100, pf=pos / neg if neg > 0 else np.inf,
                avg_r=r.mean(), sum_r=r.sum())


def main():
    t0 = time.time()
    rng = np.random.default_rng(42)
    trades = []          # all real-signal trades, every tol x exit
    pools = []           # random-entry outcomes (MAIN_TOL stop distribution only)
    coverage = []

    for sym in SYMBOLS:
        m = load_1m(sym)
        b5 = build_bars(m)
        m_ts = m.index.values
        H, L, C = m['high'].values, m['low'].values, m['close'].values
        entry_j = np.searchsorted(m_ts, (b5.index + pd.Timedelta(minutes=5)).values)
        closes, atrs = b5['close'].values, b5['atr'].values

        main_sl_dists = {}  # (exit, direction) -> real stop distances at MAIN_TOL
        for tol in TOLS:
            sigs, has_zone = find_signals(b5, tol)
            coverage.append((sym, tol, has_zone.mean() * 100, len(sigs)))
            for i, direction, zb, zt in sigs:
                j0, entry = entry_j[i], closes[i]
                for name, spec in EXITS.items():
                    st = stop_and_target(entry, direction, spec, zb, zt, atrs[i])
                    if st is None:
                        continue
                    res = walk(H, L, C, j0, entry, st[0], st[1], direction)
                    if res is None:
                        continue
                    reason, pnl, r, sl_dist = res
                    trades.append(dict(symbol=sym, tol=tol, exit=name, direction=direction,
                                       time=b5.index[i], entry=entry, zbot=zb, ztop=zt,
                                       reason=reason, pnl=pnl, r=r, sl_dist=sl_dist))
                    if tol == MAIN_TOL:
                        main_sl_dists.setdefault((name, direction), []).append(sl_dist)

        # Random-entry pool: same exits, random 5m bars, same direction.
        valid = np.nonzero(np.isfinite(atrs) & (entry_j + MAX_HOLD_MIN <= len(H)))[0]
        for direction in ('long', 'short'):
            picks = rng.choice(valid, size=POOL_PER_SIDE, replace=False)
            for name, spec in EXITS.items():
                real = main_sl_dists.get((name, direction))
                if spec[0] == 'zone' and not real:
                    continue
                for i in picks:
                    entry = closes[i]
                    override = rng.choice(real) if spec[0] == 'zone' else None
                    st = stop_and_target(entry, direction, spec, np.nan, np.nan, atrs[i], override)
                    if st is None:
                        continue
                    res = walk(H, L, C, entry_j[i], entry, st[0], st[1], direction)
                    if res is not None:
                        pools.append((sym, direction, name, res[2]))
        print(f'  {sym}: done ({time.time() - t0:.0f}s)', flush=True)
        del m, b5, H, L, C

    df = pd.DataFrame(trades)
    df.to_csv(OUT_CSV, index=False)
    pool = pd.DataFrame(pools, columns=['symbol', 'direction', 'exit', 'r'])

    print('\n' + '=' * 90 + '\nZONE COVERAGE (share of 5m bars with a live confluence zone; signals before per-exit filtering)')
    for sym, tol, cov, n in coverage:
        print(f'  {sym:10s} tol={tol*100:.1f}%  zone live {cov:5.1f}% of bars   raw signals {n}')

    print('\n' + '=' * 90 + '\nALL TOLERANCES x EXITS (R = net of 0.14% friction; 1R = 1% equity at 1% risk)')
    print(f"{'tol':>5} {'exit':18s} {'n':>5} {'win%':>6} {'PF':>5} {'avgR':>7} {'sumR':>8} {'med stop%':>9} {'cost/R':>7}")
    for tol in TOLS:
        for name in EXITS:
            sub = df[(df.tol == tol) & (df.exit == name)]
            s = stats(sub.r)
            med = sub.sl_dist.median() * 100
            cost_r = (ROUND_TRIP_FRICTION / sub.sl_dist).mean()
            print(f"{tol*100:4.1f}% {name:18s} {s['n']:5d} {s['win']:6.1f} {s['pf']:5.2f} {s['avg_r']:+7.3f} {s['sum_r']:+8.1f} {med:9.2f} {cost_r:7.2f}")
        print()

    main = df[df.tol == MAIN_TOL]
    pool_arrays = {k: g.r.values for k, g in pool.groupby(['symbol', 'direction', 'exit'])}
    print('=' * 90 + f'\nRANDOM BASELINE @ tol={MAIN_TOL*100:.1f}% ({N_SEEDS} matched draws; % of draws the real signal beats)')
    print(f"{'exit':18s} {'dir':6s} {'n':>5} {'avgR':>7} {'rand avgR':>9} {'beat avgR':>9} {'PF':>5} {'rand PF':>7} {'beat PF':>7}")
    for name in EXITS:
        for direction in ('long', 'short', 'both'):
            sub = main[(main.exit == name) & ((main.direction == direction) | (direction == 'both'))]
            if sub.empty:
                continue
            counts = sub.groupby(['symbol', 'direction']).size()
            rand_avg, rand_pf = [], []
            for _ in range(N_SEEDS):
                draw = []
                for (sym, d), cnt in counts.items():
                    draw.append(rng.choice(pool_arrays[(sym, d, name)], size=cnt, replace=True))
                s = stats(np.concatenate(draw))
                rand_avg.append(s['avg_r']); rand_pf.append(s['pf'])
            real = stats(sub.r)
            rand_avg, rand_pf = np.array(rand_avg), np.array(rand_pf)
            print(f"{name:18s} {direction:6s} {real['n']:5d} {real['avg_r']:+7.3f} {np.median(rand_avg):+9.3f} "
                  f"{(real['avg_r'] > rand_avg).mean()*100:8.1f}% {real['pf']:5.2f} {np.median(rand_pf):7.2f} "
                  f"{(real['pf'] > rand_pf).mean()*100:6.1f}%")

    print('\n' + '=' * 90 + f'\nPER-YEAR avgR @ tol={MAIN_TOL*100:.1f}% (both directions)')
    main = main.assign(year=pd.to_datetime(main.time).dt.year)
    print(main.pivot_table(index='exit', columns='year', values='r', aggfunc='mean').reindex(list(EXITS)).round(3).to_string())
    print('\n' + '=' * 90 + f'\nPER-SYMBOL avgR @ tol={MAIN_TOL*100:.1f}% (both directions)')
    print(main.pivot_table(index='exit', columns='symbol', values='r', aggfunc='mean').reindex(list(EXITS)).round(3).to_string())
    print('\n' + '=' * 90 + f'\nEXIT REASONS @ tol={MAIN_TOL*100:.1f}% (% of trades)')
    print((main.pivot_table(index='exit', columns='reason', values='r', aggfunc='count')
           .div(main.groupby('exit').size(), axis=0) * 100).reindex(list(EXITS)).round(1).to_string())
    print(f'\nTotal runtime {time.time() - t0:.0f}s. Trades saved to {OUT_CSV}')


if __name__ == '__main__':
    main()
