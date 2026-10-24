"""
Shared exchange connection + order-placement primitives for live_trading/.
Used by both the manual smoke test (test_order_mechanics.py) and the real
v7 executor (live_v7.py) so both go through the exact same order logic --
no separate "test path" vs "real path" for the dangerous part.

TRADING_MODE env var selects testnet vs mainnet (default: testnet, so a
missing/blank env var can never accidentally mean "real money"). Mainnet
credentials (BINANCE_API_KEY/BINANCE_API_SECRET) are not used anywhere yet
-- this file only wires up testnet until the user explicitly asks to add
mainnet support.
"""
import os

import ccxt
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

TRADING_MODE = os.getenv('TRADING_MODE', 'testnet').strip().lower()


def make_exchange():
    if TRADING_MODE != 'testnet':
        # Mainnet path deliberately not implemented yet -- see module docstring. Fails loudly
        # rather than silently falling back to testnet or guessing mainnet credentials.
        raise RuntimeError(
            f"TRADING_MODE={TRADING_MODE!r} is not supported yet -- only 'testnet' is wired up "
            f"so far. Mainnet support is a deliberate, separate later step."
        )
    api_key = os.getenv('BINANCE_TESTNET_API_KEY')
    api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
    if not api_key or not api_secret:
        raise RuntimeError("BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET not set in .env")
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'disableFuturesSandboxWarning': True,  # see test_connection.py's comment for why
        },
    })
    exchange.set_sandbox_mode(True)
    exchange.load_markets()
    return exchange


def set_leverage(exchange, symbol, leverage):
    market = exchange.market(symbol)
    exchange.set_leverage(leverage, market['id'])


def place_market_entry(exchange, symbol, direction, qty):
    """Just the entry leg -- split out from placing SL/TP (2026-09-21)
    because a market order's own create_order response's 'average'/
    'price' fields are ALWAYS null on Binance Futures (confirmed by
    direct testing -- Binance's raw response always has `"price": "0.00"`
    for a MARKET order, only ever set for LIMIT orders); the true fill
    price only exists in the resulting trade record. A caller that needs
    the real fill price (to size/place SL/TP relative to what actually
    happened, not the pre-fill theoretical price) MUST call
    get_actual_fill_price() afterwards -- see that function's docstring
    for why this matters (found via a real ~2% entry-price discrepancy on
    testnet, not a hypothetical)."""
    entry_side = 'buy' if direction == 'long' else 'sell'
    return exchange.create_order(symbol, 'market', entry_side, qty)


def get_actual_fill_price(exchange, symbol, order_id, retries=4, retry_delay_sec=1.5):
    """The REAL average fill price for order_id, read from the trade
    record (fetch_my_trades), not the order response (see
    place_market_entry()'s docstring -- market order responses never
    carry it). Found necessary 2026-09-21 after a live SOL/USDT entry's
    recorded price (from the theoretical signal price, the buggy old
    fallback) came out ~2% away from the real fill (115.82) -- over a
    5-minute poll interval, price can move enough for this to matter for
    both the recorded entry price AND for where SL/TP actually end up
    relative to the true cost basis.

    RETRIES (added 2026-09-25): the very first version of this function
    queried fetch_my_trades() exactly once and returned None -- silently
    triggering the caller's "theoretical price" fallback -- if the fill
    wasn't indexed there yet. Confirmed this isn't actually rare: a real
    AVAX/USDT entry hit it and rode with SL/TP computed off the stale
    theoretical price (same class of bug as the SOL incident) until this
    session's own health check caught the mismatch. A short retry loop
    resolves the ordinary indexing-lag case; if it's still not there
    after ~6 seconds, something is genuinely wrong and the caller's
    fallback is the right call, not an infinite wait."""
    import time
    for attempt in range(retries):
        matching = [t for t in exchange.fetch_my_trades(symbol, limit=10) if str(t['order']) == str(order_id)]
        if matching:
            total_qty = sum(float(t['amount']) for t in matching)
            return sum(float(t['price']) * float(t['amount']) for t in matching) / total_qty
        if attempt < retries - 1:
            time.sleep(retry_delay_sec)
    return None


def place_sl_tp(exchange, symbol, direction, qty, sl_price, tp_price):
    """Places a STOP_MARKET and a TAKE_PROFIT_MARKET order (explicit
    quantity + reduceOnly=True, not closePosition -- see the CRITICAL
    FINDING note below for why that distinction doesn't actually matter
    for where the order ends up, but matters a lot for margin/quantity
    clarity).

    CRITICAL FINDING (2026-09-20, discovered on testnet before ever
    wiring real signals to this): on this ccxt version (4.5.78), Binance
    Futures STOP_MARKET/TAKE_PROFIT_MARKET orders are ALWAYS routed to a
    separate "conditional/algo order" system (POST /fapi/v1/algoOrder),
    regardless of closePosition vs reduceOnly+quantity. Plain
    fetch_order()/fetch_orders()/fetch_open_orders()/cancel_all_orders()
    do NOT see these at all -- an order can be verified to genuinely
    exist and be live (algoStatus: NEW) on the exchange while looking
    exactly like a silent failure to code that only checks the regular
    order endpoints. Use fetch_open_conditional_orders() /
    cancel_all_conditional_orders() below for these, always -- never the
    plain fetch_open_orders()/cancel_all_orders() for SL/TP.

    Returns {'sl': order, 'tp': order}. The CALLER is responsible for
    cancelling whichever did NOT fire once the position is confirmed flat
    (Binance does not auto-cancel one when the other fills, since they're
    two independent conditional orders)."""
    exit_side = 'sell' if direction == 'long' else 'buy'
    sl_order = exchange.create_order(
        symbol, 'STOP_MARKET', exit_side, qty, None,
        params={'stopPrice': sl_price, 'reduceOnly': True},
    )
    tp_order = exchange.create_order(
        symbol, 'TAKE_PROFIT_MARKET', exit_side, qty, None,
        params={'stopPrice': tp_price, 'reduceOnly': True},
    )
    return {'sl': sl_order, 'tp': tp_order}


def open_position_with_sl_tp(exchange, symbol, direction, qty, sl_price, tp_price):
    """Convenience wrapper combining place_market_entry() + place_sl_tp()
    for callers that don't need the real fill price in between (e.g. the
    manual smoke test, where sl_price/tp_price are already arbitrary).
    live_v7.py does NOT use this -- it needs get_actual_fill_price() in
    between, see that function's docstring."""
    entry_order = place_market_entry(exchange, symbol, direction, qty)
    sl_tp = place_sl_tp(exchange, symbol, direction, qty, sl_price, tp_price)
    return {'entry': entry_order, 'sl': sl_tp['sl'], 'tp': sl_tp['tp']}


def close_position_market(exchange, symbol, direction, qty):
    """Immediate market close of an existing position (e.g. v7's
    VOL_UNCONFIRMED early exit). reduceOnly guarantees this can only ever
    shrink/close an existing position, never accidentally open a new one
    in the opposite direction if qty is wrong."""
    close_side = 'sell' if direction == 'long' else 'buy'
    return exchange.create_order(symbol, 'market', close_side, qty, None, params={'reduceOnly': True})


def fetch_open_conditional_orders(exchange, symbol):
    """The SL/TP orders open_position_with_sl_tp() places -- see that
    function's CRITICAL FINDING note. `conditional: True` is ccxt's own
    documented param (binance.py's cancelAllOrders/fetchOpenOrders) for
    routing to the algo-order endpoints instead of the regular ones."""
    return exchange.fetch_open_orders(symbol, params={'conditional': True})


def cancel_all_conditional_orders(exchange, symbol):
    return exchange.cancel_all_orders(symbol, params={'conditional': True})


def cancel_all_symbol_orders(exchange, symbol):
    """Cancels EVERYTHING for a symbol: regular orders AND conditional
    (SL/TP) orders -- these are two separate systems on Binance Futures
    (see open_position_with_sl_tp()'s CRITICAL FINDING note), so both
    calls are required; neither one alone is a full cleanup."""
    exchange.cancel_all_orders(symbol)
    cancel_all_conditional_orders(exchange, symbol)


def get_open_position(exchange, symbol):
    """Returns the open position dict for symbol, or None if flat. Source
    of truth is always the EXCHANGE, never local state -- local state is
    only used to remember metadata (which order IDs are SL vs TP, etc.)
    the exchange position object itself doesn't carry."""
    positions = exchange.fetch_positions([symbol])
    for p in positions:
        if float(p.get('contracts') or 0) != 0:
            return p
    return None
