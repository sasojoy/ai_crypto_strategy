"""
PAPER-TRADING MONITOR v4 -- EXPERIMENTAL, DEV-WINDOW BACKTESTED BUT NOT
HOLDOUT-VALIDATED. Same locked RSI(14) oversold/overbought momentum-
continuation + per-symbol volume-tercile entry as v1, and the same
"wait for the 1H bar to close" entry timing (no anticipatory entry like
v3, no pyramid add like v2) -- the ONLY difference is wider SL/TP
distances: 2.5xATR/5.0xATR instead of v1's locked 2.0xATR/4.0xATR, same
2:1 reward:risk ratio.

WHY: user observed the locked spec's win rate is low (~40%) and asked
about raising it. Two ideas were dev-window tested (RESEARCH_FINDINGS.md,
"v4 探索", 2026-09-11): moving the stop to breakeven once ahead by some
ATR amount FAILED badly (scripts/dev_momentum_v4_lock_profit.py -- 64.5%
of what would have been TP winners got diverted to a breakeven exit
instead, because this strategy's real winners routinely retrace/whipsaw
before their actual move). Widening the INITIAL stop distance instead
(scripts/dev_momentum_v4_wider_stop.py) showed a modest, consistent
improvement instead: SL/TP=2.5/5.0 scored PF 1.22->1.27, annualized
(linear) +82.3%->+97.6%/yr, quarters with PF>1 19/24->21/24, top-3-trade
concentration 2.4%->2.0% (healthier), all 5 symbols still net positive --
no metric got worse. Long/short split and by-symbol breakdown (same
script) reproduce the ALREADY-KNOWN long-strong/short-weak asymmetry
(RESEARCH_FINDINGS.md "多空分開的穩健性") proportionally rather than
introducing any NEW instability -- same conclusion pattern as v2's
pyramid add-on review.

Still only a SINGLE dev-window pass on ONE mechanism in isolation -- has
NOT been sent to the 2026+ holdout window (already spent once on the
locked no-this-mechanism spec; spending it again needs its own explicit
decision, not an automatic side effect of a good dev-window number).
Tracks its own independent P&L in state/momentum_v4_*, doesn't affect
v1/v2/v3's track records.

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
    BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

# The only mechanism change vs v1 -- see docstring. Same 2:1 reward:risk ratio,
# just wider in absolute ATR terms. Deliberately does NOT import v1's
# SL_ATR_MULT/TP_ATR_MULT (2.0/4.0) from dev_volume_confirm -- these override them.
SL_ATR_MULT = 2.5
TP_ATR_MULT = 5.0

MAX_CONCURRENT = 5  # kept as an absolute backstop even under the risk-budget cap below
RISK_BUDGET = 3.0  # correlation-aware portfolio-risk cap, same convention as v1/v2/v3
LOOKBACK_DAYS = 45   # enough bars for RSI/ATR/vol_ma20 warm-up plus a 7-day max hold

REFERENCE_CAPITAL_USD = 1000  # illustrative paper-trading base for the dollar figures shown in
                               # Telegram messages only -- P&L tracking itself stays entirely in
                               # % terms (cumulative_pnl_pct), this doesn't feed back into it


def position_size_usd(entry_price, sl_price):
    """Dollar risk/quantity/notional for BASE_RISK_PER_TRADE of REFERENCE_CAPITAL_USD at this
    entry/SL, mirroring the risk-based sizing leg_pnl_pct() already assumes. Display-only."""
    risk_usd = REFERENCE_CAPITAL_USD * BASE_RISK_PER_TRADE
    sl_dist = abs(entry_price - sl_price)
    qty = risk_usd / sl_dist if sl_dist > 0 else 0.0
    return risk_usd, qty, qty * entry_price


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v4_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v4_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """Same correlation-aware portfolio-risk calc as v1/v2/v3."""
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
    eq_pnl = (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0
    return {**pos, 'exit_price': exit_price, 'exit_time': str(exit_time), 'reason': reason, 'equity_pnl_pct': eq_pnl}


def main():
    thresholds = load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']
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
            msg = (f"📕 【模擬盤出場-v4】{closed['symbol']} {closed['direction'].upper()}\n"
                   f"原因: {closed['reason']}  損益: {closed['equity_pnl_pct']:+.2f}%（固定名目部位，2%風險/筆，SL/TP=2.5x/5.0xATR）\n"
                   f"進場: {fmt_taipei(pd.Timestamp(closed['entry_time']) + pd.Timedelta(hours=1))} @ {closed['entry_price']:.4f}\n"
                   f"出場: {fmt_taipei(closed['exit_time'])} @ {closed['exit_price']:.4f}\n"
                   f"累計模擬損益(v4): {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed']}筆已平倉）")
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

            open_legs = [(p['symbol'], p['direction']) for p in state['open_positions']]
            trial_risk = portfolio_risk(open_legs + [(s, direction)], corr)
            if len(state['open_positions']) >= MAX_CONCURRENT or trial_risk > RISK_BUDGET:
                msg = (f"⏭️ 【訊號略過(v4)，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】{s} "
                       f"{'oversold' if reversion_direction=='long' else 'overbought'} -> {direction.upper()} "
                       f"@ {fmt_taipei(ts)}  vol_ratio={df['vol_ratio'].iloc[i]:.2f}")
                print(msg)
                send_telegram_msg(msg)
                continue

            new_pos = {'symbol': s, 'direction': direction, 'entry_time': str(ts), 'entry_price': float(entry_price),
                       'sl_price': float(sl_price), 'tp_price': float(tp_price), 'vol_ratio': float(df['vol_ratio'].iloc[i])}
            state['open_positions'].append(new_pos)
            risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price)
            msg = (f"📗 【模擬盤進場-v4，放寬停損】{s} {direction.upper()}（{'超賣' if reversion_direction=='long' else '超買'}動能延續）\n"
                   f"時間: {fmt_taipei(ts + pd.Timedelta(hours=1))}  進場價: {entry_price:.4f}\n"
                   f"停損: {sl_price:.4f}  停利: {tp_price:.4f}（SL/TP=2.5x/5.0xATR，比v1寬）\n"
                   f"風險金額: ${risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {BASE_RISK_PER_TRADE*100:.0f}%）"
                   f"  建議部位: {qty:.4f}（名目 ${notional_usd:,.2f}）\n"
                   f"量能比: {df['vol_ratio'].iloc[i]:.2f}（門檻{cutoff:.2f}）\n"
                   f"目前同時持倉: {len(state['open_positions'])}  相關性風險: {trial_risk:.2f}/{RISK_BUDGET}")
            print(msg)
            send_telegram_msg(msg)

        if len(df):
            state['last_processed'][s] = str(df['timestamp'].iloc[-1])

    save_state(state)
    print(f"\nRun complete. Open positions: {len(state['open_positions'])}. "
          f"Cumulative paper P&L (v4): {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed']} closed trades.")


if __name__ == "__main__":
    main()
