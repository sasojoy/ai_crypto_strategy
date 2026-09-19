"""
PAPER-TRADING MONITOR v7 -- COMBINES v3's real-time ANTICIPATORY ENTRY
mechanism with v6's ADX-SCALED RISK sizing. Both are independently
(thinly) holdout/dev-validated mechanisms that change ORTHOGONAL things
(v3: entry timing: v6: per-trade risk%) and had never been tested together
until the user asked for it (2026-09-19).

Dev-window test (scripts/dev_momentum_v3_plus_v6.py, RESEARCH_FINDINGS.md
"v3+v6疊加測試"): on v3's own (fresh-cross-bug-FIXED) trigger population
(n=4,381), applying v6's ADX percentile-rank risk scaling (1%-3%, same
formula, average risk still exactly 2%) instead of v3's flat 2% gave
PF 1.11->1.15, total(linear) +468.6%->+620.4%, quarters_PF>1 19/24->20/24,
top-3-trade concentration 2.5%->2.8% (still healthy) -- and crucially, ALL
5 SYMBOLS individually improved, including v3's own worst symbol (BTC:
-59.3 -> -12.8). A clean, consistent, non-cliff-edge improvement, unlike
the mixed/negative result from combining v6 with a tighter TP instead (see
dev_momentum_tighter_tp_plus_v6.py) -- this is the ONE combination out of
several tested on 2026-09-19 that actually earned deployment.

Everything else is v3 UNCHANGED: same touch-price + real-time
volume-projection entry (see momentum_monitor_v3.py's own docstring/
mechanism section for the full description, including its 2026-09-19
fresh-cross-guard bug fix), same post-close VOL_UNCONFIRMED confirmation
checkpoint, same SL=2.0xATR/TP=4.0xATR/168-bar-hold. The ONLY difference
from v3 is that risk_frac is computed from that trade's ADX(14) (at the
same last-closed bar used for its entry threshold) instead of being a flat
BASE_RISK_PER_TRADE.

LIVE APPROXIMATION: reuses the SAME `adx_p1_within_tercile_by_symbol` /
`adx_p99_within_tercile_by_symbol` anchors from thresholds.json that
momentum_monitor_v6.py uses (calibrated on the CLASSIC closed-bar trigger
population, not v3's own anticipatory-entry population) -- the dev-window
test above calibrated its rank fresh within v3's own population, so this
live version is an approximation of that, same spirit as v5/v6's existing
"can't rank against an unknown future population live" approximation.
Recalibrating a v3-specific anchor pair is a possible future refinement,
not done here to avoid adding a third calibration path for a first
deployment.

DEV-WINDOW-VALIDATED ONLY, NOT HOLDOUT-VALIDATED. This is a brand new
combination -- neither v3's nor v6's individual holdout passes cover it.
Tracks its own independent P&L in state/momentum_v7_*, doesn't affect
v1/v2/v3/v4/v5/v6's track records.

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
    SYMBOLS, compute_atr, SL_ATR_MULT, TP_ATR_MULT, ROUND_TRIP_FRICTION, MAX_HOLD_BARS,
)
from dev_momentum_adx_trend_filter import compute_adx
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

MAX_CONCURRENT_GROUPS = 5
RISK_BUDGET = 3.0
COOLDOWN_HOURS = 8
ALPHA = 1 / 14  # Wilder RSI(14) smoothing factor

MIN_RISK = 0.01   # risk fraction at (or below) the adx_p1 anchor
MAX_RISK = 0.03   # risk fraction at (or above) the adx_p99 anchor

REFERENCE_CAPITAL_USD = 1000  # illustrative paper-trading base for the dollar figures shown in
                               # Telegram messages only -- P&L tracking itself stays entirely in
                               # % terms (cumulative_pnl_pct), this doesn't feed back into it


def adx_scaled_risk(adx_value, p1, p99):
    """Same live approximation as momentum_monitor_v6.py: linearly maps
    ADX(14) from [p1 -> MIN_RISK] to [p99 -> MAX_RISK], clamped outside
    that range."""
    if np.isnan(adx_value) or p99 <= p1:
        return (MIN_RISK + MAX_RISK) / 2
    rank = (adx_value - p1) / (p99 - p1)
    rank = max(0.0, min(1.0, rank))
    return MIN_RISK + rank * (MAX_RISK - MIN_RISK)


def position_size_usd(entry_price, sl_price, risk_frac):
    risk_usd = REFERENCE_CAPITAL_USD * risk_frac
    sl_dist = abs(entry_price - sl_price)
    qty = risk_usd / sl_dist if sl_dist > 0 else 0.0
    return risk_usd, qty, qty * entry_price


LOOKBACK_DAYS = 45
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v7_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v7_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """Same correlation-aware portfolio-risk calc as v1-v6."""
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


def leg_pnl_pct(direction, entry_price, exit_price, sl_price, risk_frac):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price - ROUND_TRIP_FRICTION
    else:
        pnl = (entry_price - exit_price) / entry_price - ROUND_TRIP_FRICTION
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * risk_frac * 100 if sl_dist_pct > 0 else 0.0


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


def detect_entry(symbol, df_closed, causal_cutoff):
    """Same as momentum_monitor_v3.py's detect_entry() (including the
    2026-09-19 fresh-cross guard), plus capturing the last closed bar's
    ADX(14) for risk sizing."""
    if len(df_closed) < 21:
        return None
    last_close = df_closed['close'].iloc[-1]
    ag_prev = df_closed['avg_gain'].iloc[-1]
    al_prev = df_closed['avg_loss'].iloc[-1]
    atr_sizing = df_closed['atr'].iloc[-1]
    adx_value = df_closed['adx'].iloc[-1]
    vol_ma20_causal = df_closed['volume'].iloc[-20:].mean()
    if np.isnan(ag_prev) or np.isnan(al_prev) or np.isnan(atr_sizing) or atr_sizing <= 0 or vol_ma20_causal <= 0:
        return None
    last_rsi = 50.0 if al_prev == 0 else 100 - 100 / (1 + ag_prev / al_prev)

    # Fresh-cross guard -- see momentum_monitor_v3.py's detect_entry() for the full writeup
    # (2026-09-19 bug fix: without this, a sustained overbought/oversold run solves a threshold
    # on the WRONG side of last_close, which the next candle then satisfies almost trivially).
    thr_long = threshold_price(last_close, ag_prev, al_prev, 70) if last_rsi <= 70 else None
    thr_short = threshold_price(last_close, ag_prev, al_prev, 30) if last_rsi >= 30 else None
    if thr_long is None and thr_short is None:
        return None

    hour_start = df_closed['timestamp'].iloc[-1] + pd.Timedelta(hours=1)
    dfm = fetch_1m_since(symbol, hour_start)
    if dfm.empty:
        return None

    cum_vol = 0.0
    for i, bar in enumerate(dfm.itertuples(), start=1):
        cum_vol += bar.volume
        projected_ratio = (cum_vol * (60.0 / i)) / vol_ma20_causal
        direction, entry_price = None, None
        if thr_long is not None and bar.high >= thr_long:
            direction, entry_price = 'long', thr_long
        elif thr_short is not None and bar.low <= thr_short:
            direction, entry_price = 'short', thr_short
        if direction is not None and projected_ratio >= causal_cutoff:
            return {
                'direction': direction, 'entry_price': float(entry_price),
                'entry_time': bar.timestamp, 'atr': float(atr_sizing), 'adx': float(adx_value),
                'hour_start': hour_start, 'hour_end': hour_start + pd.Timedelta(hours=1),
                'minutes_into_hour': i, 'projected_vol_ratio': float(projected_ratio),
            }
    return None


def process_position(pos, state, cutoffs):
    """Same as momentum_monitor_v3.py's process_position(), using this
    position's own (ADX-derived, fixed-at-entry) risk_frac for P&L."""
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
                pass
            elif not confirmed:
                _close_position(pos, close, ts, 'VOL_UNCONFIRMED', state)
                return pos, False
            else:
                pos['vol_confirmed'] = True

    pos['last_checked'] = str(df['timestamp'].iloc[-1])
    return pos, True


def _check_volume_confirmed(pos, cutoffs):
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
    pnl = leg_pnl_pct(pos['direction'], pos['entry_price'], exit_price, pos['sl_price'], pos['risk_frac'])
    state['cumulative_pnl_pct'] += pnl
    state['n_closed'] += 1
    log_row = {**pos, 'exit_price': float(exit_price), 'exit_time': str(exit_time),
               'reason': reason, 'equity_pnl_pct': pnl}
    append_trade_log(log_row)
    msg = (f"📕 【模擬盤出場-v7提早進場+重倉版】{pos['symbol']} {pos['direction'].upper()}\n"
           f"原因: {reason}  損益: {pnl:+.2f}%（本筆風險{pos['risk_frac']*100:.2f}%，依ADX動態調整）\n"
           f"進場: {fmt_taipei(pos['entry_time'])} @ {pos['entry_price']:.4f}\n"
           f"出場: {fmt_taipei(exit_time)} @ {exit_price:.4f}\n"
           f"累計模擬損益(v7): {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed']}筆已平倉）")
    print(msg)
    send_telegram_msg(msg)


def main():
    thresholds = load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']
    causal_cutoffs = thresholds['vol_ratio_top_tercile_cutoff_causal_by_symbol']
    adx_p1s = thresholds['adx_p1_within_tercile_by_symbol']
    adx_p99s = thresholds['adx_p99_within_tercile_by_symbol']
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
        df['adx'] = compute_adx(df)

        cand = detect_entry(s, df, causal_cutoffs[s])
        if cand is None:
            continue

        state['last_entry_time'][s] = str(cand['entry_time'])

        open_legs = [(p['symbol'], p['direction']) for p in state['positions']]
        trial_risk = portfolio_risk(open_legs + [(s, cand['direction'])], corr)
        if n_open >= MAX_CONCURRENT_GROUPS or trial_risk > RISK_BUDGET:
            msg = (f"⏭️ 【訊號略過-v7提早進場+重倉版，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】"
                   f"{s} @ {fmt_taipei(cand['entry_time'])} 推估量能比={cand['projected_vol_ratio']:.2f} "
                   f"ADX={cand['adx']:.1f}")
            print(msg)
            send_telegram_msg(msg)
            continue

        atr = cand['atr']
        direction = cand['direction']
        entry_price = cand['entry_price']
        sl_price = entry_price - SL_ATR_MULT * atr if direction == 'long' else entry_price + SL_ATR_MULT * atr
        tp_price = entry_price + TP_ATR_MULT * atr if direction == 'long' else entry_price - TP_ATR_MULT * atr
        risk_frac = adx_scaled_risk(cand['adx'], adx_p1s[s], adx_p99s[s])

        new_pos = {
            'symbol': s, 'direction': direction, 'entry_time': str(cand['entry_time']),
            'entry_price': entry_price, 'atr': atr, 'sl_price': float(sl_price), 'tp_price': float(tp_price),
            'hour_start': str(cand['hour_start']), 'hour_end': str(cand['hour_end']),
            'vol_confirmed': False, 'last_checked': str(cand['entry_time']),
            'adx': cand['adx'], 'risk_frac': float(risk_frac),
        }
        state['positions'].append(new_pos)
        n_open += 1
        risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price, risk_frac)
        msg = (f"📗 【模擬盤進場-v7提早進場+重倉版，趨勢越強押越多】{s} {direction.upper()}\n"
               f"時間: {fmt_taipei(cand['entry_time'])}（小時第{cand['minutes_into_hour']}分鐘觸發）  進場價: {entry_price:.4f}\n"
               f"停損: {sl_price:.4f}  停利: {tp_price:.4f}\n"
               f"風險金額: ${risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {risk_frac*100:.2f}%，依ADX動態調整於1~3%）"
               f"  建議部位: {qty:.4f}（名目 ${notional_usd:,.2f}）\n"
               f"即時推估量能比: {cand['projected_vol_ratio']:.2f}（收盤後會再次確認真實量能）  ADX(14): {cand['adx']:.1f}\n"
               f"目前同時持倉組數: {n_open}  相關性風險: {trial_risk:.2f}/{RISK_BUDGET}")
        print(msg)
        send_telegram_msg(msg)

    save_state(state)
    print(f"\nRun complete. Open positions: {len(state['positions'])}. "
          f"Cumulative paper P&L (v7): {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed']} closed legs.")


if __name__ == "__main__":
    main()
