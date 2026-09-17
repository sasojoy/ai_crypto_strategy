"""
DEV-WINDOW ONLY (< 2026-01-01). Tests the user's proposed refinement to
momentum_monitor_v3.py's volume-CONFIRMATION checkpoint (not its entry
mechanism, which is taken as-is): today, once an anticipatory entry fires
intra-hour, the position rides fully unconfirmed until the entry hour's 1H
bar actually closes, at which point the REAL final volume ratio is checked
against the (non-causal) top-tercile cutoff -- if it fails, the position is
closed immediately (VOL_UNCONFIRMED). v3's own docstring already reports
this happens to ~49% of entries, closing out at a small average PROFIT
(+0.14%), not a loss.

The user's question: instead of waiting the full remaining time in the hour
before ever re-checking, should the monitor keep re-projecting volume in
real time after entry and bail out EARLY once the projection looks like it
will clearly miss the bar -- shortening the window where an ultimately-
unconfirmed position is still exposed to SL/TP risk on a signal that (per
the checkpoint's own base rate) fails roughly half the time?

METHODOLOGY:
Replicates momentum_monitor_v3.py's entry mechanism exactly (same
threshold_price() solve from the last closed bar's Wilder RSI state, same
real-time projected-volume-ratio gate against the per-symbol CAUSAL cutoff,
checked across EVERY hour of the dev window -- not just RSI-cross hours --
using the full 2020-2025 1-minute cache) on all 5 symbols. Cutoffs
(causal + non-causal top-tercile) are calibrated fresh from this dev
window's own RSI-cross trigger population (mirroring
paper_trading/calibrate_momentum_threshold.py's method) rather than reusing
the live thresholds.json, which is calibrated on data through 2026-09-08 --
after the dev cutoff -- and would leak forward information into this
backtest.

For each entry, computes:
  - natural_exit: the SL=2xATR/TP=4xATR/168-bar-hold resolution completely
    IGNORING volume confirmation (i.e. "what would happen if this position
    were just held to its normal conclusion").
  - confirmed_at_hour_end: whether the entry hour's REAL final volume ratio
    (using that hour's own actual closed 1H bar, non-causal MA) clears the
    non-causal cutoff -- the existing ground-truth check.
  - a per-minute timeline of the CAUSAL projected ratio from entry through
    hour-end (the same metric already used at entry, just kept running).

A policy is then just "the earliest of: natural_exit, an early-reject
trigger (if the policy defines one and it fires before hour-end), or an
hour-end VOL_UNCONFIRMED close (if the position isn't confirmed and hasn't
already resolved by then)" -- this reproduces the exact shipped baseline
when no early-reject rule is supplied, and isolates precisely what an
early-reject rule changes.

EARLY-REJECT rule tested: "once at least K minutes into the entry hour, if
the running causal-projected ratio has fallen below FRAC times the causal
cutoff, close immediately at that minute's price (reason EARLY_REJECT)."
K in {15, 30, 45} minutes, FRAC in {0.5, 0.75, 1.0}, fixed a priori (a 3x3
grid, not tuned after looking at results) -- FRAC=1.0 is the most
aggressive variant (reject as soon as the projection dips below the entry
bar itself, no safety margin).

Not part of the deployed app; safe to delete after use.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dev_volume_confirm import (
    SYMBOLS, load_1h, compute_atr, compute_rsi, find_triggers,
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'backtest_cache')
ALPHA = 1 / 14  # Wilder RSI(14) smoothing factor, same as momentum_monitor_v3.py
MAX_HOLD_MINUTES = MAX_HOLD_BARS * 60  # 168 hours -> minutes

EARLY_REJECT_K_MINUTES = [15, 30, 45]
EARLY_REJECT_FRAC = [0.5, 0.75, 1.0]


def compute_rsi_state(close):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=ALPHA, adjust=False).mean()
    avg_loss = loss.ewm(alpha=ALPHA, adjust=False).mean()
    return avg_gain, avg_loss


def threshold_price(prev_close, avg_gain_prev, avg_loss_prev, target_rsi):
    a = ALPHA
    if target_rsi == 30:
        ag_new = avg_gain_prev * (1 - a)
        al_new = ag_new * 70 / 30
        loss = (al_new - avg_loss_prev * (1 - a)) / a
        return prev_close - loss
    elif target_rsi == 70:
        al_new = avg_loss_prev * (1 - a)
        ag_new = al_new * 70 / 30
        gain = (ag_new - avg_gain_prev * (1 - a)) / a
        return prev_close + gain
    raise ValueError(target_rsi)


def load_1m_dev(symbol):
    path = os.path.join(CACHE_DIR, symbol.replace('/', '_') + '_1m_devwindow.csv')
    df = pd.read_csv(path, parse_dates=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    return df


def calibrate_dev_cutoffs(df_1h, symbol):
    """Same method as paper_trading/calibrate_momentum_threshold.py, restricted
    to this symbol's dev-window 1H trigger population (RSI(14) cross <30 or
    >70, momentum-continuation direction irrelevant here -- only the vol_ratio
    at those bars matters)."""
    triggers = find_triggers(df_1h)
    ratios = [df_1h['vol_ratio'].iloc[i] for i, _ in triggers if not np.isnan(df_1h['vol_ratio'].iloc[i])]
    ratios_causal = [df_1h['vol_ratio_causal'].iloc[i] for i, _ in triggers if not np.isnan(df_1h['vol_ratio_causal'].iloc[i])]
    cutoff = float(pd.Series(ratios).quantile(2 / 3))
    cutoff_causal = float(pd.Series(ratios_causal).quantile(2 / 3))
    return cutoff, cutoff_causal, len(ratios)


def leg_pnl_pct(direction, entry_price, exit_price, sl_price):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0


def simulate_symbol(symbol):
    df = load_1h(symbol)
    df['rsi'] = compute_rsi(df['close'])
    df['atr'] = compute_atr(df)
    ag, al = compute_rsi_state(df['close'])
    df['avg_gain'], df['avg_loss'] = ag, al
    df['vol_ma20'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma20']
    df['vol_ma20_causal'] = df['vol_ma20'].shift(1)
    df['vol_ratio_causal'] = df['volume'] / df['vol_ma20_causal']

    cutoff, cutoff_causal, n_calib = calibrate_dev_cutoffs(df, symbol)

    dfm = load_1m_dev(symbol)
    ts1h = df['timestamp'].values
    close1h, atr1h, agv, alv = df['close'].values, df['atr'].values, df['avg_gain'].values, df['avg_loss'].values
    vol_ma20_causal_1h, vol_ratio_1h = df['vol_ma20_causal'].values, df['vol_ratio'].values

    ts1m = dfm['timestamp'].values
    high1m, low1m, close1m, vol1m = dfm['high'].values, dfm['low'].values, dfm['close'].values, dfm['volume'].values
    n1m = len(ts1m)

    trades = []
    n_hours_checked = 0
    last_entry_time = None
    for H in range(30, len(df) - 1):
        if np.isnan(agv[H - 1]) or np.isnan(alv[H - 1]) or np.isnan(atr1h[H - 1]) or atr1h[H - 1] <= 0:
            continue
        vma = vol_ma20_causal_1h[H]  # == mean of the 20 bars ending at H-1
        if np.isnan(vma) or vma <= 0:
            continue

        hour_start = ts1h[H]
        if last_entry_time is not None and (hour_start - last_entry_time) < np.timedelta64(8, 'h'):
            continue  # 8-hour per-symbol cooldown, matching momentum_monitor_v3.py's COOLDOWN_HOURS
        hour_end = hour_start + np.timedelta64(1, 'h')
        i0 = np.searchsorted(ts1m, hour_start, side='left')
        i1 = np.searchsorted(ts1m, hour_end, side='left')
        if i1 - i0 < 1:
            continue
        n_hours_checked += 1

        thr_long = threshold_price(close1h[H - 1], agv[H - 1], alv[H - 1], 70)
        thr_short = threshold_price(close1h[H - 1], agv[H - 1], alv[H - 1], 30)

        vol_h = vol1m[i0:i1]
        high_h, low_h, close_h = high1m[i0:i1], low1m[i0:i1], close1m[i0:i1]
        cumvol = np.cumsum(vol_h)
        minutes = np.arange(1, len(vol_h) + 1)
        projected_ratio = cumvol * (60.0 / minutes) / vma
        long_touch = high_h >= thr_long
        short_touch = low_h <= thr_short
        vol_ok = projected_ratio >= cutoff_causal
        qualifying = np.where(long_touch, vol_ok, np.where(short_touch, vol_ok, False))
        if not qualifying.any():
            continue
        k_rel = int(np.argmax(qualifying))
        direction = 'long' if long_touch[k_rel] else 'short'
        entry_price = thr_long if direction == 'long' else thr_short
        entry_idx = i0 + k_rel
        atr_sizing = atr1h[H - 1]
        sl_price = entry_price - SL_ATR_MULT * atr_sizing if direction == 'long' else entry_price + SL_ATR_MULT * atr_sizing
        tp_price = entry_price + TP_ATR_MULT * atr_sizing if direction == 'long' else entry_price - TP_ATR_MULT * atr_sizing

        # natural exit: SL/TP/TIMEOUT chase from entry, ignoring confirmation entirely
        end_idx = min(entry_idx + MAX_HOLD_MINUTES, n1m)
        if end_idx <= entry_idx + 1:
            continue
        fut_high, fut_low, fut_close = high1m[entry_idx:end_idx], low1m[entry_idx:end_idx], close1m[entry_idx:end_idx]
        if direction == 'long':
            sl_hit = fut_low <= sl_price
            tp_hit = fut_high >= tp_price
        else:
            sl_hit = fut_high >= sl_price
            tp_hit = fut_low <= tp_price
        first_sl = np.argmax(sl_hit) if sl_hit.any() else None
        first_tp = np.argmax(tp_hit) if tp_hit.any() else None
        if first_sl is None and first_tp is None:
            if end_idx - entry_idx < MAX_HOLD_MINUTES and end_idx == n1m:
                continue  # ran off the end of available data before resolving -- drop (edge effect)
            nat_rel, nat_reason = MAX_HOLD_MINUTES - 1, 'TIMEOUT'
        elif first_tp is None or (first_sl is not None and first_sl <= first_tp):
            nat_rel, nat_reason = first_sl, 'SL'
        else:
            nat_rel, nat_reason = first_tp, 'TP'
        nat_rel = min(nat_rel, len(fut_close) - 1)
        nat_idx = entry_idx + nat_rel
        nat_time, nat_price = ts1m[nat_idx], (sl_price if nat_reason == 'SL' else tp_price if nat_reason == 'TP' else fut_close[nat_rel])

        confirmed = bool(vol_ratio_1h[H] >= cutoff) if not np.isnan(vol_ratio_1h[H]) else False
        hour_end_price = close1h[H]

        # per-minute checkpoints from entry through hour-end (for early-reject candidates)
        chk_end_rel = i1 - i0  # relative to hour start, exclusive
        chk_minutes = minutes[k_rel:chk_end_rel]  # minutes-into-hour, 1-indexed
        chk_ratio = projected_ratio[k_rel:chk_end_rel]
        chk_time = ts1m[i0 + k_rel: i0 + chk_end_rel]
        chk_price = close1m[i0 + k_rel: i0 + chk_end_rel]

        last_entry_time = ts1m[entry_idx]
        trades.append(dict(
            symbol=symbol, direction=direction, entry_time=hour_start, entry_price=entry_price,
            sl_price=sl_price, tp_price=tp_price, hour_end=hour_end, hour_end_price=hour_end_price,
            confirmed=confirmed, nat_time=nat_time, nat_price=nat_price, nat_reason=nat_reason,
            chk_minutes=chk_minutes, chk_ratio=chk_ratio, chk_time=chk_time, chk_price=chk_price,
            cutoff_causal=cutoff_causal,
        ))

    return trades, dict(symbol=symbol, cutoff=cutoff, cutoff_causal=cutoff_causal, n_calib=n_calib,
                         n_hours_checked=n_hours_checked, n_entries=len(trades))


def resolve_policy(trade, early_reject=None):
    """early_reject: (K_minutes, frac) or None for baseline."""
    candidates = [(trade['nat_time'], trade['nat_price'], trade['nat_reason'])]
    if early_reject is not None:
        K, frac = early_reject
        mask = (trade['chk_minutes'] >= K) & (trade['chk_ratio'] < trade['cutoff_causal'] * frac)
        if mask.any():
            m_rel = int(np.argmax(mask))
            candidates.append((trade['chk_time'][m_rel], trade['chk_price'][m_rel], 'EARLY_REJECT'))
    if trade['hour_end'] < trade['nat_time'] and not trade['confirmed']:
        candidates.append((trade['hour_end'], trade['hour_end_price'], 'VOL_UNCONFIRMED'))
    return min(candidates, key=lambda c: c[0])


def stats_for(trades, early_reject=None):
    rows = []
    for t in trades:
        _, price, reason = resolve_policy(t, early_reject)
        pnl = leg_pnl_pct(t['direction'], t['entry_price'], price, t['sl_price'])
        rows.append(dict(pnl=pnl, reason=reason, entry_time=t['entry_time']))
    d = pd.DataFrame(rows)
    if d.empty:
        return None
    n = len(d)
    wr = (d['pnl'] > 0).mean() * 100
    gw = d[d['pnl'] > 0]['pnl'].sum()
    gl = -d[d['pnl'] <= 0]['pnl'].sum()
    pf = gw / gl if gl > 0 else float('inf')
    # NOTE: trades overlap heavily (many concurrent open positions across symbols/hours), so
    # naively compounding one account through them in entry-time order (as the simpler, low-
    # overlap dev scripts do) produces a meaningless number here -- reported instead as an
    # additive total (sum of each trade's already risk-normalized equity_pnl_pct, as if each
    # signal got its own independent capital slice, the same assumption the live portfolio-risk
    # budget makes when it allows several concurrent positions at once).
    years = (d['entry_time'].max() - d['entry_time'].min()) / np.timedelta64(365, 'D')
    total_pnl = d['pnl'].sum()
    ann_additive = total_pnl / years if years > 0 else float('nan')
    reason_counts = d['reason'].value_counts().to_dict()
    return dict(n=n, win_rate=wr, pf=pf, total_pnl=total_pnl, avg_pnl=d['pnl'].mean(),
                annualized_additive=ann_additive, reasons=reason_counts)


def main():
    all_trades = []
    print("Simulating v3's anticipatory-entry mechanism hour-by-hour across the dev window (2020-2025)...")
    for s in SYMBOLS:
        trades, info = simulate_symbol(s)
        all_trades.extend(trades)
        print(f"  {s}: cutoff={info['cutoff']:.3f} causal_cutoff={info['cutoff_causal']:.3f} "
              f"(from {info['n_calib']} RSI-cross triggers) | {info['n_hours_checked']} hours checked, "
              f"{info['n_entries']} entries fired")

    print(f"\nTotal entries across all 5 symbols: {len(all_trades)}\n")

    print(f"{'='*78}\nBASELINE (wait for hour close, current shipped momentum_monitor_v3.py)\n{'='*78}")
    st = stats_for(all_trades, None)
    print(f"  n={st['n']} win_rate={st['win_rate']:.1f}% PF={st['pf']:.2f} "
          f"total_pnl={st['total_pnl']:+.1f}% avg/trade={st['avg_pnl']:+.4f}% additive_annualized={st['annualized_additive']:+.1f}%/yr")
    print(f"  exit reasons: {st['reasons']}")

    print(f"\n{'='*78}\nEARLY-REJECT variants (K minutes into hour, FRAC of causal cutoff)\n{'='*78}")
    for K in EARLY_REJECT_K_MINUTES:
        for frac in EARLY_REJECT_FRAC:
            st = stats_for(all_trades, (K, frac))
            print(f"  K={K:2d}min FRAC={frac:.2f}: n={st['n']} win_rate={st['win_rate']:.1f}% PF={st['pf']:.2f} "
                  f"total_pnl={st['total_pnl']:+.1f}% avg/trade={st['avg_pnl']:+.4f}% additive_ann={st['annualized_additive']:+.1f}%/yr  reasons={st['reasons']}")

    # precision check: among trades where the BEST-looking variant's early-reject rule fires,
    # what fraction were genuinely headed for VOL_UNCONFIRMED anyway (vs. would have confirmed)?
    print(f"\n{'='*78}\nPrecision check: for K=30min FRAC=0.75, what would each rejected trade's\n"
          f"baseline outcome have been?\n{'='*78}")
    K, frac = 30, 0.75
    would_confirm, would_unconfirm = 0, 0
    for t in all_trades:
        mask = (t['chk_minutes'] >= K) & (t['chk_ratio'] < t['cutoff_causal'] * frac)
        if mask.any():
            if t['confirmed']:
                would_confirm += 1
            else:
                would_unconfirm += 1
    total_rejected = would_confirm + would_unconfirm
    if total_rejected:
        print(f"  {total_rejected} trades rejected early. Of those, {would_unconfirm} "
              f"({100*would_unconfirm/total_rejected:.1f}%) were genuinely headed for VOL_UNCONFIRMED anyway; "
              f"{would_confirm} ({100*would_confirm/total_rejected:.1f}%) would actually have CONFIRMED "
              f"(false rejections under this rule).")


if __name__ == "__main__":
    main()
