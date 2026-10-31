"""
STEP 2 of the live-trading rollout for v7: validates the actual order-
placement mechanics (exchange.py) on TESTNET with a real (fake-money)
trade, BEFORE wiring up v7's real entry signals. Manually triggered, one
symbol, minimum size -- not driven by any strategy logic yet.

Two separate invocations (no interactive input() -- this is meant to be run
via a tool that can't pause for a keypress mid-script):
  python test_order_mechanics.py open   -- sets leverage, opens a tiny LONG
      market position on BTC/USDT, places STOP_MARKET + TAKE_PROFIT_MARKET
      around it, prints everything, then EXITS leaving it open so it can be
      visually checked on https://testnet.binancefuture.com/.
  python test_order_mechanics.py close  -- flattens the position at market
      and cancels any remaining SL/TP order, leaving the account clean.

Run: ../venv/Scripts/python.exe test_order_mechanics.py open
     ../venv/Scripts/python.exe test_order_mechanics.py close
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from binance_client import (
    make_exchange, set_leverage, open_position_with_sl_tp,
    close_position_market, cancel_all_symbol_orders, get_open_position,
    fetch_open_conditional_orders,
)

SYMBOL = 'BTC/USDT'
LEVERAGE = 2


def do_open():
    exchange = make_exchange()
    market = exchange.market(SYMBOL)
    print(f"Market limits for {SYMBOL}: amount_min={market['limits']['amount']['min']}  "
          f"cost_min={market['limits']['cost']['min']}  amount_precision={market['precision']['amount']}")

    existing = get_open_position(exchange, SYMBOL)
    if existing:
        print(f"\n⚠️  {SYMBOL} already has an open position ({existing['side']} {existing['contracts']}) "
              f"-- aborting so this test doesn't interfere with it.")
        return

    print(f"\nSetting {LEVERAGE}x leverage on {SYMBOL}...")
    set_leverage(exchange, SYMBOL, LEVERAGE)

    ticker = exchange.fetch_ticker(SYMBOL)
    last_price = ticker['last']
    min_cost = market['limits']['cost']['min'] or 100
    qty = exchange.amount_to_precision(SYMBOL, (min_cost * 1.2) / last_price)
    qty = float(qty)
    print(f"Last price: {last_price}  ->  test quantity: {qty} {SYMBOL.split('/')[0]} "
          f"(~${qty * last_price:.2f} notional)")

    sl_price = exchange.price_to_precision(SYMBOL, last_price * 0.98)   # -2% (arbitrary, just for the mechanics test)
    tp_price = exchange.price_to_precision(SYMBOL, last_price * 1.02)   # +2%

    print(f"\nOpening LONG {qty} {SYMBOL} @ market, SL={sl_price}, TP={tp_price}...")
    result = open_position_with_sl_tp(exchange, SYMBOL, 'long', qty, sl_price, tp_price)
    print(f"  Entry order: id={result['entry']['id']} status={result['entry']['status']}")
    print(f"  SL order:    id={result['sl']['id']} stopPrice={sl_price}")
    print(f"  TP order:    id={result['tp']['id']} stopPrice={tp_price}")

    time.sleep(2)
    pos = get_open_position(exchange, SYMBOL)
    print(f"\nConfirmed position on exchange: {pos['side']} {pos['contracts']} @ entryPrice={pos['entryPrice']}")

    open_orders = fetch_open_conditional_orders(exchange, SYMBOL)
    print(f"Open conditional (SL/TP) orders confirmed on exchange: {len(open_orders)} "
          f"({[(o['type'], o['triggerPrice']) for o in open_orders]})")

    print(f"\n--- Left open on purpose. Check https://testnet.binancefuture.com/en/futures/{SYMBOL.replace('/', '')} "
          f"to visually confirm the position + SL/TP orders look right, then run:\n"
          f"    python test_order_mechanics.py close ---")


def do_close():
    exchange = make_exchange()
    pos = get_open_position(exchange, SYMBOL)
    if pos is None:
        print(f"No open {SYMBOL} position found -- cancelling any stray orders and exiting.")
        cancel_all_symbol_orders(exchange, SYMBOL)
        return

    direction = 'long' if pos['side'] == 'long' else 'short'
    qty = abs(float(pos['contracts']))
    print(f"Closing {direction} {qty} {SYMBOL} at market and cancelling remaining SL/TP orders...")
    close_position_market(exchange, SYMBOL, direction, qty)
    cancel_all_symbol_orders(exchange, SYMBOL)

    time.sleep(2)
    pos_after = get_open_position(exchange, SYMBOL)
    orders_after = fetch_open_conditional_orders(exchange, SYMBOL)
    print(f"\nFinal check -- open position: {pos_after}  |  open conditional orders: {len(orders_after)}")
    print("Cleaned up." if pos_after is None and not orders_after else "Still open -- check manually.")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else None
    if action == 'open':
        do_open()
    elif action == 'close':
        do_close()
    else:
        print("Usage: python test_order_mechanics.py [open|close]")
