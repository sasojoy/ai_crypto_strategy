"""
STEP 1 of the live-trading rollout for v7 (提早進場+重倉版): confirms the
Binance Futures TESTNET credentials work at all, before any order-placement
code is written. Read-only -- fetches account balance and open positions,
places NO orders.

Deliberately a separate, brand-new `live_trading/` tree, not reusing any
of the old v600.x PerpPredator/emergency_kill.py code (per the user's
explicit instruction, 2026-09-21) -- no shared naming, no shared assumptions.

Run: ../venv/Scripts/python.exe test_connection.py
"""
import os
import sys

import ccxt
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))


def make_testnet_exchange():
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
            # ccxt 4.x's set_sandbox_mode() now hard-refuses futures testnet ("please use demo
            # trading instead" -- see the deprecation link in ccxt/binance.py's sign()), even
            # though testnet.binancefuture.com itself is still live and working. This flag is
            # ccxt's own documented escape hatch (binance.py: `disableFuturesSandboxWarning`) to
            # skip that refusal, since we're deliberately choosing testnet for validation, not
            # accidentally landing on it.
            'disableFuturesSandboxWarning': True,
            'warnOnFetchOpenOrdersWithoutSymbol': False,
            'fetchOpenOrders': {'warnWithoutSymbol': False},
        },
    })
    exchange.set_sandbox_mode(True)  # routes to testnet.binancefuture.com, not the real exchange
    return exchange


def main():
    exchange = make_testnet_exchange()

    print("Connecting to Binance Futures TESTNET...")
    print(f"  sandbox mode: {exchange.urls.get('api')}")

    balance = exchange.fetch_balance()
    usdt = balance.get('USDT', {})
    print(f"\nUSDT balance: total={usdt.get('total')}  free={usdt.get('free')}  used={usdt.get('used')}")
    if usdt.get('total') is None:
        raw_assets = balance.get('info', {}).get('assets', [])
        raw_usdt = next((a for a in raw_assets if a.get('asset') == 'USDT'), None)
        print(f"  (parsed USDT was empty -- raw testnet asset entry: {raw_usdt})")

    positions = exchange.fetch_positions()
    open_positions = [p for p in positions if float(p.get('contracts') or 0) != 0]
    print(f"\nOpen positions: {len(open_positions)}")
    for p in open_positions:
        print(f"  {p['symbol']}: {p['side']} {p['contracts']} contracts @ {p['entryPrice']}")

    # fetch_open_orders() with NO symbol routes ccxt to a SPOT endpoint even with
    # defaultType='future' (confirmed 2026-09-21: it hit testnet.binance.vision, a different
    # testnet system with different credentials, and 401'd) -- passing a symbol keeps it on futures.
    open_orders = exchange.fetch_open_orders('BTC/USDT')
    print(f"\nOpen orders (BTC/USDT only, as a connectivity check): {len(open_orders)}")
    for o in open_orders:
        print(f"  {o['symbol']}: {o['side']} {o['type']} {o['amount']} @ {o.get('price') or o.get('stopPrice')}")

    ticker = exchange.fetch_ticker('BTC/USDT')
    print(f"\nSanity check -- BTC/USDT last price on testnet: {ticker['last']}")

    print("\n✅ Testnet connection working. No orders were placed.")


if __name__ == "__main__":
    main()
