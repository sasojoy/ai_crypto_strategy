"""
PAPER-TRADING MONITOR for the locked RSI(14) momentum-continuation +
volume-tercile strategy (RESEARCH_FINDINGS.md "第二十三次測試", validated
in "第二十四次測試"). Read-only: fetches public market data via ccxt (no
API key / trade permission needed), simulates trades on paper using the
exact locked rules, and sends a Telegram notification on every simulated
entry/exit so a human can decide whether to replicate it with real
capital. It never places a real order.

Run this periodically (e.g. once an hour via Windows Task Scheduler --
see paper_trading/README.md). Each run:
  1. Loads state (open paper positions, last-processed bar per symbol,
     cumulative fixed-notional paper P&L) from state/momentum_state.json.
  2. Fetches recent 1H OHLCV for each symbol.
  3. Updates any open paper positions (checks whether SL/TP was hit, or
     the 7-day max-hold window has elapsed, using the same rules as
     dev_momentum_continuation.py / holdout_momentum_validation.py).
  4. Detects new RSI(14) oversold/overbought crosses with volume >= the
     calibrated top-tercile cutoff (paper_trading/thresholds.json,
     produced by calibrate_momentum_threshold.py) and opens a new paper
     position if fewer than MAX_CONCURRENT positions are already open
     (the concurrency cap recommended in DEPLOYMENT_RISK_ASSESSMENT.md
     as a risk control, not a return-optimizer).
  5. Sizing uses FIXED-NOTIONAL 2%-of-reference-capital risk per trade
     (not compounding), per the correction in
     scripts/dev_momentum_fixed_notional.py -- the original backtest's
     sequential-compounding number was shown to be an unreliable estimate
     of what a real account would realize.
  6. Saves state and appends any closed trades to
     state/momentum_trades_log.csv.

Sends Telegram messages via src/notifier.py's send_telegram_msg (reuses
the existing project notification infra -- configure TELEGRAM_BOT_TOKEN /
TELEGRAM_CHAT_ID in a .env file at the project root; without them this
still runs and logs to the console/CSV, it just won't message you).

Not part of the deployed app (v600.46) -- this is a separate, standalone
paper-trading system for the two research-validated candidates, does not
touch the live trading pipeline in src/market.py.
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
    SL_ATR_MULT, TP_ATR_MULT, BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_continuation import flip
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

MAX_CONCURRENT = 5  # kept as an absolute backstop even under the risk-budget cap below
RISK_BUDGET = 3.0  # correlation-aware portfolio-risk cap, replaces the flat headcount cap
                    # (see DEPLOYMENT_RISK_ASSESSMENT.md / scripts/dev_momentum_portfolio_risk.py:
                    # ~97% of the flat cap's average return, ~20-24% lower max drawdown on the dev window)
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
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """open_legs: list of (symbol, direction_str) tuples ('long'/'short')
    for CURRENTLY open positions plus the candidate being evaluated.
    Portfolio risk = sqrt(sum_i sum_j e_i e_j corr(sym_i, sym_j)) where
    e=+1 long/-1 short -- same-direction correlated legs cost MORE than
    one count each, opposite-direction correlated legs (partial hedges)
    cost less."""
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
    """fetch_ohlcv's last row is often the currently-forming, not-yet-
    closed candle (its 'close' isn't final and its volume is a fraction
    of a normal bar's -- confirmed by inspection: a bar fetched 13 seconds
    into its hour showed ~65 volume vs ~5000-17000 for closed hours).
    Computing RSI/ATR/volume-ratio or detecting a trigger on it would use
    numbers that are still changing. Drop any row whose 1H period hasn't
    fully elapsed yet."""
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
        return None  # entry bar has scrolled out of the fetch window; leave it, next run's wider context isn't needed since exit checks only need bars AFTER entry
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
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']  # per-symbol, 2026-09-08 fix -- see calibrate_momentum_threshold.py
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
            msg = (f"📕 【模擬盤出場】{closed['symbol']} {closed['direction'].upper()}\n"
                   f"原因: {closed['reason']}  損益: {closed['equity_pnl_pct']:+.2f}%（固定名目部位，2%風險/筆）\n"
                   f"進場: {fmt_taipei(pd.Timestamp(closed['entry_time']) + pd.Timedelta(hours=1))} @ {closed['entry_price']:.4f}\n"
                   f"出場: {fmt_taipei(closed['exit_time'])} @ {closed['exit_price']:.4f}\n"
                   f"累計模擬損益: {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed']}筆已平倉）")
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
            # First run for this symbol: establish a baseline instead of treating the
            # whole LOOKBACK_DAYS backlog as fresh signals (which would immediately
            # fill the concurrency cap with stale, already-expired "trades").
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
                msg = (f"⏭️ 【訊號略過，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】{s} "
                       f"{'oversold' if reversion_direction=='long' else 'overbought'} -> {direction.upper()} "
                       f"@ {fmt_taipei(ts)}  vol_ratio={df['vol_ratio'].iloc[i]:.2f}")
                print(msg)
                send_telegram_msg(msg)
                continue

            new_pos = {'symbol': s, 'direction': direction, 'entry_time': str(ts), 'entry_price': float(entry_price),
                       'sl_price': float(sl_price), 'tp_price': float(tp_price), 'vol_ratio': float(df['vol_ratio'].iloc[i])}
            state['open_positions'].append(new_pos)
            risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price)
            # entry_time is stored as ts (the trigger bar's OPEN timestamp) because that's the key
            # update_open_position() matches against df['timestamp'] to find where to start scanning
            # for SL/TP -- doesn't cause a look-ahead bug here since the scan explicitly starts at
            # entry_idx+1 (the NEXT bar), but it does mean the stored/displayed time is an hour
            # before entry_price (that bar's CLOSE) was actually known. Display the real moment.
            msg = (f"📗 【模擬盤進場】{s} {direction.upper()}（{'超賣' if reversion_direction=='long' else '超買'}動能延續）\n"
                   f"時間: {fmt_taipei(ts + pd.Timedelta(hours=1))}  進場價: {entry_price:.4f}\n"
                   f"停損: {sl_price:.4f}  停利: {tp_price:.4f}\n"
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
          f"Cumulative paper P&L: {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed']} closed trades.")


if __name__ == "__main__":
    main()
