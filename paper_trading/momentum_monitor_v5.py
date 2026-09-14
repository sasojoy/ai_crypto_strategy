"""
PAPER-TRADING MONITOR v5 -- EXPERIMENTAL, DEV-WINDOW BACKTESTED BUT NOT
HOLDOUT-VALIDATED. Same locked RSI(14) oversold/overbought momentum-
continuation entry/exit rules and timing as v1 (SL=2.0xATR/TP=4.0xATR,
wait for the bar to close, no pyramid, no anticipatory entry) -- the ONLY
difference is per-trade RISK SIZING: instead of a flat 2% of reference
capital on every trade that clears the top-tercile volume filter, risk is
scaled with how far above the tercile cutoff that trade's volume ratio
sits, so a barely-qualifying trade risks less and an extreme-volume trade
risks more.

WHY: this research line already found (dev_momentum_continuation.py's
Spearman test) that volume ratio at the trigger positively correlates
with trade P&L for this setup -- "how much conviction does the volume
give this specific trade" was already a validated signal, just never
acted on beyond a binary pass/fail gate. Dev-window test
(scripts/dev_momentum_vol_scaled_risk.py, RESEARCH_FINDINGS.md "風險%與量能比
連動"): scaling risk 1%-3% (average ~2%, so this reallocates risk rather
than raising it) by each trade's percentile rank of vol_ratio within its
symbol's top-tercile-qualifying population gave PF 1.22->1.24, annualized
(linear) +82.3%->+89.9%/yr, quarters PF>1 19/24->20/24 -- a modest,
genuine improvement of the same order as v4's wider-stop finding, at the
cost of slightly higher top-3-trade concentration (2.4%->3.3%, still
healthy in absolute terms) since the strongest signals now carry more
weight. Win rate is UNCHANGED by design (40.6%->40.6%) -- this mechanism
doesn't touch which trades win or lose, only how much is risked on each.

LIVE APPROXIMATION OF "PERCENTILE RANK": the backtest ranked each trade
against its OWN dev-window's full trigger population, which a live
monitor can't do (it doesn't have a future population to rank against,
the same reason the top-tercile CUTOFF itself has to be pre-calibrated
rather than computed live -- see calibrate_momentum_threshold.py). This
monitor instead linearly interpolates a live trade's vol_ratio between two
FIXED, pre-calibrated anchors from thresholds.json: the existing per-symbol
tercile cutoff (-> risk 1%) and a newly-calibrated
`vol_ratio_p99_within_tercile_by_symbol` (the 99th percentile of vol_ratio
among that symbol's OWN historical top-tercile-qualifying triggers, not
the raw max, to avoid one freak outlier pinning the whole scale -> risk
3%), clamping outside that range. Re-run calibrate_momentum_threshold.py
periodically to keep both anchors current, same as the cutoff itself.

Still only a SINGLE dev-window pass on ONE mechanism in isolation -- has
NOT been sent to the 2026+ holdout window, and has NOT been tested
combined with v4's wider-stop mechanism (that would be a new, separate,
untested combination -- see v3's docstring for why this research line
tests one mechanism at a time). Tracks its own independent P&L in
state/momentum_v5_*, doesn't affect v1/v2/v3/v4's track records.

Still entirely read-only / no trade-execution API keys, never places a
real order, notifies via src/notifier.py's send_telegram_msg.
"""
import os
import sys
import json
import itertools

import ccxt
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from dev_volume_confirm import (
    SYMBOLS, compute_atr, compute_rsi, find_triggers,
    SL_ATR_MULT, TP_ATR_MULT, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

MIN_RISK = 0.01   # risk fraction at (or below) the tercile cutoff
MAX_RISK = 0.03   # risk fraction at (or above) the p99-within-tercile anchor

MAX_CONCURRENT = 5  # kept as an absolute backstop even under the risk-budget cap below
RISK_BUDGET = 3.0  # correlation-aware portfolio-risk cap, same convention as v1/v2/v3/v4
LOOKBACK_DAYS = 45   # enough bars for RSI/ATR/vol_ma20 warm-up plus a 7-day max hold

REFERENCE_CAPITAL_USD = 1000  # illustrative paper-trading base for the dollar figures shown in
                               # Telegram messages only -- P&L tracking itself stays entirely in
                               # % terms (cumulative_pnl_pct), this doesn't feed back into it


def vol_scaled_risk(vol_ratio, cutoff, p99):
    """Linearly maps vol_ratio from [cutoff -> MIN_RISK] to [p99 -> MAX_RISK],
    clamped outside that range. Live, causal approximation of the backtest's
    population-relative percentile rank -- see module docstring."""
    if p99 <= cutoff:
        return (MIN_RISK + MAX_RISK) / 2  # degenerate calibration data; fall back to the midpoint
    rank = (vol_ratio - cutoff) / (p99 - cutoff)
    rank = max(0.0, min(1.0, rank))
    return MIN_RISK + rank * (MAX_RISK - MIN_RISK)


def position_size_usd(entry_price, sl_price, risk_frac):
    """Dollar risk/quantity/notional for this trade's risk_frac of REFERENCE_CAPITAL_USD
    at this entry/SL. Display-only."""
    risk_usd = REFERENCE_CAPITAL_USD * risk_frac
    sl_dist = abs(entry_price - sl_price)
    qty = risk_usd / sl_dist if sl_dist > 0 else 0.0
    return risk_usd, qty, qty * entry_price


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v5_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v5_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """Same correlation-aware portfolio-risk calc as v1/v2/v3/v4."""
    if not open_legs:
        return 0.0
    signed = [(sym, 1 if d == 'long' else -1) for sym, d in open_legs]
    variance = 0.0
    for (s1, e1), (s2, e2) in itertools.product(signed, repeat=2):
        variance += e1 * e2 * corr[s1][s2]
    return np.sqrt(max(variance, 0.0))


def load_thresholds():
    with open(THRESHOLDS_PATH) as f:
        return json.load(f)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state = json.load(f)
    else:
        state = {'last_processed': {}, 'open_positions': [], 'cumulative_pnl_pct': 0.0, 'n_closed': 0}
    return state


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def append_trade_log(row):
    os.makedirs(os.path.dirname(TRADES_LOG_PATH), exist_ok=True)
    df = pd.DataFrame([row])
    header = not os.path.exists(TRADES_LOG_PATH)
    df.to_csv(TRADES_LOG_PATH, mode='a', header=header, index=False)


def fetch_recent_1h(symbol):
    since = exchange.parse8601((pd.Timestamp.now('UTC') - pd.Timedelta(days=LOOKBACK_DAYS)).isoformat())
    all_ohlcv = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
        if not batch:
            break
        all_ohlcv.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    return drop_incomplete_last_bar(df)


def drop_incomplete_last_bar(df):
    """Same as v1: only ever compute RSI/ATR/volume-ratio or check a trigger
    against fully CLOSED 1H bars."""
    if df.empty:
        return df
    now = pd.Timestamp.now('UTC').tz_localize(None)
    closed = df['timestamp'] + pd.Timedelta(hours=1) <= now
    return df[closed].reset_index(drop=True)


def update_open_position(pos, df):
    """Checks whether SL/TP/timeout has been reached since entry, using
    bars available so far. Returns None if still open, else a close dict."""
    ts = df['timestamp']
    entry_mask = ts == pd.Timestamp(pos['entry_time'])
    if not entry_mask.any():
        return None
    entry_idx = entry_mask.idxmax()
    close, high, low = df['close'].values, df['high'].values, df['low'].values
    max_hold_exit_time = pd.Timestamp(pos['entry_time']) + pd.Timedelta(hours=MAX_HOLD_BARS)

    for j in range(entry_idx + 1, len(df)):
        if pos['direction'] == 'long':
            if low[j] <= pos['sl_price']:
                return _close(pos, pos['sl_price'], 'SL', df['timestamp'].iloc[j])
            if high[j] >= pos['tp_price']:
                return _close(pos, pos['tp_price'], 'TP', df['timestamp'].iloc[j])
        else:
            if high[j] >= pos['sl_price']:
                return _close(pos, pos['sl_price'], 'SL', df['timestamp'].iloc[j])
            if low[j] <= pos['tp_price']:
                return _close(pos, pos['tp_price'], 'TP', df['timestamp'].iloc[j])
        if df['timestamp'].iloc[j] >= max_hold_exit_time:
            return _close(pos, close[j], 'TIMEOUT', df['timestamp'].iloc[j])
    return None


def _close(pos, exit_price, reason, exit_time):
    entry_price = pos['entry_price']
    if pos['direction'] == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - pos['sl_price']) / entry_price
    # risk_frac is the value fixed AT ENTRY (based on that trade's vol_ratio) -- position
    # size was already set then, moving the goalposts on exit would be wrong.
    eq_pnl = (pnl / sl_dist_pct) * pos['risk_frac'] * 100 if sl_dist_pct > 0 else 0.0
    return {**pos, 'exit_price': exit_price, 'exit_time': str(exit_time), 'reason': reason, 'equity_pnl_pct': eq_pnl}


def main():
    thresholds = load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']
    p99s = thresholds['vol_ratio_p99_within_tercile_by_symbol']
    corr = thresholds['correlation_matrix']
    state = load_state()

    still_open = []
    for pos in state['open_positions']:
        df = fetch_recent_1h(pos['symbol'])
        closed = update_open_position(pos, df)
        if closed:
            state['cumulative_pnl_pct'] += closed['equity_pnl_pct']
            state['n_closed'] += 1
            append_trade_log(closed)
            msg = (f"📕 【模擬盤出場-v5】{closed['symbol']} {closed['direction'].upper()}\n"
                   f"原因: {closed['reason']}  損益: {closed['equity_pnl_pct']:+.2f}%"
                   f"（本筆風險{closed['risk_frac']*100:.2f}%，依量能比動態調整）\n"
                   f"進場: {fmt_taipei(pd.Timestamp(closed['entry_time']) + pd.Timedelta(hours=1))} @ {closed['entry_price']:.4f}\n"
                   f"出場: {fmt_taipei(closed['exit_time'])} @ {closed['exit_price']:.4f}\n"
                   f"累計模擬損益(v5): {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed']}筆已平倉）")
            print(msg)
            send_telegram_msg(msg)
        else:
            still_open.append(pos)
    state['open_positions'] = still_open

    for s in SYMBOLS:
        df = fetch_recent_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma20']

        last_ts = state['last_processed'].get(s)
        if last_ts is None:
            if len(df):
                state['last_processed'][s] = str(df['timestamp'].iloc[-1])
            print(f"{s}: first run, baseline set at {df['timestamp'].iloc[-1] if len(df) else 'n/a'} -- "
                  f"will act on triggers from the next run onward.")
            continue

        cutoff = cutoffs[s]
        p99 = p99s[s]
        triggers = find_triggers(df)
        for i, reversion_direction in triggers:
            ts = df['timestamp'].iloc[i]
            if last_ts is not None and ts <= pd.Timestamp(last_ts):
                continue
            if np.isnan(df['vol_ratio'].iloc[i]) or df['vol_ratio'].iloc[i] < cutoff:
                continue
            direction = flip(reversion_direction)
            entry_price = df['close'].iloc[i]
            atr = df['atr'].iloc[i]
            if np.isnan(atr) or atr <= 0:
                continue
            sl_price = entry_price - SL_ATR_MULT * atr if direction == 'long' else entry_price + SL_ATR_MULT * atr
            tp_price = entry_price + TP_ATR_MULT * atr if direction == 'long' else entry_price - TP_ATR_MULT * atr
            risk_frac = vol_scaled_risk(df['vol_ratio'].iloc[i], cutoff, p99)

            open_legs = [(p['symbol'], p['direction']) for p in state['open_positions']]
            trial_risk = portfolio_risk(open_legs + [(s, direction)], corr)
            if len(state['open_positions']) >= MAX_CONCURRENT or trial_risk > RISK_BUDGET:
                msg = (f"⏭️ 【訊號略過(v5)，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】{s} "
                       f"{'oversold' if reversion_direction=='long' else 'overbought'} -> {direction.upper()} "
                       f"@ {fmt_taipei(ts)}  vol_ratio={df['vol_ratio'].iloc[i]:.2f}")
                print(msg)
                send_telegram_msg(msg)
                continue

            new_pos = {'symbol': s, 'direction': direction, 'entry_time': str(ts), 'entry_price': float(entry_price),
                       'sl_price': float(sl_price), 'tp_price': float(tp_price),
                       'vol_ratio': float(df['vol_ratio'].iloc[i]), 'risk_frac': float(risk_frac)}
            state['open_positions'].append(new_pos)
            risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price, risk_frac)
            msg = (f"📗 【模擬盤進場-v5，量能連動風險】{s} {direction.upper()}（{'超賣' if reversion_direction=='long' else '超買'}動能延續）\n"
                   f"時間: {fmt_taipei(ts + pd.Timedelta(hours=1))}  進場價: {entry_price:.4f}\n"
                   f"停損: {sl_price:.4f}  停利: {tp_price:.4f}\n"
                   f"風險金額: ${risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {risk_frac*100:.2f}%，依量能比動態調整於1~3%）"
                   f"  建議部位: {qty:.4f}（名目 ${notional_usd:,.2f}）\n"
                   f"量能比: {df['vol_ratio'].iloc[i]:.2f}（門檻{cutoff:.2f}，強訊號基準{p99:.2f}）\n"
                   f"目前同時持倉: {len(state['open_positions'])}  相關性風險: {trial_risk:.2f}/{RISK_BUDGET}")
            print(msg)
            send_telegram_msg(msg)

        if len(df):
            state['last_processed'][s] = str(df['timestamp'].iloc[-1])

    save_state(state)
    print(f"\nRun complete. Open positions: {len(state['open_positions'])}. "
          f"Cumulative paper P&L (v5): {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed']} closed trades.")


if __name__ == "__main__":
    main()
