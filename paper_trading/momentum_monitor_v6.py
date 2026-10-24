"""
PAPER-TRADING MONITOR v6 -- EXPERIMENTAL, DEV-WINDOW BACKTESTED BUT NOT
HOLDOUT-VALIDATED. Same locked RSI(14) oversold/overbought momentum-
continuation entry/exit rules, timing, and SL/TP (2.0xATR/4.0xATR) as v1
-- the ONLY difference is per-trade RISK SIZING: instead of a flat 2% of
reference capital, risk scales 1%-3% (averaging back to ~2%) with each
trade's Wilder ADX(14) trend strength at entry, so a trade fired during a
choppy/weak-trend stretch risks less and one fired during a strong trend
risks more. The existing top-tercile volume gate is COMPLETELY UNCHANGED --
every trade that qualifies today still qualifies, none are skipped.

WHY: the user suspected (and live paper-trading data then confirmed --
2026-09-09~14, all of v1/v2/v3/v4 underperformed their backtested win
rates during a stretch where ADX showed ETH/NEAR spent 81-85% of the week
below 25, i.e. genuinely choppy) that this strategy does worse in choppy
markets. A first attempt (scripts/dev_momentum_adx_trend_filter.py) tried
a binary ADX>=25 skip-the-trade gate and found it net-negative: per-trade
quality improved but cutting 46.3% of signals shrank annualized return far
more than the quality gain made up for. This monitor implements the
suggested fix instead -- scale size down in chop rather than skipping the
trade outright, so trade count doesn't collapse.

Dev-window test (scripts/dev_momentum_adx_scaled_risk.py, "rank" mode --
RESEARCH_FINDINGS.md "ADX連動風險"): scaling risk by each trade's
percentile rank of ADX(14) within its symbol's top-tercile-qualifying
population (the same fairness property as v5's vol_ratio ranking --
average risk locked to exactly 2%, not a stealth leverage increase) gave
PF 1.22->1.24, annualized (linear) +82.3%->+88.1%/yr, same 19/24 quarters
PF>1 as baseline, at the cost of slightly higher top-3-trade concentration
(2.4%->3.4%, still healthy). A cruder FIXED-ANCHOR version (ADX 15->1%,
35->3%, no ranking) looked better at first (+92.9%/yr) but that was
partly an illusion -- its average risk crept up to 2.12% (not exactly
2%), so some of the apparent gain was just taking slightly more risk on
average, not smarter allocation. The rank-based version above is the one
actually deployed here, because it's the fair, apples-to-apples comparison.
Win rate is UNCHANGED by design (40.6%->40.6%) -- this mechanism doesn't
touch which trades win or lose, only how much is risked on each.

LIVE APPROXIMATION OF "PERCENTILE RANK": same reasoning as v5 -- a live
monitor can't rank a trade against a still-unknown future population.
Unlike v5's vol_ratio (which already has a natural lower anchor, the
existing tercile cutoff), ADX has no such built-in floor, so BOTH ends are
pre-calibrated from thresholds.json: `adx_p1_within_tercile_by_symbol`
(-> risk 1%) and `adx_p99_within_tercile_by_symbol` (-> risk 3%), the 1st/
99th percentile of ADX among that symbol's own historical top-tercile-
qualifying triggers (calibrate_momentum_threshold.py). Re-run that script
periodically to keep both anchors current.

HOLDOUT-VALIDATED (2026-09-14, scripts/holdout_v6_adx_scaled_risk.py --
RESEARCH_FINDINGS.md "v6 封存區驗證", this project's SECOND-ever use of the
one-shot 2026+ holdout window, done at the user's explicit request): on
222 out-of-sample holdout candidates, ADX-scaled risk (avg 2.02%, no
material drift from the flat-2% baseline) scored PF 1.13 / compounded
+29.76% vs the same trades' flat-2% baseline PF 1.04 / +1.74% -- the
dev-window improvement replicated out of sample, same direction, at least
as large. Same thin-margin, mixed-by-symbol character as the original
locked-spec holdout pass (BTC/NEAR net positive, ETH/AVAX net negative,
SOL marginal) -- not a reason for outsized confidence, just confirmation
the mechanism isn't a dev-window fluke. Has NOT been tested combined with
v4's wider-stop or v5's vol-ratio risk scaling (each is a separate,
untested combination -- see v3's docstring for why this research line
tests one mechanism at a time). Tracks its own independent P&L in
state/momentum_v6_*, doesn't affect v1/v2/v3/v4/v5's track records.

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
from dev_momentum_adx_trend_filter import compute_adx
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

MIN_RISK = 0.01   # risk fraction at (or below) the adx_p1 anchor
MAX_RISK = 0.03   # risk fraction at (or above) the adx_p99 anchor

MAX_CONCURRENT = 5  # kept as an absolute backstop even under the risk-budget cap below
RISK_BUDGET = 3.0  # correlation-aware portfolio-risk cap, same convention as v1/v2/v3/v4/v5
LOOKBACK_DAYS = 45   # enough bars for RSI/ATR/vol_ma20/ADX warm-up plus a 7-day max hold

REFERENCE_CAPITAL_USD = 1000  # illustrative paper-trading base for the dollar figures shown in
                               # Telegram messages only -- P&L tracking itself stays entirely in
                               # % terms (cumulative_pnl_pct), this doesn't feed back into it


def adx_scaled_risk(adx_value, p1, p99):
    """Linearly maps ADX(14) from [p1 -> MIN_RISK] to [p99 -> MAX_RISK],
    clamped outside that range. Live, causal approximation of the backtest's
    population-relative percentile rank -- see module docstring."""
    if np.isnan(adx_value) or p99 <= p1:
        return (MIN_RISK + MAX_RISK) / 2  # missing/degenerate data; fall back to the midpoint
    rank = (adx_value - p1) / (p99 - p1)
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
STATE_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v6_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'momentum_v6_trades_log.csv')
THRESHOLDS_PATH = os.path.join(THIS_DIR, 'thresholds.json')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def portfolio_risk(open_legs, corr):
    """Same correlation-aware portfolio-risk calc as v1/v2/v3/v4/v5."""
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
    """Same as v1: only ever compute RSI/ATR/ADX/volume-ratio or check a
    trigger against fully CLOSED 1H bars."""
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
    # risk_frac is the value fixed AT ENTRY (based on that trade's ADX) -- position
    # size was already set then, moving the goalposts on exit would be wrong.
    eq_pnl = (pnl / sl_dist_pct) * pos['risk_frac'] * 100 if sl_dist_pct > 0 else 0.0
    return {**pos, 'exit_price': exit_price, 'exit_time': str(exit_time), 'reason': reason, 'equity_pnl_pct': eq_pnl}


def main():
    thresholds = load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']
    adx_p1s = thresholds['adx_p1_within_tercile_by_symbol']
    adx_p99s = thresholds['adx_p99_within_tercile_by_symbol']
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
            msg = (f"📕 【模擬盤出場-v6】{closed['symbol']} {closed['direction'].upper()}\n"
                   f"原因: {closed['reason']}  損益: {closed['equity_pnl_pct']:+.2f}%"
                   f"（本筆風險{closed['risk_frac']*100:.2f}%，依ADX趨勢強度動態調整）\n"
                   f"進場: {fmt_taipei(pd.Timestamp(closed['entry_time']) + pd.Timedelta(hours=1))} @ {closed['entry_price']:.4f}\n"
                   f"出場: {fmt_taipei(closed['exit_time'])} @ {closed['exit_price']:.4f}\n"
                   f"累計模擬損益(v6): {state['cumulative_pnl_pct']:+.2f}%（{state['n_closed']}筆已平倉）")
            print(msg)
            send_telegram_msg(msg)
        else:
            still_open.append(pos)
    state['open_positions'] = still_open

    for s in SYMBOLS:
        df = fetch_recent_1h(s)
        df['rsi'] = compute_rsi(df['close'])
        df['atr'] = compute_atr(df)
        df['adx'] = compute_adx(df)
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
        adx_p1, adx_p99 = adx_p1s[s], adx_p99s[s]
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
            adx_value = df['adx'].iloc[i]
            risk_frac = adx_scaled_risk(adx_value, adx_p1, adx_p99)

            open_legs = [(p['symbol'], p['direction']) for p in state['open_positions']]
            trial_risk = portfolio_risk(open_legs + [(s, direction)], corr)
            if len(state['open_positions']) >= MAX_CONCURRENT or trial_risk > RISK_BUDGET:
                msg = (f"⏭️ 【訊號略過(v6)，相關性風險預算已滿（{trial_risk:.2f} > {RISK_BUDGET}）】{s} "
                       f"{'oversold' if reversion_direction=='long' else 'overbought'} -> {direction.upper()} "
                       f"@ {fmt_taipei(ts)}  vol_ratio={df['vol_ratio'].iloc[i]:.2f}  ADX={adx_value:.1f}")
                print(msg)
                send_telegram_msg(msg)
                continue

            new_pos = {'symbol': s, 'direction': direction, 'entry_time': str(ts), 'entry_price': float(entry_price),
                       'sl_price': float(sl_price), 'tp_price': float(tp_price),
                       'vol_ratio': float(df['vol_ratio'].iloc[i]), 'adx': float(adx_value),
                       'risk_frac': float(risk_frac)}
            state['open_positions'].append(new_pos)
            risk_usd, qty, notional_usd = position_size_usd(entry_price, sl_price, risk_frac)
            msg = (f"📗 【模擬盤進場-v6，ADX連動風險】{s} {direction.upper()}（{'超賣' if reversion_direction=='long' else '超買'}動能延續）\n"
                   f"時間: {fmt_taipei(ts + pd.Timedelta(hours=1))}  進場價: {entry_price:.4f}\n"
                   f"停損: {sl_price:.4f}  停利: {tp_price:.4f}\n"
                   f"風險金額: ${risk_usd:.2f}（模擬本金 ${REFERENCE_CAPITAL_USD:,} 的 {risk_frac*100:.2f}%，依ADX動態調整於1~3%）"
                   f"  建議部位: {qty:.4f}（名目 ${notional_usd:,.2f}）\n"
                   f"量能比: {df['vol_ratio'].iloc[i]:.2f}（門檻{cutoff:.2f}）  ADX(14): {adx_value:.1f}\n"
                   f"目前同時持倉: {len(state['open_positions'])}  相關性風險: {trial_risk:.2f}/{RISK_BUDGET}")
            print(msg)
            send_telegram_msg(msg)

        if len(df):
            state['last_processed'][s] = str(df['timestamp'].iloc[-1])

    save_state(state)
    print(f"\nRun complete. Open positions: {len(state['open_positions'])}. "
          f"Cumulative paper P&L (v6): {state['cumulative_pnl_pct']:+.2f}% over {state['n_closed']} closed trades.")


if __name__ == "__main__":
    main()
