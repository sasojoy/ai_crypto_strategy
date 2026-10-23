"""
PRE-REGISTERED TEST (RESEARCH_FINDINGS.md "資金費率閘門的獨立驗證", 2026-10-24).

Claim under test (post-hoc finding of 2026-10-18): the directional sleeves
(V7, BRK4H, long BETA) have an edge only in weeks where the BTC funding
rate, 30-day mean annualised, is above 10 %. That breakdown used the same
50-coin streams the sleeves were designed on. Here the claim is checked
on evidence the design did not use:

  G1  35 unseen coins only (the sleeves were built on the 15-coin basket),
      BTC gate: pooled directional weekly return, gate ON minus gate OFF > 0
  G2  all 50 coins, ETH funding as the gate instead of BTC: ON - OFF > 0
  G3  all 50 coins, BTC gate, EXCLUDING the two known frenzies
      (2020-07..2021-12 and 2024-01..2024-06): ON - OFF > 0.
      This is the hard one: does the level matter outside the big bulls?

Streams: weekly R-sums of V7 and BRK4H (dev trades + 2026 holdout trades,
per coin) and weekly BETA log return net of funding, each vol-normalised
(trailing 26-week std, lagged, 1 %/week). "Pooled directional" = mean of
the three normalised streams each week. Gate = funding 30-day mean
annualised at the week's start > 10 %.

Inference: difference of weekly means, 10,000x bootstrap over weeks
(resampling ON and OFF weeks separately), one-sided p = share of
bootstrap differences <= 0. Pass per hypothesis: diff > 0 and p < 0.025.
Overall: the rule counts as independently supported only if G1, G2 and
G3 all pass. G1+G2 without G3 = "only the two big frenzies", which is
two episodes, not a rule.

Printed but not judged: per-sleeve breakdown of each test, a placebo
gate (same series shifted back 52 weeks), and a threshold sweep
5/10/15/20 % on the 35-coin sample.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dev_coin_personality import ORIGINAL, MAJORS  # noqa: E402
from dev_regime_switch import full_daily_panel, normalize, week_of, HOLD, ROOT  # noqa: E402
import brk4h  # noqa: E402
from fetch_holdout_2026 import coins  # noqa: E402

START = pd.Timestamp('2020-07-01')
LAST_WEEK = pd.Timestamp('2026-09-20')
THRESH = 0.10
N_BOOT = 10000
ALPHA = 0.025
SEED = 20261024
FRENZY = [(pd.Timestamp('2020-07-01'), pd.Timestamp('2022-01-01')), (pd.Timestamp('2024-01-01'), pd.Timestamp('2024-07-01'))]


def directional_trades():
    from prereg_vol_trend import build as build_v7_dev
    v7d = build_v7_dev()[['coin', 'time', 'r']]
    v7h = pd.read_csv(os.path.join(ROOT, 'scripts', 'holdout_short_crowding_trades.csv'), parse_dates=['time'])[['coin', 'time', 'r']]
    v7 = pd.concat([v7d, v7h[v7h.time >= '2026-01-01']])
    sq = pd.read_csv(os.path.join(ROOT, 'scripts', 'squeeze_breakout_trades.csv'), parse_dates=['time'])
    bd = sq[(sq.kind == 'control') & (sq.exit == 'fixed3R')][['coin', 'time', 'r']]
    rows = []
    for b in coins():
        h = pd.read_csv(os.path.join(HOLD, f'{b}_USDT_1h.csv'), parse_dates=['timestamp'])
        for t, sgn, status, r in brk4h.signals(brk4h.to_4h(h), pd.Timestamp('2026-01-01')):
            if status != 'OPEN':
                rows.append(dict(coin=b, time=t, r=r))
    return {'V7': v7, 'BRK4H': pd.concat([bd, pd.DataFrame(rows)])}


def weekly_streams(trades, px, funding, coin_set):
    out = {}
    for name, d in trades.items():
        d = d[d.coin.isin(coin_set)]
        out[name] = d.groupby(d.time.map(week_of)).r.sum()
    cols = [c for c in px.columns if c in coin_set]
    wk = px[cols].resample('W-SUN').last()
    ret = np.log(wk).diff().shift(-1)
    fpaid = pd.DataFrame({b: funding[b].groupby(funding[b].index.map(week_of)).sum() for b in cols}).reindex(ret.index).fillna(0.0)
    out['BETA'] = (ret - fpaid.where(ret.notna())).mean(axis=1).dropna()
    s = pd.DataFrame({k: normalize(v) for k, v in out.items()})
    s = s[(s.index >= START) & (s.index <= LAST_WEEK)].fillna(0.0)
    s['DIR'] = s[['V7', 'BRK4H', 'BETA']].mean(axis=1)
    return s


def gate_from(funding, cur, weeks, shift_weeks=0):
    daily = funding[cur].resample('1D').sum()
    ann30 = daily.rolling(30).mean() * 365
    g = ann30.reindex(weeks, method='ffill')
    if shift_weeks:
        g = g.shift(shift_weeks)
    return g


def test(s, gate, rng, label, thresh=THRESH):
    on = (gate > thresh).fillna(False).values
    a, b = s['DIR'].values[on], s['DIR'].values[~on]
    diff = a.mean() - b.mean()
    boot = rng.choice(a, (N_BOOT, len(a))).mean(1) - rng.choice(b, (N_BOOT, len(b))).mean(1)
    p = (boot <= 0).mean()
    ok = diff > 0 and p < ALPHA
    print(f'  {label:44s} on={on.sum():3d}w off={(~on).sum():3d}w  diff={diff*100:+.3f}%/wk  p={p:.4f}  '
          f'Sharpe on/off={sh(a):+.2f}/{sh(b):+.2f}  -> {"PASS" if ok else "FAIL"}')
    for c in ['V7', 'BRK4H', 'BETA']:
        print(f'      {c:6s} Sharpe on/off={sh(s[c].values[on]):+.2f}/{sh(s[c].values[~on]):+.2f}')
    return ok


def sh(x):
    return np.nan if len(x) < 8 or x.std() == 0 else x.mean() / x.std() * np.sqrt(52)


def main():
    rng = np.random.default_rng(SEED)
    px, funding = full_daily_panel()
    trades = directional_trades()
    basket = set(ORIGINAL + MAJORS)
    unseen = set(px.columns) - basket
    s35 = weekly_streams(trades, px, funding, unseen)
    s50 = weekly_streams(trades, px, funding, set(px.columns))
    print(f'weeks {s50.index[0].date()}..{s50.index[-1].date()} n={len(s50)}; 35 unseen coins: {len(unseen)}')
    btc = gate_from(funding, 'BTC', s50.index)
    eth = gate_from(funding, 'ETH', s50.index)
    print(f'gate on-share: BTC {(btc > THRESH).mean()*100:.0f}%  ETH {(eth > THRESH).mean()*100:.0f}%  agreement {((btc > THRESH) == (eth > THRESH)).mean()*100:.0f}%')

    print('\n=== pre-registered ===')
    g1 = test(s35, btc.reindex(s35.index), rng, 'G1 35 unseen coins, BTC gate')
    g2 = test(s50, eth, rng, 'G2 50 coins, ETH gate')
    infr = pd.Series(False, index=s50.index)
    for a, b in FRENZY:
        infr |= (s50.index >= a) & (s50.index < b)
    g3 = test(s50[~infr], btc[~infr], rng, 'G3 50 coins, BTC gate, frenzies excluded')
    print(f'\n  -> G1 {"PASS" if g1 else "FAIL"}  G2 {"PASS" if g2 else "FAIL"}  G3 {"PASS" if g3 else "FAIL"}  '
          f'overall {"SUPPORTED" if (g1 and g2 and g3) else ("BIG-FRENZIES-ONLY" if (g1 and g2) else "NOT SUPPORTED")}')

    print('\n=== descriptive (not judged) ===')
    test(s50, gate_from(funding, 'BTC', s50.index, 52), rng, 'placebo: BTC gate shifted back 52 weeks')
    for th in (0.05, 0.10, 0.15, 0.20):
        test(s35, btc.reindex(s35.index), rng, f'threshold sweep {th*100:.0f}% (35 coins)', thresh=th)
    out = s50.copy()
    out['btc_fund30'] = btc
    out['eth_fund30'] = eth
    out.to_csv(os.path.join(ROOT, 'scripts', 'funding_gate_weekly.csv'))


if __name__ == '__main__':
    main()
