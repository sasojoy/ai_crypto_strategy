"""
DEV-WINDOW ONLY (< 2026-01-01). ANALYSIS, not a new candidate. The mirror
image of dev_momentum_v8_win_scenarios*.py: instead of hunting for setups
where the momentum-continuation signal wins unusually often (that search
found nothing usable as a filter), hunt for setups where it LOSES unusually
often -- "entry templates that almost always fail" -- which could be vetoed
without touching the rest of the signal.

Population: the locked-spec trigger population (RSI(14) cross + top volume
tercile, 1H), simulated with v7's exits (SL=2.0xATR / TP=4.0xATR) as the
primary spec, and v8's TP=3.0xATR as a cross-check.

Anti-data-mining discipline (decided BEFORE running):
  - Every feature and its binning is fixed up front (below); terciles are
    computed per symbol so one coin's scale doesn't dominate.
  - The dev window is split in time: DISCOVERY = 2020-2023, CONFIRMATION =
    2024-2025. A cell only counts as a "loss template" if it is flagged in
    discovery AND still loses in confirmation. The 2026+ holdout is not
    touched.
  - Discovery flag: n >= 40, win rate at least 10 points below the
    discovery baseline, avg R < 0, and one-sided binomial p < 0.01 against
    the baseline win rate.
  - Confirmation pass: win rate below the confirmation baseline AND avg R
    below the confirmation baseline avg R AND avg R < 0.
  - For each confirmed template, the full-dev effect of VETOING it is
    compared to vetoing the same number of randomly chosen trades.

Features (all known at the trigger bar's close):
  direction           long / short
  btc_trend_aligned   BTC close vs BTC EMA200 (1H) agrees with trade direction
  own_trend_aligned   symbol close vs its own EMA200 (1H) agrees with direction
  rsi_depth           how far RSI is past the 30/70 line (terciles)
  vol_ratio           volume / 20-bar mean (terciles, within the top tercile)
  adx                 ADX(14) (terciles)
  extension_atr       10-bar move in trade direction, ATR units (terciles)
  room_7d_atr         distance left to the 7-day extreme in trade direction,
                      ATR units (terciles; low = entering right at a new
                      7-day high for a long / low for a short)
  against_wick        trigger bar's wick against the trade, share of bar
                      range (terciles; high = the bar was rejected)
  atr_regime          ATR/close vs its own trailing 90-day median (terciles)
  ret_7d_aligned      7-day return in trade direction (terciles)
  session             UTC hour 0-7 / 8-15 / 16-23
  weekend             Saturday/Sunday UTC

Single features are tested alone and crossed with direction (the known
long/short asymmetry makes direction the one pre-registered interaction).

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import binomtest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import MAX_HOLD_BARS, ROUND_TRIP_FRICTION
from dev_momentum_tighter_tp import build_candidates, SL_MULT
from dev_momentum_adx_trend_filter import compute_adx

TP_PRIMARY = 4.0   # v7 (and v1): 2:1
TP_CHECK = 3.0     # v8: 1.5:1
SPLIT = pd.Timestamp('2024-01-01')
MIN_N = 40
MIN_GAP_PP = 10.0
MAX_P = 0.01
N_RANDOM = 2000

TERCILE_FEATURES = ['rsi_depth', 'vol_ratio', 'adx', 'extension_atr', 'room_7d_atr',
                    'against_wick', 'atr_regime', 'ret_7d_aligned']
CATEGORICAL_FEATURES = ['btc_trend_aligned', 'own_trend_aligned', 'session', 'weekend']


def simulate_r(close, high, low, atr, i, direction, tp_mult):
    """Same mechanics as dev_momentum_tighter_tp.simulate_trade (SL checked
    first within a bar), but returns the result in R (net of friction)."""
    entry = close[i]
    end = min(i + 1 + MAX_HOLD_BARS, len(close))
    if end <= i + 1 or np.isnan(atr[i]) or atr[i] <= 0:
        return None
    sgn = 1 if direction == 'long' else -1
    sl = entry - sgn * SL_MULT * atr[i]
    tp = entry + sgn * tp_mult * atr[i]
    exit_price, reason = None, None
    for j in range(i + 1, end):
        if (low[j] <= sl) if sgn > 0 else (high[j] >= sl):
            exit_price, reason = sl, 'SL'
            break
        if (high[j] >= tp) if sgn > 0 else (low[j] <= tp):
            exit_price, reason = tp, 'TP'
            break
    if exit_price is None:
        exit_price, reason = close[end - 1], 'TIMEOUT'
    pnl = sgn * (exit_price - entry) / entry - ROUND_TRIP_FRICTION
    return reason, pnl / (SL_MULT * atr[i] / entry)


def add_indicators(frames):
    btc = frames['BTC/USDT'][['timestamp', 'close']].copy()
    btc['btc_above_ema200'] = btc['close'] > btc['close'].ewm(span=200, adjust=False).mean()
    btc = btc.set_index('timestamp')['btc_above_ema200']
    for s, df in frames.items():
        df['adx'] = compute_adx(df)
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['high_7d'] = df['high'].rolling(168).max()
        df['low_7d'] = df['low'].rolling(168).min()
        atr_pct = df['atr'] / df['close']
        df['atr_regime'] = atr_pct / atr_pct.rolling(90 * 24, min_periods=30 * 24).median()
        df['ret_7d'] = df['close'] / df['close'].shift(168) - 1
        df['ret_10'] = df['close'] - df['close'].shift(10)
        df['btc_above_ema200'] = btc.reindex(df['timestamp']).values


def features(df, i, direction):
    r = df.iloc[i]
    if i < 200 or np.isnan(r['atr']) or r['atr'] <= 0 or np.isnan(r['atr_regime']) or np.isnan(r['ret_7d']):
        return None
    sgn = 1 if direction == 'long' else -1
    rng = r['high'] - r['low']
    if sgn > 0:
        wick = (r['high'] - max(r['open'], r['close'])) / rng if rng > 0 else 0.0
        room = (r['high_7d'] - r['close']) / r['atr']
    else:
        wick = (min(r['open'], r['close']) - r['low']) / rng if rng > 0 else 0.0
        room = (r['close'] - r['low_7d']) / r['atr']
    btc_up = r['btc_above_ema200']
    hour = r['timestamp'].hour
    return {
        'btc_trend_aligned': None if pd.isna(btc_up) else bool(btc_up) == (sgn > 0),
        'own_trend_aligned': (r['close'] > r['ema200']) == (sgn > 0),
        'rsi_depth': (r['rsi'] - 70) if sgn > 0 else (30 - r['rsi']),
        'vol_ratio': r['vol_ratio'],
        'adx': r['adx'],
        'extension_atr': sgn * r['ret_10'] / r['atr'],
        'room_7d_atr': room,
        'against_wick': wick,
        'atr_regime': r['atr_regime'],
        'ret_7d_aligned': sgn * r['ret_7d'],
        'session': '00-07' if hour < 8 else ('08-15' if hour < 16 else '16-23'),
        'weekend': r['timestamp'].weekday() >= 5,
    }


def cell_stats(sub):
    n = len(sub)
    if n == 0:
        return dict(n=0, win=np.nan, avg_r=np.nan, sum_r=0.0)
    return dict(n=n, win=(sub['r'] > 0).mean() * 100, avg_r=sub['r'].mean(), sum_r=sub['r'].sum())


def pf(r):
    neg = -r[r < 0].sum()
    return r[r > 0].sum() / neg if neg > 0 else np.inf


def build_dataset():
    candidates, frames = build_candidates()
    add_indicators(frames)
    rows = []
    for row in candidates.itertuples():
        df = frames[row.symbol]
        f = features(df, row.idx, row.direction)
        if f is None:
            continue
        close, high, low, atr = df['close'].values, df['high'].values, df['low'].values, df['atr'].values
        out4 = simulate_r(close, high, low, atr, row.idx, row.direction, TP_PRIMARY)
        out3 = simulate_r(close, high, low, atr, row.idx, row.direction, TP_CHECK)
        if out4 is None or out3 is None:
            continue
        rows.append({'symbol': row.symbol, 'direction': row.direction, 'entry_time': row.entry_time,
                     'reason': out4[0], 'r': out4[1], 'r_tp3': out3[1], **f})
    d = pd.DataFrame(rows)
    for feat in TERCILE_FEATURES:
        d[feat + '_bin'] = d.groupby('symbol')[feat].transform(
            lambda x: pd.qcut(x.rank(method='first'), 3, labels=['T1_low', 'T2_mid', 'T3_high'])).astype(str)
    for feat in CATEGORICAL_FEATURES:
        d[feat + '_bin'] = d[feat].astype(str)
    d['period'] = np.where(d['entry_time'] < SPLIT, 'discovery', 'confirmation')
    return d


def enumerate_cells(d):
    """(label, boolean mask) for every pre-registered cell."""
    cells = []
    for direction in ('long', 'short'):
        cells.append((f'direction={direction}', d['direction'] == direction))
    for feat in TERCILE_FEATURES + CATEGORICAL_FEATURES:
        col = feat + '_bin'
        for val in sorted(d[col].unique()):
            if val in ('None', 'nan'):
                continue
            base = d[col] == val
            cells.append((f'{feat}={val}', base))
            for direction in ('long', 'short'):
                cells.append((f'{direction} & {feat}={val}', base & (d['direction'] == direction)))
    return cells


def main():
    print('Building locked-spec population + features (dev window only)...')
    d = build_dataset()
    disc, conf = d[d.period == 'discovery'], d[d.period == 'confirmation']
    b_disc, b_conf, b_all = cell_stats(disc), cell_stats(conf), cell_stats(d)
    print(f"\nTrades: {len(d)}  (discovery 2020-2023: {len(disc)}, confirmation 2024-2025: {len(conf)})")
    for name, b in (('discovery', b_disc), ('confirmation', b_conf), ('all dev', b_all)):
        print(f"  baseline {name:12s}: win {b['win']:.1f}%  avgR {b['avg_r']:+.3f}")
    print(f"  full-dev PF (TP4) {pf(d['r']):.3f}   sumR {d['r'].sum():+.1f}")

    cells = enumerate_cells(d)
    print(f"\n{len(cells)} pre-registered cells scanned.")
    rows = []
    for label, mask in cells:
        sd, sc = cell_stats(d[mask & (d.period == 'discovery')]), cell_stats(d[mask & (d.period == 'confirmation')])
        if sd['n'] == 0:
            continue
        wins = int(round(sd['win'] / 100 * sd['n']))
        p = binomtest(wins, sd['n'], b_disc['win'] / 100, alternative='less').pvalue
        flagged = (sd['n'] >= MIN_N and sd['win'] <= b_disc['win'] - MIN_GAP_PP
                   and sd['avg_r'] < 0 and p < MAX_P)
        confirmed = flagged and sc['n'] > 0 and sc['win'] < b_conf['win'] and sc['avg_r'] < b_conf['avg_r'] and sc['avg_r'] < 0
        rows.append(dict(cell=label, d_n=sd['n'], d_win=sd['win'], d_avgR=sd['avg_r'], p=p,
                         c_n=sc['n'], c_win=sc['win'], c_avgR=sc['avg_r'], flagged=flagged, confirmed=confirmed,
                         mask=mask))
    res = pd.DataFrame(rows)

    pd.set_option('display.width', 200)
    cols = ['cell', 'd_n', 'd_win', 'd_avgR', 'p', 'c_n', 'c_win', 'c_avgR', 'confirmed']
    print('\n' + '=' * 100 + '\nWORST 25 CELLS IN DISCOVERY (n>=40), by win rate')
    print(res[res.d_n >= MIN_N].nsmallest(25, 'd_win')[cols].round(3).to_string(index=False))

    flagged = res[res.flagged]
    print('\n' + '=' * 100 + f'\nFLAGGED IN DISCOVERY: {len(flagged)}   CONFIRMED IN 2024-2025: {int(res.confirmed.sum())}')
    print(flagged[cols].round(3).to_string(index=False) if len(flagged) else '  (none)')

    rng = np.random.default_rng(7)
    print('\n' + '=' * 100 + '\nVETO EFFECT on the full dev window (confirmed cells only)')
    print(f"{'cell':40s} {'vetoed':>6} {'vet win%':>8} {'vet avgR':>8} {'PF after':>8} {'dSumR':>7} "
          f"{'beat rand':>9} {'PF TP3 before->after':>21}")
    for _, row in res[res.confirmed].iterrows():
        mask = row['mask'].values
        kept, vetoed = d[~mask], d[mask]
        d_sum = kept['r'].sum() - d['r'].sum()
        rand = np.array([-d['r'].values[rng.choice(len(d), size=mask.sum(), replace=False)].sum() for _ in range(N_RANDOM)])
        beat = (d_sum > rand).mean() * 100
        print(f"{row['cell']:40s} {mask.sum():6d} {(vetoed['r'] > 0).mean()*100:8.1f} {vetoed['r'].mean():+8.3f} "
              f"{pf(kept['r']):8.3f} {d_sum:+7.1f} {beat:8.1f}% {pf(d['r_tp3']):9.3f} -> {pf(kept['r_tp3']):.3f}")
        by_year = vetoed.assign(y=pd.to_datetime(vetoed.entry_time).dt.year).groupby('y')['r'].agg(['count', 'mean'])
        by_sym = vetoed.groupby('symbol')['r'].agg(['count', 'mean'])
        print('    per year  ' + '  '.join(f"{y}:{int(c)}/{m:+.2f}" for y, (c, m) in by_year.iterrows()))
        print('    per coin  ' + '  '.join(f"{s.split('/')[0]}:{int(c)}/{m:+.2f}" for s, (c, m) in by_sym.iterrows()))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loss_templates_trades.csv')
    d.to_csv(out, index=False)
    print(f'\nTrade-level features saved to {out}')


if __name__ == '__main__':
    main()
