"""
LIVE EXECUTOR for v7 (提早進場+重倉版), TESTNET ONLY so far (TRADING_MODE
in exchange.py refuses anything else). Reuses v7's exact, already-
validated SIGNAL logic from paper_trading/momentum_monitor_v7.py --
detect_entry() (with its 2026-09-19 fresh-cross-guard fix), the
ADX-scaled risk formula, and the correlation-aware portfolio risk cap --
UNCHANGED, imported directly rather than copy-pasted, so this can never
silently drift from the paper-validated mechanism.

WHAT'S DIFFERENT FROM THE PAPER MONITOR:
  - Signal detection still reads PUBLIC market data from real Binance
    (via v7.fetch_recent_1h/fetch_1m_since, no credentials) -- so signals
    are driven by genuine market conditions, not testnet's thin/synthetic
    order book. Only the resulting ORDERS are sent to testnet.
  - Position sizing uses the REAL testnet account balance (fetched fresh
    each run), not the paper monitor's REFERENCE_CAPITAL_USD=1000
    placeholder.
  - A fixed, conservative leverage (FIXED_LEVERAGE) is set per symbol
    before entry, and a trade is SKIPPED (not resized) if it would need
    more than MAX_MARGIN_FRACTION of account equity as margin -- refusing
    is safer than silently changing the tested risk-sizing math.
  - Real STOP_MARKET/TAKE_PROFIT_MARKET conditional orders are placed at
    entry (see exchange.py's CRITICAL FINDING docstring for why these
    need `conditional: True` to even be visible to monitoring code).
  - Reconciliation: since Binance doesn't auto-cancel one of SL/TP when
    the other fills, and doesn't push a webhook to this polling script,
    "did the position close" is detected by noticing the exchange
    position went flat, then reading the actual closing fill(s) from
    fetch_my_trades() to get the real exit price (comparing it to the
    known sl_price/tp_price only to LABEL the reason for logging -- the
    P&L itself always uses the real fill price, never an assumed one).

NOT YET DONE (deliberately, in order): mainnet credentials/support,
running this on a schedule (still manually invoked while validating),
multi-day soak testing on testnet before ANY mainnet conversation.
"""
import json
import os
import sys
import math

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'paper_trading'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import momentum_monitor_v7 as v7  # the validated, unmodified signal/risk logic
from src.notifier import send_telegram_msg
from src.tz import fmt_taipei

from binance_client import (
    make_exchange, set_leverage, place_market_entry, get_actual_fill_price, place_sl_tp,
    close_position_market, cancel_all_conditional_orders, get_open_position, TRADING_MODE,
)

FIXED_LEVERAGE = 3          # conservative, fixed (not dynamically raised to fit bigger trades)
MAX_MARGIN_FRACTION = 0.30  # never commit more than 30% of account equity as margin to one trade
MODE_TAG = f"[{TRADING_MODE.upper()}-v7]"

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(THIS_DIR, 'state', 'live_v7_state.json')
TRADES_LOG_PATH = os.path.join(THIS_DIR, 'state', 'live_v7_trades_log.csv')


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {'last_entry_time': {}, 'positions': []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def append_trade_log(row):
    """Durable local record of every closed trade -- Telegram messages
    and console output both scroll away/aren't queryable later, and this
    is meant to be run unattended ('認真當實戰'), so a real audit trail
    matters here even more than for the paper monitors (which already do
    this). Same convention as paper_trading/*_trades_log.csv."""
    os.makedirs(os.path.dirname(TRADES_LOG_PATH), exist_ok=True)
    pd.DataFrame([row]).to_csv(TRADES_LOG_PATH, mode='a', header=not os.path.exists(TRADES_LOG_PATH), index=False)


def infer_exit_price_and_reason(testnet_ex, pos):
    """Position is confirmed flat on the exchange. Reads the actual
    closing fill(s) from fetch_my_trades() for the true exit price
    (never assumed), and labels the reason by comparing that price to
    the known sl_price/tp_price purely for logging/notification text."""
    since_ms = int(pd.Timestamp(pos['entry_time']).timestamp() * 1000)
    trades = testnet_ex.fetch_my_trades(pos['symbol'], since=since_ms)
    closing_side = 'sell' if pos['direction'] == 'long' else 'buy'
    # Binance Futures trade fills carry NO 'reduceOnly' field in their raw info (confirmed
    # 2026-09-20) -- 'realizedPnl' is the reliable signal instead: exactly 0 for a trade that
    # opened/added to a position, non-zero for one that reduced/closed it.
    closing_trades = [t for t in trades if t['side'] == closing_side
                       and float(t.get('info', {}).get('realizedPnl', 0)) != 0]
    if not closing_trades:
        # Fallback: no reduceOnly fill found (e.g. manual close on the exchange UI) -- use mark price.
        ticker = testnet_ex.fetch_ticker(pos['symbol'])
        return ticker['last'], 'UNKNOWN'
    total_qty = sum(float(t['amount']) for t in closing_trades)
    exit_price = sum(float(t['price']) * float(t['amount']) for t in closing_trades) / total_qty

    sl_dist = abs(exit_price - pos['sl_price'])
    tp_dist = abs(exit_price - pos['tp_price'])
    reason = 'SL' if sl_dist < tp_dist else 'TP'
    return exit_price, reason


def leg_pnl_pct(direction, entry_price, exit_price, sl_price, risk_frac):
    if direction == 'long':
        pnl = (exit_price - entry_price) / entry_price
    else:
        pnl = (entry_price - exit_price) / entry_price
    sl_dist_pct = abs(entry_price - sl_price) / entry_price
    return (pnl / sl_dist_pct) * risk_frac * 100 if sl_dist_pct > 0 else 0.0


def process_live_position(testnet_ex, pos, cutoffs):
    real_pos = get_open_position(testnet_ex, pos['symbol'])
    if real_pos is None:
        exit_price, reason = infer_exit_price_and_reason(testnet_ex, pos)
        cancel_all_conditional_orders(testnet_ex, pos['symbol'])  # clean up whichever of SL/TP didn't fire
        pnl = leg_pnl_pct(pos['direction'], pos['entry_price'], exit_price, pos['sl_price'], pos['risk_frac'])
        append_trade_log({**pos, 'exit_price': exit_price, 'exit_time': str(pd.Timestamp.now('UTC').tz_localize(None)),
                           'reason': reason, 'equity_pnl_pct': pnl})
        msg = (f"📕 {MODE_TAG} 出場 {pos['symbol']} {pos['direction'].upper()}\n"
               f"原因: {reason}（依成交價還原推斷）  損益: {pnl:+.2f}%（風險{pos['risk_frac']*100:.2f}%）\n"
               f"進場: {fmt_taipei(pos['entry_time'])} @ {pos['entry_price']:.4f}\n"
               f"出場: @ {exit_price:.4f}")
        print(msg)
        send_telegram_msg(msg)
        return pos, False

    hour_end = pd.Timestamp(pos['hour_end'])
    now = pd.Timestamp.now('UTC').tz_localize(None)
    if not pos['vol_confirmed'] and now >= hour_end:
        confirmed = v7._check_volume_confirmed(pos, cutoffs)
        if confirmed is None:
            pass  # entry hour's closed bar not published yet -- retry next run
        elif not confirmed:
            qty = abs(float(real_pos['contracts']))
            close_position_market(testnet_ex, pos['symbol'], pos['direction'], qty)
            cancel_all_conditional_orders(testnet_ex, pos['symbol'])
            ticker = testnet_ex.fetch_ticker(pos['symbol'])
            exit_price = ticker['last']
            pnl = leg_pnl_pct(pos['direction'], pos['entry_price'], exit_price, pos['sl_price'], pos['risk_frac'])
            append_trade_log({**pos, 'exit_price': exit_price, 'exit_time': str(pd.Timestamp.now('UTC').tz_localize(None)),
                               'reason': 'VOL_UNCONFIRMED', 'equity_pnl_pct': pnl})
            msg = (f"📕 {MODE_TAG} 出場 {pos['symbol']} {pos['direction'].upper()}\n"
                   f"原因: VOL_UNCONFIRMED  損益: {pnl:+.2f}%\n"
                   f"進場: {fmt_taipei(pos['entry_time'])} @ {pos['entry_price']:.4f}\n"
                   f"出場: @ {exit_price:.4f}")
            print(msg)
            send_telegram_msg(msg)
            return pos, False
        else:
            pos['vol_confirmed'] = True
    return pos, True


def try_open_position(testnet_ex, symbol, cand, cutoffs_meta):
    """NOTE on entry price: cand['entry_price'] is the THEORETICAL signal
    price (where detect_entry() saw the trigger touched, up to ~5 minutes
    ago given this script's poll interval) -- used below only to size the
    trade and gate the margin check (an approximation, fine for a go/
    no-go decision). The REAL fill price is fetched AFTER the market
    order executes (get_actual_fill_price()) and is what SL/TP actually
    get placed relative to, and what's recorded as entry_price -- found
    necessary 2026-09-21 after a live SOL/USDT entry showed a ~2% gap
    between the theoretical signal price and the real fill."""
    adx_p1, adx_p99 = cutoffs_meta['adx_p1s'][symbol], cutoffs_meta['adx_p99s'][symbol]
    direction, theoretical_price, atr = cand['direction'], cand['entry_price'], cand['atr']
    adx_value = cand['adx']
    risk_frac = v7.adx_scaled_risk(adx_value, adx_p1, adx_p99)

    theoretical_sl = (theoretical_price - v7.SL_ATR_MULT * atr if direction == 'long'
                       else theoretical_price + v7.SL_ATR_MULT * atr)

    balance = testnet_ex.fetch_balance()['USDT']['total'] or 0.0
    risk_usd = balance * risk_frac
    sl_dist_price = abs(theoretical_price - theoretical_sl)
    qty_raw = risk_usd / sl_dist_price if sl_dist_price > 0 else 0.0
    notional = qty_raw * theoretical_price
    margin_needed = notional / FIXED_LEVERAGE

    if balance <= 0 or margin_needed > balance * MAX_MARGIN_FRACTION:
        msg = (f"⏭️ {MODE_TAG} 訊號略過（所需保證金 ${margin_needed:.2f} 超過帳戸權益的"
               f"{MAX_MARGIN_FRACTION*100:.0f}%上限，帳戶餘額${balance:.2f}）"
               f"{symbol} {direction.upper()} @ {fmt_taipei(cand['entry_time'])}")
        print(msg)
        send_telegram_msg(msg)
        return None

    qty = float(testnet_ex.amount_to_precision(symbol, qty_raw))
    if qty <= 0:
        return None

    set_leverage(testnet_ex, symbol, FIXED_LEVERAGE)
    entry_order = place_market_entry(testnet_ex, symbol, direction, qty)
    real_entry_price = get_actual_fill_price(testnet_ex, symbol, entry_order['id'])
    if real_entry_price is None:
        # Trade record not queryable yet (rare timing edge case) -- fall back to the theoretical
        # price rather than crash; SL/TP still gets ATTACHED (a position with none at all would
        # be far worse), just potentially off by whatever the real slippage turns out to be.
        real_entry_price = theoretical_price

    sl_price = real_entry_price - v7.SL_ATR_MULT * atr if direction == 'long' else real_entry_price + v7.SL_ATR_MULT * atr
    tp_price = real_entry_price + v7.TP_ATR_MULT * atr if direction == 'long' else real_entry_price - v7.TP_ATR_MULT * atr
    sl_tp = place_sl_tp(testnet_ex, symbol, direction, qty,
                         testnet_ex.price_to_precision(symbol, sl_price),
                         testnet_ex.price_to_precision(symbol, tp_price))

    new_pos = {
        'symbol': symbol, 'direction': direction, 'entry_time': str(cand['entry_time']),
        'entry_price': float(real_entry_price), 'atr': float(atr), 'adx': float(adx_value),
        'risk_frac': float(risk_frac), 'sl_price': float(sl_price), 'tp_price': float(tp_price),
        'hour_start': str(cand['hour_start']), 'hour_end': str(cand['hour_end']),
        'vol_confirmed': False, 'qty': qty, 'leverage': FIXED_LEVERAGE,
        'sl_order_id': sl_tp['sl']['id'], 'tp_order_id': sl_tp['tp']['id'],
    }
    slippage_pct = (real_entry_price - theoretical_price) / theoretical_price * 100
    msg = (f"📗 {MODE_TAG} 進場 {symbol} {direction.upper()}\n"
           f"時間: {fmt_taipei(cand['entry_time'])}  訊號價: {theoretical_price:.4f}  "
           f"實際成交: {real_entry_price:.4f}（滑價{slippage_pct:+.2f}%，下單量{qty}，槓桿{FIXED_LEVERAGE}x）\n"
           f"停損: {sl_price:.4f}  停利: {tp_price:.4f}（依實際成交價重算）\n"
           f"風險: {risk_frac*100:.2f}%（帳戶權益${balance:.2f}）  ADX(14): {adx_value:.1f}\n"
           f"即時推估量能比: {cand['projected_vol_ratio']:.2f}（收盤後會再次確認真實量能）")
    print(msg)
    send_telegram_msg(msg)
    return new_pos


def main():
    testnet_ex = make_exchange()
    thresholds = v7.load_thresholds()
    cutoffs = thresholds['vol_ratio_top_tercile_cutoff_by_symbol']
    causal_cutoffs = thresholds['vol_ratio_top_tercile_cutoff_causal_by_symbol']
    cutoffs_meta = {'adx_p1s': thresholds['adx_p1_within_tercile_by_symbol'],
                    'adx_p99s': thresholds['adx_p99_within_tercile_by_symbol']}
    corr = thresholds['correlation_matrix']
    state = load_state()

    still_open = []
    for pos in state['positions']:
        pos, is_open = process_live_position(testnet_ex, pos, cutoffs)
        if is_open:
            still_open.append(pos)
    state['positions'] = still_open
    n_open = len(state['positions'])

    now = pd.Timestamp.now('UTC').tz_localize(None)
    for s in v7.SYMBOLS:
        if any(p['symbol'] == s for p in state['positions']):
            continue  # already have a live position on this symbol
        last_entry = state['last_entry_time'].get(s)
        if last_entry is not None and (now - pd.Timestamp(last_entry)) < pd.Timedelta(hours=v7.COOLDOWN_HOURS):
            continue

        df = v7.fetch_recent_1h(s)
        if len(df) < 21:
            print(f"{s}: not enough closed-bar history yet, skipping")
            continue
        avg_gain, avg_loss = v7.compute_rsi_state(df['close'])
        df['avg_gain'] = avg_gain
        df['avg_loss'] = avg_loss
        df['atr'] = v7.compute_atr(df)
        df['adx'] = v7.compute_adx(df)

        cand = v7.detect_entry(s, df, causal_cutoffs[s])
        if cand is None:
            continue
        state['last_entry_time'][s] = str(cand['entry_time'])

        real_open_legs = []
        for p in state['positions']:
            real_open_legs.append((p['symbol'], p['direction']))
        trial_risk = v7.portfolio_risk(real_open_legs + [(s, cand['direction'])], corr)
        if n_open >= v7.MAX_CONCURRENT_GROUPS or trial_risk > v7.RISK_BUDGET:
            msg = (f"⏭️ {MODE_TAG} 訊號略過，相關性風險預算已滿（{trial_risk:.2f} > {v7.RISK_BUDGET}）"
                   f"{s} @ {fmt_taipei(cand['entry_time'])}")
            print(msg)
            send_telegram_msg(msg)
            continue

        new_pos = try_open_position(testnet_ex, s, cand, cutoffs_meta)
        if new_pos is not None:
            state['positions'].append(new_pos)
            n_open += 1

    save_state(state)
    print(f"\nRun complete ({TRADING_MODE}). Open positions: {len(state['positions'])}.")


if __name__ == "__main__":
    main()
