"""
DESCRIPTIVE (no hypothesis, 2026-10-17): history of the BTC quarterly-futures
basis on Binance USDT-M. Cash-and-carry held to expiry locks ln(F/S) with no
prediction (convergence is mechanical), so the question is only "how big
was the basis, how often, and what did holding to expiry pay net of cost".
S = perp close of the 23:00 UTC bar (same end-of-day as the 1d close; perp ~ spot), F = quarterly 1d close,
contracts with 20..120 days to expiry, cost 0.28% round trip. Margin risk
(short futures leg marked to market during a rally) reported as the max
adverse move of F from entry to expiry.
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', 'backtest_cache')
COST = 0.0028

q = pd.read_csv(os.path.join(CACHE, 'quarterly', 'BTCUSDT_quarterly_1d.csv'), parse_dates=['timestamp', 'expiry'])
full = pd.read_csv(os.path.join(CACHE, 'BTC_USDT_1h_full.csv'), parse_dates=['timestamp'])
fwd = pd.read_csv(os.path.join(ROOT, 'data', 'forward', 'BTC_USDT_1h.csv'), parse_dates=['timestamp'])
px = pd.concat([full, fwd]).drop_duplicates('timestamp').sort_values('timestamp').set_index('timestamp')['close']
# quarterly 1d close is the END of the day; align with the perp close of the 23:00 bar of the same day
spot = px[px.index.hour == 23]
spot.index = spot.index.normalize()

q['dte'] = (q['expiry'] - q['timestamp']).dt.total_seconds() / 86400
q = q[(q.dte >= 20) & (q.dte <= 120)].copy()
q['spot'] = spot.reindex(q['timestamp']).values
q = q.dropna(subset=['spot'])
q['basis'] = np.log(q['close'] / q['spot'])
q['ann'] = q['basis'] * 365 / q['dte']
# realised: hold to expiry -> basis locked (F converges to S at settlement)
q['hold_ret'] = q['basis'] - COST
# max adverse move on the short futures leg during the hold
maxf = q.groupby('contract')['close'].transform(lambda s: s[::-1].cummax()[::-1])
q['max_adverse'] = maxf / q['close'] - 1

print('Annualised basis by year (days with a 20-120 dte contract):')
for y, g in q.groupby(q.timestamp.dt.year):
    print(f'  {y}: days={g.timestamp.nunique():4d}  median={g.ann.median()*100:5.1f}%  p90={g.ann.quantile(.9)*100:5.1f}%  '
          f'>10%: {(g.ann>0.10).mean()*100:3.0f}% of days  >20%: {(g.ann>0.20).mean()*100:3.0f}%  max={g.ann.max()*100:5.1f}%')

print('\nRule "enter when annualised basis >= X, hold to expiry" (one entry per contract, first qualifying day):')
for X in [0.05, 0.10, 0.15, 0.20]:
    e = q[q.ann >= X].sort_values('timestamp').groupby('contract').first()
    if e.empty:
        print(f'  X={X*100:.0f}%: never'); continue
    yrs = (q.timestamp.max() - q.timestamp.min()).days / 365.25
    print(f'  X={X*100:.0f}%: entries={len(e)}  mean hold={e.dte.mean():.0f}d  mean net per trade={e.hold_ret.mean()*100:+.2f}%  '
          f'total={e.hold_ret.sum()*100:+.1f}% over {yrs:.1f}y  worst adverse move on short leg={e.max_adverse.max()*100:+.0f}%  '
          f'years: {sorted(set(e.timestamp.dt.year))}')
