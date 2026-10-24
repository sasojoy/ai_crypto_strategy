"""
STEP 1 of the WebSocket real-time entry-detection build (2026-09-26):
confirms ccxt.pro's watch_ohlcv() actually streams real-time 1-minute
kline updates from Binance Futures PUBLIC data (no credentials -- same
"signals from real market data" convention as the polling-based
live_v7.py/momentum_monitor_v7.py, only the resulting orders ever touch
testnet). Read-only, prints incoming updates for a fixed duration so the
update frequency/format can be visually confirmed before anything is
built on top of it.

Run: ../venv/Scripts/python.exe test_ws_connection.py
"""
import asyncio
import sys
import os

import ccxt.pro as ccxtpro

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

SYMBOL = 'BTC/USDT'
RUN_SECONDS = 20


async def main():
    exchange = ccxtpro.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    print(f"Connecting to Binance Futures public WebSocket for {SYMBOL} 1m klines...")
    end_time = asyncio.get_event_loop().time() + RUN_SECONDS
    update_count = 0
    try:
        while asyncio.get_event_loop().time() < end_time:
            ohlcv = await exchange.watch_ohlcv(SYMBOL, '1m')
            update_count += 1
            last = ohlcv[-1]
            ts, o, h, l, c, v = last
            import pandas as pd
            print(f"  update #{update_count}  bar_open={pd.Timestamp(ts, unit='ms')}  "
                  f"O={o} H={h} L={l} C={c} V={v}")
    finally:
        await exchange.close()

    print(f"\n✅ Received {update_count} updates in {RUN_SECONDS}s. WebSocket connection works.")


if __name__ == "__main__":
    asyncio.run(main())
