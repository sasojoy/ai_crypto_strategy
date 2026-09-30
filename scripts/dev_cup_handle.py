"""
DEV-WINDOW ONLY (< 2026-01-01). Cup-and-handle breakout (long only), user
request 2026-09-30. Earlier chart-pattern tests (test #8) covered
Fibonacci / double bottom / breakout-retest, not cup-and-handle.

Definition (O'Neil-style, adapted to crypto with ATR/percent limits; fixed
before running). On 4H bars (primary) and 1D bars (check):
  - Rims are fractal highs (FRACTAL bars each side), usable only once
    confirmed -> no look-ahead.
  - Left rim LH at a, right rim RH at r: r-a within CUP_MIN..CUP_MAX bars;
    nothing between them trades above LH; |RH - LH| <= 10% of depth.
  - Bottom B = lowest low between the rims. Depth = LH - B, 8%..50% of LH
    and >= 5 x ATR.
  - U not V: bottom sits in the middle 25-75% of the cup, and >= 15% of
    cup bars have a low within the bottom quarter of the depth.
  - Prior uptrend: the rise into LH (from the lowest low of the preceding
    cup-length bars) is at least one cup depth.
  - Handle: bars after RH until breakout, HANDLE_MIN..HANDLE_MAX long,
    stays in the upper half of the cup, pulls back <= 35% of depth.
  - Entry: first close above the pivot (highest high from RH through the
    handle). One trade per cup.
  - Variant: breakout bar volume >= 1.5 x its 20-bar mean (O'Neil's rule).

Exits: (a) classic -- stop at handle low, target = pivot + cup depth
(measured move); (b) this project's standard SL 2xATR / TP 4xATR.
Friction 0.14% round trip; max hold MAX_HOLD bars.

Controls (the real question is whether the CUP SHAPE adds anything):
  - Plain breakout: first close above the highest high of the previous
    BRK_LOOKBACK bars (no shape requirement), same ATR exits.
  - Random long entries matched per symbol, same exits (for (a), stop and
    target distances drawn from the real cup trades).
Reported for 2020-23 and 2024-25 separately.

`python dev_cup_handle.py universe` re-runs the IDENTICAL rules (4H only)
on the 45 other coins from scripts/fetch_4h_universe.py -- an independent
sample, since the rules were fixed on BTC/ETH/SOL/NEAR/AVAX.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import SYMBOLS, load_1h, compute_atr, ROUND_TRIP_FRICTION

SPLIT = pd.Timestamp('2024-01-01')
N_RANDOM = 1000
CONFIG = {
    '4H': dict(rule='4h', FRACTAL=3, CUP_MIN=15, CUP_MAX=180, HANDLE_MIN=2, HANDLE_MAX=15, MAX_HOLD=180, BRK_LOOKBACK=60),
    '1D': dict(rule='1D', FRACTAL=3, CUP_MIN=15, CUP_MAX=200, HANDLE_MIN=2, HANDLE_MAX=20, MAX_HOLD=60, BRK_LOOKBACK=40),
}


def resample(df, rule):
    x = df.set_index('timestamp').resample(rule, label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
    x['atr'] = compute_atr(x)
    x['vol_ma20'] = x['volume'].rolling(20).mean().shift(1)
    return x


def fractal_highs(h, w):
    n = len(h)
    out = np.zeros(n, bool)
    for i in range(w, n - w):
        seg = h[i - w:i + w + 1]
        out[i] = h[i] == seg.max() and (seg == h[i]).sum() == 1
    return out


def find_cups(x, c):
    h, l, cl, atr = x['high'].values, x['low'].values, x['close'].values, x['atr'].values
    n = len(x)
    fr = fractal_highs(h, c['FRACTAL'])
    fr_idx = np.nonzero(fr)[0]
    trades, used_r = [], set()
    for t in range(c['CUP_MIN'] + c['HANDLE_MIN'], n - 1):
        # candidate right rims: confirmed by t-1, handle length within bounds
        for r in fr_idx[(fr_idx <= t - 1 - c['FRACTAL']) & (fr_idx >= t - c['HANDLE_MAX'])][::-1]:
            if r in used_r or t - r < c['HANDLE_MIN']:
                continue
            pivot = h[r:t].max()
            if not (cl[t] > pivot and cl[t - 1] <= pivot):
                continue
            ok = None
            for a in fr_idx[(fr_idx <= r - c['CUP_MIN']) & (fr_idx >= r - c['CUP_MAX'])][::-1]:
                LH, RH = h[a], h[r]
                if h[a + 1:r].max() > LH:
                    continue
                b = a + 1 + np.argmin(l[a + 1:r])
                B = l[b]
                depth = LH - B
                if depth <= 0 or np.isnan(atr[r]) or depth < 5 * atr[r] or not (0.08 <= depth / LH <= 0.50):
                    continue
                if abs(RH - LH) > 0.10 * depth:
                    continue
                if not (0.25 <= (b - a) / (r - a) <= 0.75):
                    continue
                if (l[a:r + 1] <= B + 0.25 * depth).mean() < 0.15:
                    continue
                lookback = r - a
                if a - lookback < 0 or LH - l[a - lookback:a].min() < depth:
                    continue
                hl = l[r + 1:t].min() if t > r + 1 else l[r]
                if hl < B + 0.5 * depth or RH - hl > 0.35 * depth:
                    continue
                ok = dict(a=a, r=r, b=b, depth=depth, pivot=pivot, handle_low=hl)
                break
            if ok:
                used_r.add(r)
                vr = x['volume'].values[t] / x['vol_ma20'].values[t] if x['vol_ma20'].values[t] > 0 else np.nan
                trades.append(dict(t=t, vol_ratio=vr, **ok))
                break
    return trades


def walk(h, l, cl, t, sl, tp, max_hold):
    entry = cl[t]
    end = min(t + 1 + max_hold, len(cl))
    if t + 1 + max_hold > len(cl):
        return None
    for j in range(t + 1, end):
        if l[j] <= sl:
            return (sl - entry) / entry - ROUND_TRIP_FRICTION, (entry - sl) / entry
        if h[j] >= tp:
            return (tp - entry) / entry - ROUND_TRIP_FRICTION, (entry - sl) / entry
    return (cl[end - 1] - entry) / entry - ROUND_TRIP_FRICTION, (entry - sl) / entry


def plain_breakouts(x, c):
    h, cl = x['high'].values, x['close'].values
    prior_max = pd.Series(h).shift(1).rolling(c['BRK_LOOKBACK']).max().values
    sig = (cl > prior_max) & (np.roll(cl, 1) <= np.roll(prior_max, 1))
    out, last = [], -10**9
    for t in np.nonzero(sig)[0]:
        if t - last > 10:
            out.append(t)
            last = t
    return out


def stats_line(label, r):
    r = np.asarray(r, float)
    if len(r) == 0:
        return f"  {label:34s} n=   0"
    pf = r[r > 0].sum() / -r[r < 0].sum() if (r < 0).any() else np.inf
    return f"  {label:34s} n={len(r):4d}  win={(r > 0).mean()*100:5.1f}%  PF={pf:5.2f}  avgR={r.mean():+.3f}"


UNIVERSE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'data', 'backtest_cache', 'universe_4h')


def load_universe(sym):
    df = pd.read_csv(os.path.join(UNIVERSE_DIR, sym.replace('/', '_') + '_4h.csv'), parse_dates=['timestamp'])
    return df[df['timestamp'] < pd.Timestamp('2026-01-01')].sort_values('timestamp').reset_index(drop=True)


def run(tf, c, rng, symbols=SYMBOLS, loader=load_1h):
    rows, ctrl, pools = [], [], []
    for s in symbols:
        x = resample(loader(s), c['rule'])
        h, l, cl, atr = x['high'].values, x['low'].values, x['close'].values, x['atr'].values
        ts = x['timestamp'].values
        for tr in find_cups(x, c):
            t = tr['t']
            if np.isnan(atr[t]):
                continue
            classic = walk(h, l, cl, t, tr['handle_low'], tr['pivot'] + tr['depth'], c['MAX_HOLD'])
            atrx = walk(h, l, cl, t, cl[t] - 2 * atr[t], cl[t] + 4 * atr[t], c['MAX_HOLD'])
            if classic is None or atrx is None or classic[1] <= 0:
                continue
            rows.append(dict(symbol=s, time=pd.Timestamp(ts[t]), vol_ratio=tr['vol_ratio'],
                             r_classic=classic[0] / classic[1], r_atr=atrx[0] / atrx[1],
                             sl_pct=classic[1], tp_pct=(tr['pivot'] + tr['depth'] - cl[t]) / cl[t],
                             depth_pct=tr['depth'] / h[tr['a']], cup_bars=tr['r'] - tr['a']))
        for t in plain_breakouts(x, c):
            if np.isnan(atr[t]):
                continue
            res = walk(h, l, cl, t, cl[t] - 2 * atr[t], cl[t] + 4 * atr[t], c['MAX_HOLD'])
            if res is not None:
                vm = x['vol_ma20'].values[t]
                ctrl.append(dict(symbol=s, time=pd.Timestamp(ts[t]), r_atr=res[0] / res[1],
                                 vol_ratio=x['volume'].values[t] / vm if vm > 0 else np.nan))
        pools.append((s, x))
    d, ctrl = pd.DataFrame(rows), pd.DataFrame(ctrl)

    print(f"\n{'=' * 100}\n{tf}: cup-and-handle breakouts found: {len(d)}  "
          f"(per coin: {d.groupby('symbol').size().to_dict() if len(d) else {}})")
    if d.empty:
        return
    print(f"  median depth {d.depth_pct.median()*100:.1f}%, median cup length {d.cup_bars.median():.0f} bars, "
          f"median stop {d.sl_pct.median()*100:.2f}%, median target {d.tp_pct.median()*100:.2f}%")
    for per, m_c, m_k in (('ALL dev', slice(None), slice(None)),
                          ('2020-23', d.time < SPLIT, ctrl.time < SPLIT),
                          ('2024-25', d.time >= SPLIT, ctrl.time >= SPLIT)):
        dd, kk = d[m_c], ctrl[m_k]
        print(f"  --- {per}")
        print(stats_line('cup&handle, classic exits', dd.r_classic))
        print(stats_line('cup&handle, ATR 2/4 exits', dd.r_atr))
        vol = dd[dd.vol_ratio >= 1.5]
        print(stats_line('cup&handle + vol>=1.5x, classic', vol.r_classic))
        print(stats_line('cup&handle + vol>=1.5x, ATR 2/4', vol.r_atr))
        print(stats_line('CONTROL plain breakout, ATR 2/4', kk.r_atr))
        print(stats_line('CONTROL plain brk + vol>=1.5x, ATR', kk[kk.vol_ratio >= 1.5].r_atr))

    # random-entry baselines (all dev), matched per symbol
    counts = d.groupby('symbol').size()
    rand_classic, rand_atr = [], []
    cache = {}
    for s, x in pools:
        if s not in counts:
            continue
        h, l, cl, atr = x['high'].values, x['low'].values, x['close'].values, x['atr'].values
        valid = np.nonzero(~np.isnan(atr) & (np.arange(len(x)) + 1 + c['MAX_HOLD'] <= len(x)))[0]
        picks = rng.choice(valid, size=min(3000, len(valid)), replace=False)
        sub = d[d.symbol == s]
        rc, ra = [], []
        for t in picks:
            k = rng.integers(len(sub))
            slp, tpp = sub.sl_pct.iloc[k], sub.tp_pct.iloc[k]
            res = walk(h, l, cl, t, cl[t] * (1 - slp), cl[t] * (1 + tpp), c['MAX_HOLD'])
            if res is not None:
                rc.append(res[0] / res[1])
            res = walk(h, l, cl, t, cl[t] - 2 * atr[t], cl[t] + 4 * atr[t], c['MAX_HOLD'])
            if res is not None:
                ra.append(res[0] / res[1])
        cache[s] = (np.array(rc), np.array(ra))
    sims_c, sims_a = [], []
    for _ in range(N_RANDOM):
        sims_c.append(np.concatenate([rng.choice(cache[s][0], cnt) for s, cnt in counts.items()]).mean())
        sims_a.append(np.concatenate([rng.choice(cache[s][1], cnt) for s, cnt in counts.items()]).mean())
    sims_c, sims_a = np.array(sims_c), np.array(sims_a)
    print(f"  --- random long entries, same exits, matched per coin ({N_RANDOM} draws, all dev)")
    print(f"  classic exits: random avgR median {np.median(sims_c):+.3f}; cup beats {(d.r_classic.mean() > sims_c).mean()*100:.1f}% of draws")
    print(f"  ATR 2/4 exits: random avgR median {np.median(sims_a):+.3f}; cup beats {(d.r_atr.mean() > sims_a).mean()*100:.1f}% of draws")
    print(f"  plain-breakout control avgR (ATR) {ctrl.r_atr.mean():+.3f} vs cup {d.r_atr.mean():+.3f}")
    d.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), f'cup_handle_trades_{tf}.csv'), index=False)
    return d


def main():
    rng = np.random.default_rng(5)
    if len(sys.argv) > 1 and sys.argv[1] == 'universe':
        syms = sorted(f[:-len('_USDT_4h.csv')] + '/USDT' for f in os.listdir(UNIVERSE_DIR) if f.endswith('_4h.csv'))
        d = run('4H_universe', CONFIG['4H'], rng, syms, load_universe)
        if d is not None and len(d):
            v = d[d.vol_ratio >= 1.5]
            print(f"\n  cup+vol trades per coin: {v.groupby('symbol').size().sort_values(ascending=False).head(10).to_dict()}")
            print(f"  cup+vol avgR per year: {v.groupby(v.time.dt.year).r_atr.agg(['count', 'mean']).round(3).to_dict('index')}")
        return
    for tf, c in CONFIG.items():
        run(tf, c, rng)


if __name__ == '__main__':
    main()
