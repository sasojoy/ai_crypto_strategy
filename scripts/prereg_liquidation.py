"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "新方向G：爆倉連鎖後的反轉", 2026-10-24).
Sample: the only liquidation history Binance publishes -- COIN-M
BTCUSD_PERP and ETHUSD_PERP liquidation snapshots, 2023-06-25 ..
2024-10-14 (data/backtest_cache/liquidations, fetch_liquidations.py).
Price reaction measured on the USDT-M perp 5-minute bars (universe_5m).
All of this is before 2026, so it is dev-window data; there is no 2026
liquidation history, so no holdout exists for this direction.

Forced flow per 5-minute bar: SELL-side liquidations = longs being
closed by force (forced selling); BUY-side = shorts (forced buying).
Notional = contracts x 100 USD (BTC) / x 10 USD (ETH). net_t = forced
buying minus forced selling in bar t. Event: |net_t| above the 99th
percentile of the trailing 30 days of |net| (causal), no re-trigger
within 6 bars. Direction d = -sign(net_t) (fade the forced flow).

  H_G1  reversal: mean(d * log(c[t+3] / c[t])) > 0   (15 minutes after
        the event bar closes)
  H_G2  maker-tradable, same fill rule as direction D: limit at c[t]
        against the move, filled only if bar t+1 trades through it by
        2 bp, exit at the close of bar t+4, cost 0.09 %; mean net > 0.

Inference: events pooled across BTC and ETH, one-sided t-test and
10,000x bootstrap, alpha 0.025 per hypothesis. Pass = pooled mean > 0,
p < 0.025, BTC > 0 and ETH > 0, same sign in the first and second half
of the sample (split 2024-02-15). Breakdowns only after a pass.
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIQ = os.path.join(ROOT, 'data', 'backtest_cache', 'liquidations')
U5M = os.path.join(ROOT, 'data', 'backtest_cache', 'universe_5m')
CONTRACT_USD = {'BTC': 100.0, 'ETH': 10.0}
PCT, PWIN_BARS, COOLDOWN, HOLD, THROUGH, COST = 0.99, 288 * 30, 6, 3, 2e-4, 0.0009
SPLIT = pd.Timestamp('2024-02-15')
N_BOOT, ALPHA, SEED = 10000, 0.025, 20261024


def events(base):
    liq = pd.read_csv(os.path.join(LIQ, f'{base}USD_PERP_liquidations.csv'))
    liq['t'] = pd.to_datetime(liq['time'], unit='ms').dt.floor('5min')
    liq['usd'] = liq['last_fill_quantity'] * CONTRACT_USD[base]
    signed = liq['usd'].where(liq['side'] == 'BUY', -liq['usd'])
    net = signed.groupby(liq['t']).sum()
    px = pd.read_csv(os.path.join(U5M, f'{base}_USDT_5m.csv'), parse_dates=['timestamp']).set_index('timestamp')
    px = px[(px.index >= net.index.min() - pd.Timedelta(days=31)) & (px.index <= net.index.max() + pd.Timedelta(hours=1))]
    net = net.reindex(px.index).fillna(0.0)
    thr = net.abs().rolling(PWIN_BARS, min_periods=288 * 10).quantile(PCT).shift(1)
    c, h, l = px['close'].values, px['high'].values, px['low'].values
    idx = np.where((net.abs() > thr) & (thr > 0))[0]
    rows, last = [], -10
    for t in idx:
        if t - last < COOLDOWN or t + HOLD + 1 >= len(c):
            continue
        last = t
        d = -np.sign(net.iloc[t])
        y1 = d * np.log(c[t + HOLD] / c[t])
        P = c[t]
        filled = (l[t + 1] < P * (1 - THROUGH)) if d > 0 else (h[t + 1] > P * (1 + THROUGH))
        y2 = d * np.log(c[t + 1 + HOLD] / P) - COST if filled else np.nan
        rows.append((base, px.index[t], d, net.iloc[t], y1, filled, y2))
    return pd.DataFrame(rows, columns=['coin', 'time', 'dir', 'net_usd', 'y1', 'filled', 'y2'])


def infer(x, rng):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 20:
        return np.nan, np.nan, np.nan, len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    boot = rng.choice(x, (N_BOOT, len(x))).mean(1)
    return x.mean(), t, (boot <= 0).mean(), len(x)


def main():
    rng = np.random.default_rng(SEED)
    d = pd.concat([events('BTC'), events('ETH')], ignore_index=True)
    d['half'] = np.where(d.time < SPLIT, 'H1', 'H2')
    print(f'events={len(d)}  BTC={int((d.coin == "BTC").sum())}  ETH={int((d.coin == "ETH").sum())}  '
          f'{d.time.min().date()}..{d.time.max().date()}  fill rate={d.filled.mean()*100:.0f}%  '
          f'median |net|=${d.net_usd.abs().median()/1e6:.2f}M')
    for col, name in [('y1', 'H_G1 15-min reversal after a liquidation cascade'), ('y2', 'H_G2 maker-entry tradable (net 0.09%)')]:
        print(f'\n=== {name} ===')
        res = {}
        for label, sub in [('pooled', d), ('BTC', d[d.coin == 'BTC']), ('ETH', d[d.coin == 'ETH']),
                           ('H1', d[d.half == 'H1']), ('H2', d[d.half == 'H2'])]:
            mean, t, p, n = infer(sub[col], rng)
            res[label] = (mean, p)
            print(f'  {label:6s} mean={mean*1e4:+7.1f} bp  t={t:+5.2f}  p={p:.4f}  n={n}')
        ok = (res['pooled'][0] > 0 and res['pooled'][1] < ALPHA and res['BTC'][0] > 0 and res['ETH'][0] > 0
              and res['H1'][0] > 0 and res['H2'][0] > 0)
        print(f'  -> {name.split()[0]} {"PASS" if ok else "FAIL"}')
        if ok:
            for lab, m in [('after forced selling (long)', d.dir > 0), ('after forced buying (short)', d.dir < 0)]:
                mean, t, p, n = infer(d.loc[m, col], rng)
                print(f'    {lab:28s} n={n}  mean={mean*1e4:+.1f} bp')
            q = pd.qcut(d.net_usd.abs(), 3, labels=['small', 'mid', 'large'])
            for lab in ['small', 'mid', 'large']:
                mean, t, p, n = infer(d.loc[q == lab, col], rng)
                print(f'    size {lab:5s} n={n}  mean={mean*1e4:+.1f} bp')
    d.to_csv(os.path.join(ROOT, 'scripts', 'liquidation_events.csv'), index=False)


if __name__ == '__main__':
    main()
