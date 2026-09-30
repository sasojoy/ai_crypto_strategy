"""
DEV-WINDOW ONLY (< 2026-01-01). "Different coins need different strategies"
(user, 2026-09-30) -- tested honestly: assign each coin a strategy from a
MEASURED personality trait (not from its past P&L, which the universe
study showed barely persists), fitted on 2020-23, judged on 2024-25.

Coins (15): the original 5 + the 10 most liquid majors:
  BTC ETH SOL NEAR AVAX | BNB XRP DOGE ADA LINK LTC DOT BCH TRX UNI

Pre-registered before running:
  Trait (primary): variance ratio VR(24) of 1H log returns over 2020-23
    = Var(24h returns) / (24 x Var(1h returns)).  > 1 trending, < 1
    mean-reverting. Also reported (descriptive): lag-1 autocorrelation of
    4H returns, correlation with BTC (daily), median ATR%.
  Strategies, fixed parameters, 1H:
    MOM  v7 locked spec, close-of-bar entry (RSI(14) cross 30/70 in the
         momentum direction, coin's own top volume tercile, 8-bar
         cooldown), SL 2xATR / TP 4xATR, max hold 168h.
    MR   Bollinger(20, 2) fade: first close outside a band -> trade back
         toward the middle band; TP = middle band at entry, SL 2xATR,
         max hold 48h, 8-bar cooldown.
    Both: 0.14% round-trip friction, results in R.
  Assignment: coins with VR above the 15-coin median -> MOM, below -> MR.
  Judged on 2024-25 total R (and avgR) against: all-MOM, all-MR, the
  reverse assignment, and 5000 random assignments (same 8/7 split).
  Direct check: Spearman across coins between VR (2020-23) and
  [MOM avgR - MR avgR] in 2024-25. Trait stability: VR 2020-23 vs 2024-25.

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import load_1h, compute_atr, compute_rsi, find_triggers, ROUND_TRIP_FRICTION
from dev_momentum_continuation import flip
from dev_momentum_universe import load_universe_1h

ORIGINAL = ['BTC', 'ETH', 'SOL', 'NEAR', 'AVAX']
MAJORS = ['BNB', 'XRP', 'DOGE', 'ADA', 'LINK', 'LTC', 'DOT', 'BCH', 'TRX', 'UNI']
SPLIT = pd.Timestamp('2024-01-01')
COOLDOWN = 8
N_RANDOM = 5000


def load(base):
    return load_1h(f'{base}/USDT') if base in ORIGINAL else load_universe_1h(base)


def walk(c, h, l, i, sgn, sl, tp, max_hold, atr_i):
    entry = c[i]
    end = min(i + 1 + max_hold, len(c))
    if end <= i + 1:
        return None
    exit_price = c[end - 1]
    for j in range(i + 1, end):
        if (l[j] <= sl) if sgn > 0 else (h[j] >= sl):
            exit_price = sl
            break
        if (h[j] >= tp) if sgn > 0 else (l[j] <= tp):
            exit_price = tp
            break
    return (sgn * (exit_price - entry) / entry - ROUND_TRIP_FRICTION) / (abs(entry - sl) / entry)


def mom_trades(df):
    c, h, l, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
    rows = []
    for i, rev in find_triggers(df):
        if np.isnan(df['vol_ratio'].iloc[i]) or np.isnan(atr[i]):
            continue
        sgn = 1 if flip(rev) == 'long' else -1
        r = walk(c, h, l, i, sgn, c[i] - sgn * 2 * atr[i], c[i] + sgn * 4 * atr[i], 168, atr[i])
        if r is not None:
            rows.append((df['timestamp'].iloc[i], df['vol_ratio'].iloc[i], r))
    t = pd.DataFrame(rows, columns=['time', 'vol_ratio', 'r'])
    t = t[pd.qcut(t['vol_ratio'].rank(method='first'), 3, labels=False) == 2]
    return t[['time', 'r']]


def mr_trades(df):
    c, h, l, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
    mid = df['close'].rolling(20).mean().values
    sd = df['close'].rolling(20).std().values
    up, lo = mid + 2 * sd, mid - 2 * sd
    rows, last = [], -10**9
    for i in range(21, len(df)):
        if i - last <= COOLDOWN or np.isnan(atr[i]) or np.isnan(mid[i]):
            continue
        if c[i] < lo[i] and c[i - 1] >= lo[i - 1]:
            sgn = 1
        elif c[i] > up[i] and c[i - 1] <= up[i - 1]:
            sgn = -1
        else:
            continue
        r = walk(c, h, l, i, sgn, c[i] - sgn * 2 * atr[i], mid[i], 48, atr[i])
        if r is not None:
            rows.append((df['timestamp'].iloc[i], r))
            last = i
    return pd.DataFrame(rows, columns=['time', 'r'])


def variance_ratio(close, q=24):
    lr = np.log(close).diff().dropna()
    rq = np.log(close).diff(q).dropna()
    return rq.var() / (q * lr.var())


def traits(df, btc_daily):
    close = df.set_index('timestamp')['close']
    c4 = close.resample('4h').last().dropna()
    daily = close.resample('1D').last().dropna().pct_change().dropna()
    return dict(vr24=variance_ratio(close), ac4h=np.log(c4).diff().autocorr(lag=1),
                btc_corr=daily.corr(btc_daily.reindex(daily.index)),
                atr_pct=(df['atr'] / df['close']).median() * 100)


def main():
    coins = ORIGINAL + MAJORS
    frames = {}
    for b in coins:
        df = load(b)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        frames[b] = df
    btc = frames['BTC'].set_index('timestamp')['close']

    rows, trades = [], {}
    for b in coins:
        df = frames[b]
        disc, conf = df[df.timestamp < SPLIT], df[df.timestamp >= SPLIT]
        btc_d = btc[btc.index < SPLIT].resample('1D').last().pct_change()
        btc_c = btc[btc.index >= SPLIT].resample('1D').last().pct_change()
        td, tc = traits(disc, btc_d), traits(conf, btc_c)
        m, r = mom_trades(df), mr_trades(df)
        trades[b] = (m, r)
        row = dict(coin=b, **{k + '_disc': v for k, v in td.items()}, vr24_conf=tc['vr24'])
        for name, t in (('mom', m), ('mr', r)):
            for p, mask in (('disc', t.time < SPLIT), ('conf', t.time >= SPLIT)):
                row[f'{name}_n_{p}'] = int(mask.sum())
                row[f'{name}_avgR_{p}'] = t.r[mask].mean()
                row[f'{name}_sumR_{p}'] = t.r[mask].sum()
        rows.append(row)
    d = pd.DataFrame(rows)
    med = d.vr24_disc.median()
    d['assigned'] = np.where(d.vr24_disc > med, 'mom', 'mr')

    pd.set_option('display.width', 220)
    print('=' * 110 + '\nPERSONALITY (measured on 2020-23) AND BOTH STRATEGIES PER COIN')
    show = d[['coin', 'vr24_disc', 'vr24_conf', 'ac4h_disc', 'btc_corr_disc', 'atr_pct_disc', 'assigned',
              'mom_n_disc', 'mom_avgR_disc', 'mr_n_disc', 'mr_avgR_disc',
              'mom_n_conf', 'mom_avgR_conf', 'mr_n_conf', 'mr_avgR_conf']].sort_values('vr24_disc', ascending=False)
    print(show.round(3).to_string(index=False))
    print(f"\n  VR(24) median (assignment cut) = {med:.3f}")
    rho_s, p_s = spearmanr(d.vr24_disc, d.vr24_conf)
    print(f"  trait stability: Spearman VR 2020-23 vs 2024-25 = {rho_s:+.3f} (p={p_s:.3f})")
    for p in ('disc', 'conf'):
        rho, pv = spearmanr(d.vr24_disc, d[f'mom_avgR_{p}'] - d[f'mr_avgR_{p}'])
        print(f"  Spearman VR(2020-23) vs [MOM avgR - MR avgR] in {p}: {rho:+.3f} (p={pv:.3f})")

    def portfolio(assign, p):
        s = sum(d.loc[d.coin == b, f'{assign[b]}_sumR_{p}'].iloc[0] for b in coins)
        n = sum(d.loc[d.coin == b, f'{assign[b]}_n_{p}'].iloc[0] for b in coins)
        return s, s / n, n

    matched = dict(zip(d.coin, d.assigned))
    reverse = {b: ('mr' if a == 'mom' else 'mom') for b, a in matched.items()}
    print('\n' + '=' * 110 + '\nPORTFOLIOS (sum of R over all trades; 1R = one unit of risk per trade)')
    for label, assign in (('personality-matched', matched), ('reverse-matched', reverse),
                          ('all momentum (v7)', {b: 'mom' for b in coins}), ('all mean-reversion', {b: 'mr' for b in coins})):
        out = []
        for p in ('disc', 'conf'):
            s, a, n = portfolio(assign, p)
            out.append(f"{p}: n={n:5d} totalR={s:+8.1f} avgR={a:+.3f}")
        print(f"  {label:22s} " + ' | '.join(out))

    rng = np.random.default_rng(1)
    n_mom = (d.assigned == 'mom').sum()
    sims_s, sims_a = [], []
    for _ in range(N_RANDOM):
        pick = set(rng.choice(coins, n_mom, replace=False))
        s, a, _n = portfolio({b: ('mom' if b in pick else 'mr') for b in coins}, 'conf')
        sims_s.append(s)
        sims_a.append(a)
    s, a, _n = portfolio(matched, 'conf')
    print(f"\n  2024-25 random {n_mom}/{len(coins) - n_mom} assignments ({N_RANDOM}x): totalR median {np.median(sims_s):+.1f}, "
          f"matched beats {(s > np.array(sims_s)).mean()*100:.1f}%;  avgR median {np.median(sims_a):+.3f}, "
          f"matched beats {(a > np.array(sims_a)).mean()*100:.1f}%")
    d.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'coin_personality.csv'), index=False)


if __name__ == '__main__':
    main()
