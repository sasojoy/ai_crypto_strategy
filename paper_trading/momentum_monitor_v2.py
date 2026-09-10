"""
PAPER-TRADING MONITOR v2 -- EXPERIMENTAL, DEV-WINDOW BACKTESTED BUT NOT
HOLDOUT-VALIDATED. Builds on the git-committed v1 baseline
(momentum_monitor.py, commit "CHECKPOINT: Paper-trading monitors v1")
with two additions the user explicitly asked to try:

1. MINUTE-LEVEL SL/TP POLLING: v1 only checked stop/target hits once an
   hour (against 1H bar highs/lows), which cannot react faster than an
   hour to a fast intrabar move. v2 polls 1-minute bars for every open
   position on each run (recommended cadence: every 1-5 minutes) and
   checks SL/TP/timeout against that finer data -- much closer to what a
   real stop-loss/take-profit order resting on the exchange would do,
   though still not the same as a real conditional order (this script
   still has to be running to catch it; see DEPLOYMENT_RISK_ASSESSMENT.md
   on why a real deployment should use exchange-native stop orders, not
   rely on a polling script, for actual capital protection). This part
   is a pure engineering improvement, not a strategy assumption -- there
   is nothing to backtest here.

2. TREND-FOLLOWING PYRAMIDING (加倉) -- EXPERIMENTAL: once a position's
   unrealized move reaches +1x the ORIGINAL entry ATR in the favorable
   direction, add ONE more fixed-notional (2%-risk) unit at the current
   price, with its own SL/TP computed from the same original ATR. Both
   legs share the original position's overall 7-day max-hold deadline.
   At most one add per position (kept simple and bounded for this first
   experimental version). This mechanism does NOT exist in the locked,
   holdout-validated spec (dev_momentum_continuation.py /
   RESEARCH_FINDINGS.md "第二十三/二十四次測試"). UPDATE (2026-09-08,
   same session as this file's creation): it HAS since been backtested
   on the dev window (scripts/dev_momentum_pyramid_backtest.py: combined
   +133.97%/yr vs the no-pyramid baseline's +72.08%/yr, positive every
   year 2020-2025) with follow-up robustness checks (quarterly stability
   19/24 profitable quarters, long/short split, BTC-exclusion check) that
   came back reassuring -- no new instability was introduced beyond what
   the already-validated base spec already has (long side robust, short
   side weaker, same as the locked spec). What it has NOT had is a
   HOLDOUT run -- that would need a separate, explicit decision with the
   user before spending the one-shot holdout on a mechanism this new (see
   RESEARCH_FINDINGS.md's "實驗性延伸" section for the full writeup). Do
   not describe this as "never backtested" -- it has dev-window backtest
   support, just not out-of-sample holdout confirmation. Track its P&L
   SEPARATELY from the no-pyramid v1 baseline so the two can be
   compared honestly once enough paper history accumulates.

Entry-signal detection (RSI(14) oversold/overbought cross + volume
top-tercile) is UNCHANGED from v1 -- same rules, same thresholds.json
cutoff, same 5-concurrent-position-GROUP cap (pyramid adds don't count
against this cap; they scale an already-approved position, they aren't a
new independent signal -- but this means total open-leg risk exposure can
exceed 5x2%=10% once adds are counted; the run summary reports this
explicitly).

Still entirely read-only / no trade-execution API keys, still never
places a real order, still notifies via src/notifier.py's
send_telegram_msg. Uses its OWN state files (state/momentum_v2_*) so it
does not interfere with v1's independent track record.

Not part of the deployed app; safe to delete after use.
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

MAX_CONCURRENT_GROUPS = 5     # absolute backstop, kept even under the risk-budget cap below
RISK_BUDGET = 3.0             # correlation-aware portfolio-risk cap replacing the flat headcount
                               # cap for NEW signal groups (pyramid adds don't get a fresh accept/
                               # reject check -- they scale an already-approved group, matching v1's convention)
PYRAMID_TRIGGER_ATR = 1.0     # add a unit once unrealized move reaches +1x original ATR
MAX_ADDS_PER_POSITION = 1     # bounded, experimental -- raise only after reviewing paper results

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


LOOKBACK_DAYS = 45
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v2_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v2_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """Same correlation-aware portfolio-risk calc as v1's momentum_monitor.py.
    open_legs: list of (symbol, direction_str) tuples ('long'/'short')."""
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
            return json.load(f)
    return {'last_processed': {}, 'positions': [], 'cumulative_pnl_pct': 0.0, 'n_closed_legs': 0}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def append_trade_log(row):
    os.makedirs(os.path.dirname(TRADES_LOG_PATH), exist_ok=True)
    pd.DataFrame([row]).to_csv(TRADES_LOG_PATH, mode='a', header=not os.path.exists(TRADES_LOG_PATH), index=False)


def fetch_recent_1h(symbol):
    since = exchange.parse8601((pd.Timestamp.now('UTC') - pd.Timedelta(days=LOOKBACK_DAYS)).isoformat())
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    return drop_incomplete_last_1h_bar(df)


def drop_incomplete_last_1h_bar(df):
    """Same issue as momentum_monitor.py v1: fetch_ohlcv's last 1H row is
    often the still-forming candle (confirmed by inspection -- a bar
    fetched 13s into its hour showed ~65 volume vs ~5000-17000 for closed
    hours). RSI/ATR/volume-ratio and entry-trigger detection must only
    see fully-closed bars, or they react to numbers that are still
    changing. (Not applied to the 1-minute fetch used for SL/TP/pyramid
    checks -- there, using the still-forming bar's high/low-so-far is
    correct: it reflects whether price has genuinely already crossed a
    level, closer to how a real stop order would behave.)"""
    if df.empty:
        return df
    now = pd.Timestamp.now('UTC').tz_localize(None)
    closed = df['timestamp'] + pd.Timedelta(hours=1) <= now
    return df[closed].reset_index(drop=True)


def fetch_1m_since(symbol, since_ts):
    since = exchange.parse8601(pd.Timestamp(since_ts).isoformat())
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, '1m', since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1][0] + 1
    if not rows:
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)


def leg_pnl_pct(direction, entry_price, exit_price, sl_price):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * BASE_RISK_PER_TRADE * 100 if sl_dist_pct > 0 else 0.0


def process_position(pos, state):
    """Fetches 1-minute bars since this position's last check and walks
    them bar-by-bar: closes legs on SL/TP/timeout, triggers the pyramid
    add once, at the correct point in the sequence (not after the fact)."""
    since_ts = pos.get('last_checked', pos['entry_time'])
    df = fetch_1m_since(pos['symbol'], since_ts)
    if df.empty:
        return pos, True  # still open, nothing new to check

    max_hold_exit_time = pd.Timestamp(pos['entry_time']) + pd.Timedelta(hours=MAX_HOLD_BARS)

    for _, bar in df.iterrows():
        ts, high, low, close = bar['timestamp'], bar['high'], bar['low'], bar['close']

        # 1. original leg
        orig = pos['original']
        if not orig['closed']:
            hit = None
            if pos['direction'] == 'long':
                if low <= orig['sl_price']:
                    hit = (orig['sl_price'], 'SL')
                elif high >= orig['tp_price']:
                    hit = (orig['tp_price'], 'TP')
            else:
                if high >= orig['sl_price']:
                    hit = (orig['sl_price'], 'SL')
                elif low <= orig['tp_price']:
                    hit = (orig['tp_price'], 'TP')
            if hit is None and ts >= max_hold_exit_time:
                hit = (close, 'TIMEOUT')
            if hit is not None:
                exit_price, reason = hit
                orig['closed'] = True
                orig['exit_price'] = float(exit_price)
                orig['exit_time'] = str(ts)
                orig['reason'] = reason
                orig['equity_pnl_pct'] = leg_pnl_pct(pos['direction'], orig['entry_price'], exit_price, orig['sl_price'])
                _report_close(pos, 'original', orig, state)

        # 2. pyramid add leg (if it exists)
        add = pos.get('add')
        if add is not None and not add['closed']:
            hit = None
            if pos['direction'] == 'long':
                if low <= add['sl_price']:
                    hit = (add['sl_price'], 'SL')
                elif high >= add['tp_price']:
                    hit = (add['tp_price'], 'TP')
            else:
                if high >= add['sl_price']:
                    hit = (add['sl_price'], 'SL')
                elif low <= add['tp_price']:
                    hit = (add['tp_price'], 'TP')
            if hit is None and ts >= max_hold_exit_time:
                hit = (close, 'TIMEOUT')
            if hit is not None:
                exit_price, reason = hit
                add['closed'] = True
                add['exit_price'] = float(exit_price)
                add['exit_time'] = str(ts)
                add['reason'] = reason
                add['equity_pnl_pct'] = leg_pnl_pct(pos['direction'], add['entry_price'], exit_price, add['sl_price'])
                _report_close(pos, 'pyramid_add', add, state)

        # 3. pyramid-add trigger (only if original still open, no add yet, under the cap)
        if not orig['closed'] and pos.get('add') is None and pos['adds_used'] < MAX_ADDS_PER_POSITION:
            favorable_move = (high - orig['entry_price']) if pos['direction'] == 'long' else (orig['entry_price'] - low)
            if favorable_move >= PYRAMID_TRIGGER_ATR * orig['atr']:
                add_price = close
                if pos['direction'] == 'long':
                    add_sl = add_price - SL_ATR_MULT * orig['atr']
                    add_tp = add_price + TP_ATR_MULT * orig['atr']
                else:
                    add_sl = add_price + SL_ATR_MULT * orig['atr']
                    add_tp = add_price - TP_ATR_MULT * orig['atr']
                pos['add'] = {'entry_time': str(ts), 'entry_price': float(add_price),
                              'sl_price': float(add_sl), 'tp_price': float(add_tp), 'closed': False}
                pos['adds_used'] += 1
                add_risk_usd, add_qty, add_notional_usd = position_size_usd(add_price, add_sl)
                msg = (f"➕ 【實驗性加倉】{pos['symbol']} {pos['direction'].upper()}（順勢加碼，未經回測驗證）\n"
                       f"原始進場: {orig['entry_price']:.4f}  加倉價: {add_price:.4f}（獲利達+{PYRAMID_TRIGGER_ATR}xATR觸發）\n"
                       f"加倉停損: {add_sl:.4f}  加倉停利: {add_tp:.4f}\n"
                       f"加倉風險金額: ${add_risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {BASE_RISK_PER_TRADE*100:.0f}%）"
                       f"  建議部位: {add_qty:.4f}（名目 ${add_notional_usd:,.2f}）")
                print(msg)
                send_telegram_msg(msg)

    pos['last_checked'] = str(df['timestamp'].iloc[-1])
    both_closed = pos['original']['closed'] and (pos.get('add') is None or pos['add']['closed'])
    return pos, not both_closed


def _report_close(pos, leg_name, leg, state):
    state['cumulative_pnl_pct'] += leg['equity_pnl_pct']
    state['n_closed_legs'] += 1
    append_trade_log({'symbol': pos['symbol'], 'direction': pos['direction'], 'leg': leg_name, **leg})
    msg = (f"📕 【模擬盤出場-v2】{pos['symbol']} {pos['direction'].upper()} ({leg_name})\n"
           f"原因: {leg['reason']}  損益: {leg['equity_pnl_pct']:+.2f}%\n"
           f"進場: {fmt_taipei(leg['entry_time'])} @ {leg['entry_price']:.4f}\n"
           f"出場: {fmt_taipei(leg['exit_time'])} @ {leg['exit_price']:.4f}\n"
           f"累計模擬損益(v2): {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed_legs']}腿已平倉）")
    print(msg)
    send_telegram_msg(msg)


def main():
    thresholds = load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']  # per-symbol, 2026-09-08 fix -- see calibrate_momentum_threshold.py
    corr = thresholds['correlation_matrix']
    state = load_state()

    still_open = []
    for pos in state['positions']:
        pos, is_open = process_position(pos, state)
        if is_open:
            still_open.append(pos)
    state['positions'] = still_open

    n_open_groups = len(state['positions'])
    n_open_legs = sum((0 if p['original']['closed'] else 1) + (1 if p.get('add') and not p['add']['closed'] else 0)
                       for p in state['positions'])

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
            print(f"{s}: first run, baseline set -- will act on triggers from the next run onward.")
            continue

        cutoff = cutoffs[s]
        for i, reversion_direction in find_triggers(df):
            ts = df['timestamp'].iloc[i]
            if ts <= pd.Timestamp(last_ts):
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

            open_legs = [(p['symbol'], p['direction']) for p in state['positions']]
            trial_risk = portfolio_risk(open_legs + [(s, direction)], corr)
            if n_open_groups >= MAX_CONCURRENT_GROUPS or trial_risk > RISK_BUDGET:
                msg = (f"⏭️ 【訊號略過(v2)，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】"
                       f"{s} @ {fmt_taipei(ts)} vol_ratio={df['vol_ratio'].iloc[i]:.2f}")
                print(msg)
                send_telegram_msg(msg)
                continue

            new_pos = {
                'symbol': s, 'direction': direction, 'entry_time': str(ts), 'adds_used': 0, 'add': None,
                'last_checked': str(ts),
                'original': {'entry_time': str(ts), 'entry_price': float(entry_price), 'atr': float(atr),
                             'sl_price': float(sl_price), 'tp_price': float(tp_price), 'closed': False},
            }
            state['positions'].append(new_pos)
            n_open_groups += 1
            risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price)
            msg = (f"📗 【模擬盤進場-v2】{s} {direction.upper()}（{'超賣' if reversion_direction=='long' else '超買'}動能延續，分鐘級防護+實驗性加倉）\n"
                   f"時間: {fmt_taipei(ts)}  進場價: {entry_price:.4f}\n"
                   f"停損: {sl_price:.4f}  停利: {tp_price:.4f}\n"
                   f"風險金額: ${risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {BASE_RISK_PER_TRADE*100:.0f}%）"
                   f"  建議部位: {qty:.4f}（名目 ${notional_usd:,.2f}）\n"
                   f"目前同時持倉組數: {n_open_groups}  相關性風險: {trial_risk:.2f}/{RISK_BUDGET}")
            print(msg)
            send_telegram_msg(msg)

        if len(df):
            state['last_processed'][s] = str(df['timestamp'].iloc[-1])

    save_state(state)
    print(f"\nRun complete. Open position groups: {n_open_groups}. Open legs (risk units): {n_open_legs} "
          f"(={n_open_legs * BASE_RISK_PER_TRADE * 100:.0f}% of reference capital at risk right now). "
          f"Cumulative paper P&L (v2): {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed_legs']} closed legs.")


if __name__ == "__main__":
    main()
