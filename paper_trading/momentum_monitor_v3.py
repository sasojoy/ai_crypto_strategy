"""
PAPER-TRADING MONITOR v3. Builds on the same locked RSI(14)+volume-tercile
entry definition as v1/v2, but replaces "wait for the 1H bar to close" with a
real-time ANTICIPATORY ENTRY mechanism: investigated and backtested across
six iterations (two look-ahead bugs found and fixed, then a volume-cutoff
calibration mismatch found and fixed on a user-requested re-audit) on the
full 2020-2025 dev window using complete 1-minute OHLCV for all 5 symbols.
See the "提早進場調查" artifact report from that session for the full
methodology and results.

HOLDOUT-VALIDATED (2026-09-17, `scripts/holdout_v3_anticipatory_entry.py`,
this project's 3rd use of the one-shot holdout window): on the same 2026
holdout window, a classic v1-style closed-bar baseline scored n=213,
win_rate 37.6%, PF 1.05 -- this anticipatory mechanism scored n=741 (3.5x
more entries, matching the dev-window ratio), win_rate 47.5%, PF 1.39, all
5 symbols net positive (vs. the baseline's ETH/AVAX/SOL net negative). Unlike
the dev-window finding (uplift mostly from more signals, not much per-trade
edge), the holdout uplift came from BOTH more signals AND a genuinely
better per-trade win rate/PF -- a stronger out-of-sample replication than
the dev-window number alone suggested.

A separate idea -- continuously re-projecting volume after entry and
rejecting early instead of always waiting for the hour to close
(`scripts/dev_momentum_v3_early_reject.py`, 2026-09-17) -- was tested and
found dev-window neutral (the mechanism accurately predicts ~98.5% of
eventual VOL_UNCONFIRMED outcomes before hour-close, but VOL_UNCONFIRMED
exits already average a small profit, not a loss, so closing them earlier
doesn't add edge). Not implemented; this file's confirmation checkpoint is
unchanged.

THE MECHANISM:
1. At the start of each still-forming 1H bar, using the LAST CLOSED bar's
   Wilder RSI state (avg_gain/avg_loss) and close, solve for the two exact
   closing prices that would make THIS hour's RSI cross 30 (oversold ->
   short entry) or 70 (overbought -> long entry) -- this is a deterministic
   function of already-known, closed-bar data, no lookahead.
2. Poll 1-minute bars for the still-forming hour (this script runs every
   5 minutes). The instant price touches one of those threshold prices,
   check a REAL-TIME PROJECTED volume ratio: cumulative volume so far this
   hour, scaled to a full hour (cum_vol * 60/minutes_elapsed), divided by
   the trailing 20-bar volume MA of the 20 CLOSED bars before this hour
   (excluding this hour's own volume, since it hasn't closed -- that MA
   must NOT include the current bar, unlike v1/v2's post-close evaluation).
   If that projected ratio clears the per-symbol CAUSAL cutoff
   (thresholds.json's vol_ratio_top_tercile_cutoff_causal_by_symbol --
   calibrated against the SAME excluding-current-bar MA convention; the
   already-existing non-causal cutoff was calibrated against an including-
   current-bar MA and is NOT the same yardstick, see calibrate_momentum
   _threshold.py's 2026-09-09 addition note), enter immediately at the
   threshold price.
3. VOLUME-CONFIRMATION CHECKPOINT: once the entry hour actually closes (a
   real, already-elapsed fact by the time it happens, not lookahead), this
   script checks the REAL final volume ratio the same way v1/v2 already do
   (including-current-bar MA, against the EXISTING non-causal cutoff -- the
   correct apples-to-apples check for "would this have been a real signal
   under the locked spec"). If it does NOT clear the bar, the position is
   closed immediately at the current price (reason VOL_UNCONFIRMED) instead
   of pretending the trade never happened -- unlike v1/v2, entries here are
   provisional until this checkpoint. Backtested VOL_UNCONFIRMED rate: ~49%
   of entries, but those close out at a small average PROFIT (+0.14%), not
   a loss -- the mechanism's real cost is mostly opportunity/complexity, not
   capital.
4. If confirmed, the position continues under the same SL=2xATR/TP=4xATR/
   7-day-max-hold rules as v1/v2, still polled every run via 1-minute bars
   for the whole hold (finer than the dev-window backtest's post-entry-hour
   1H-bar convention, which was a backtest-only computational shortcut, not
   a claim that 1H is more correct).

Backtested results (dev window, 2020-2025, after both correction rounds):
n=6,139 legs, win_rate 48.7%, PF 1.51, +387.23%/yr (vs v1's dev-window
baseline of +79.79%/yr) -- profitable in 23/24 quarters, all 5 symbols net
positive, both directions net positive. The annualized uplift comes mostly
from ~3.5x more signals firing (earlier + a looser real-time volume gate),
not from a wildly better per-trade edge (+0.274% -> +0.379% average leg).

Deliberately does NOT include v2's pyramid add-on -- combining two
unvalidated experimental mechanisms at once would make it impossible to
attribute results to either one. Tracks its own independent P&L in
state/momentum_v3_*.

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
    SYMBOLS, compute_atr, SL_ATR_MULT, TP_ATR_MULT,
    BASE_RISK_PER_TRADE, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

MAX_CONCURRENT_GROUPS = 5
RISK_BUDGET = 3.0
COOLDOWN_HOURS = 8
ALPHA = 1 / 14  # Wilder RSI(14) smoothing factor

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
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v3_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v3_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """Same correlation-aware portfolio-risk calc as v1/v2."""
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
    return {'last_entry_time': {}, 'positions': [], 'cumulative_pnl_pct': 0.0, 'n_closed': 0}


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
    """Same as v1/v2: only ever compute RSI/ATR/volume-ratio against fully
    CLOSED 1H bars. The still-forming hour is handled separately below via
    1-minute bars, which is the whole point of v3."""
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


def compute_rsi_state(close):
    """Same Wilder RSI as compute_rsi(), but also returns the avg_gain/
    avg_loss state series needed to solve for the next bar's threshold
    price."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=ALPHA, adjust=False).mean()
    avg_loss = loss.ewm(alpha=ALPHA, adjust=False).mean()
    return avg_gain, avg_loss


def threshold_price(prev_close, avg_gain_prev, avg_loss_prev, target_rsi):
    """Closing price that would make RSI(14) equal target_rsi exactly,
    given the PRIOR closed bar's Wilder state. target_rsi=30 -> oversold
    (short-entry threshold, price below prev_close). target_rsi=70 ->
    overbought (long-entry threshold, price above prev_close)."""
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


def detect_entry(symbol, df_closed, causal_cutoff):
    """df_closed: recent fully-closed 1H bars for this symbol (already has
    'rsi'/'atr'/'avg_gain'/'avg_loss' columns). Returns a candidate dict if
    an anticipatory entry fires in the still-forming hour, else None."""
    if len(df_closed) < 21:  # need 20 bars for vol MA + 1 for RSI state
        return None
    last_close = df_closed['close'].iloc[-1]
    ag_prev = df_closed['avg_gain'].iloc[-1]
    al_prev = df_closed['avg_loss'].iloc[-1]
    atr_sizing = df_closed['atr'].iloc[-1]
    vol_ma20_causal = df_closed['volume'].iloc[-20:].mean()
    if np.isnan(ag_prev) or np.isnan(al_prev) or np.isnan(atr_sizing) or atr_sizing <= 0 or vol_ma20_causal <= 0:
        return None

    thr_long = threshold_price(last_close, ag_prev, al_prev, 70)
    thr_short = threshold_price(last_close, ag_prev, al_prev, 30)

    hour_start = df_closed['timestamp'].iloc[-1] + pd.Timedelta(hours=1)
    dfm = fetch_1m_since(symbol, hour_start)
    if dfm.empty:
        return None

    cum_vol = 0.0
    for i, bar in enumerate(dfm.itertuples(), start=1):
        cum_vol += bar.volume
        projected_ratio = (cum_vol * (60.0 / i)) / vol_ma20_causal
        direction, entry_price = None, None
        if bar.high >= thr_long:
            direction, entry_price = 'long', thr_long
        elif bar.low <= thr_short:
            direction, entry_price = 'short', thr_short
        if direction is not None and projected_ratio >= causal_cutoff:
            return {
                'direction': direction, 'entry_price': float(entry_price),
                'entry_time': bar.timestamp, 'atr': float(atr_sizing),
                'hour_start': hour_start, 'hour_end': hour_start + pd.Timedelta(hours=1),
                'minutes_into_hour': i, 'projected_vol_ratio': float(projected_ratio),
            }
    return None


def process_position(pos, state, cutoffs):
    """Walks 1-minute bars since last check: SL/TP first, then (once past
    the entry-hour boundary) the volume-confirmation checkpoint, then keeps
    polling minute-by-minute for the rest of the hold if confirmed."""
    since_ts = pos.get('last_checked', pos['entry_time'])
    df = fetch_1m_since(pos['symbol'], since_ts)
    if df.empty:
        return pos, True

    entry_price, sl_price, tp_price = pos['entry_price'], pos['sl_price'], pos['tp_price']
    max_hold_exit_time = pd.Timestamp(pos['entry_time']) + pd.Timedelta(hours=MAX_HOLD_BARS)
    hour_end = pd.Timestamp(pos['hour_end'])
    confirmation_attempted_this_run = False

    for bar in df.itertuples():
        ts, high, low, close = bar.timestamp, bar.high, bar.low, bar.close

        hit = None
        if pos['direction'] == 'long':
            if low <= sl_price:
                hit = (sl_price, 'SL')
            elif high >= tp_price:
                hit = (tp_price, 'TP')
        else:
            if high >= sl_price:
                hit = (sl_price, 'SL')
            elif low <= tp_price:
                hit = (tp_price, 'TP')
        if hit is None and ts >= max_hold_exit_time:
            hit = (close, 'TIMEOUT')
        if hit is not None:
            exit_price, reason = hit
            _close_position(pos, exit_price, ts, reason, state)
            return pos, False

        if not pos['vol_confirmed'] and ts >= hour_end and not confirmation_attempted_this_run:
            confirmation_attempted_this_run = True
            confirmed = _check_volume_confirmed(pos, cutoffs)
            if confirmed is None:
                pass  # the closing 1H bar for entry hour isn't published yet -- retry next run
            elif not confirmed:
                _close_position(pos, close, ts, 'VOL_UNCONFIRMED', state)
                return pos, False
            else:
                pos['vol_confirmed'] = True

    pos['last_checked'] = str(df['timestamp'].iloc[-1])
    return pos, True


def _check_volume_confirmed(pos, cutoffs):
    """Fetches recent closed 1H bars and checks whether the entry hour's
    OWN final (including-current-bar) volume ratio clears the existing
    non-causal cutoff -- the same convention v1/v2 already use, the correct
    apples-to-apples check now that the hour has actually closed. Returns
    True/False, or None if that hour's closed bar isn't in the exchange's
    response yet (rare timing edge case -- retry next run)."""
    df = fetch_recent_1h(pos['symbol'])
    if df.empty:
        return None
    match = df[df['timestamp'] == pd.Timestamp(pos['hour_start'])]
    if match.empty:
        return None
    vol_ma20 = df['volume'].rolling(20).mean()
    row_idx = match.index[0]
    if row_idx < 19 or np.isnan(vol_ma20.iloc[row_idx]) or vol_ma20.iloc[row_idx] <= 0:
        return None
    vol_ratio_final = match['volume'].iloc[0] / vol_ma20.iloc[row_idx]
    return bool(vol_ratio_final >= cutoffs[pos['symbol']])


def _close_position(pos, exit_price, exit_time, reason, state):
    pnl = leg_pnl_pct(pos['direction'], pos['entry_price'], exit_price, pos['sl_price'])
    state['cumulative_pnl_pct'] += pnl
    state['n_closed'] += 1
    log_row = {**pos, 'exit_price': float(exit_price), 'exit_time': str(exit_time),
               'reason': reason, 'equity_pnl_pct': pnl}
    append_trade_log(log_row)
    msg = (f"📕 【模擬盤出場-v3】{pos['symbol']} {pos['direction'].upper()}\n"
           f"原因: {reason}  損益: {pnl:+.2f}%\n"
           f"進場: {fmt_taipei(pos['entry_time'])} @ {pos['entry_price']:.4f}\n"
           f"出場: {fmt_taipei(exit_time)} @ {exit_price:.4f}\n"
           f"累計模擬損益(v3): {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed']}筆已平倉）")
    print(msg)
    send_telegram_msg(msg)


def main():
    thresholds = load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']
    causal_cutoffs = thresholds['vol_ratio_top_tercile_cutoff_causal_by_symbol']
    corr = thresholds['correlation_matrix']
    state = load_state()

    still_open = []
    for pos in state['positions']:
        pos, is_open = process_position(pos, state, cutoffs)
        if is_open:
            still_open.append(pos)
    state['positions'] = still_open
    n_open = len(state['positions'])

    now = pd.Timestamp.now('UTC').tz_localize(None)
    for s in SYMBOLS:
        last_entry = state['last_entry_time'].get(s)
        if last_entry is not None and (now - pd.Timestamp(last_entry)) < pd.Timedelta(hours=COOLDOWN_HOURS):
            continue

        df = fetch_recent_1h(s)
        if len(df) < 21:
            print(f"{s}: not enough closed-bar history yet, skipping")
            continue
        avg_gain, avg_loss = compute_rsi_state(df['close'])
        df['avg_gain'] = avg_gain
        df['avg_loss'] = avg_loss
        df['atr'] = compute_atr(df)

        cand = detect_entry(s, df, causal_cutoffs[s])
        if cand is None:
            continue

        state['last_entry_time'][s] = str(cand['entry_time'])

        open_legs = [(p['symbol'], p['direction']) for p in state['positions']]
        trial_risk = portfolio_risk(open_legs + [(s, cand['direction'])], corr)
        if n_open >= MAX_CONCURRENT_GROUPS or trial_risk > RISK_BUDGET:
            msg = (f"⏭️ 【訊號略過(v3)，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】"
                   f"{s} @ {fmt_taipei(cand['entry_time'])} 推估量能比={cand['projected_vol_ratio']:.2f}")
            print(msg)
            send_telegram_msg(msg)
            continue

        atr = cand['atr']
        direction = cand['direction']
        entry_price = cand['entry_price']
        sl_price = entry_price - SL_ATR_MULT * atr if direction == 'long' else entry_price + SL_ATR_MULT * atr
        tp_price = entry_price + TP_ATR_MULT * atr if direction == 'long' else entry_price - TP_ATR_MULT * atr

        new_pos = {
            'symbol': s, 'direction': direction, 'entry_time': str(cand['entry_time']),
            'entry_price': entry_price, 'atr': atr, 'sl_price': float(sl_price), 'tp_price': float(tp_price),
            'hour_start': str(cand['hour_start']), 'hour_end': str(cand['hour_end']),
            'vol_confirmed': False, 'last_checked': str(cand['entry_time']),
        }
        state['positions'].append(new_pos)
        n_open += 1
        risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price)
        msg = (f"📗 【模擬盤進場-v3，提早進場】{s} {direction.upper()}\n"
               f"時間: {fmt_taipei(cand['entry_time'])}（小時第{cand['minutes_into_hour']}分鐘觸發）  進場價: {entry_price:.4f}\n"
               f"停損: {sl_price:.4f}  停利: {tp_price:.4f}\n"
               f"風險金額: ${risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {BASE_RISK_PER_TRADE*100:.0f}%）"
               f"  建議部位: {qty:.4f}（名目 ${notional_usd:,.2f}）\n"
               f"即時推估量能比: {cand['projected_vol_ratio']:.2f}（收盤後會再次確認真實量能）\n"
               f"目前同時持倉組數: {n_open}  相關性風險: {trial_risk:.2f}/{RISK_BUDGET}")
        print(msg)
        send_telegram_msg(msg)

    save_state(state)
    print(f"\nRun complete. Open positions: {len(state['positions'])}. "
          f"Cumulative paper P&L (v3): {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed']} closed legs.")


if __name__ == "__main__":
    main()
