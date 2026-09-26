"""
Real-time WebSocket entry-SIGNAL detector for v7 (2026-09-26), built after
the user asked to cut signal-to-execution latency further with
"即時WebSocket K棒推送" (real-time WebSocket kline streaming). Per the
user's explicit scoping ("只換掉接入偵測學的部分（偵測新訊號），其他不動" --
only replace the signal-DETECTION part, leave everything else alone), this
process handles ONLY "did a new entry signal just appear" -- everything
else (orphan checks, SL/TP health/repair, close reconciliation) stays on
live_v7.py's existing 1-minute REST poll, unchanged.

WHY A SEPARATE PROCESS, NOT A REWRITE OF live_v7.py: this needs an asyncio
event loop (ccxt.pro's watch_ohlcv() is async-only) held open indefinitely,
which is a fundamentally different run model from live_v7.py's "wake up
once, do a poll, exit" Task Scheduler design. Splitting means neither
piece's control flow has to compromise for the other's.

MECHANISM: v7's already-validated anticipatory-entry math (see
momentum_monitor_v7.py's compute_entry_thresholds()/check_bar_for_signal(),
split out of detect_entry() specifically for this reuse) is UNCHANGED.
What's new is how the "is this hour's touch+volume condition satisfied"
check gets fed:
  - live_v7.py's REST poll only ever evaluates the check once per FULLY
    CLOSED 1-minute bar (it fetches closed klines, walks them in order).
  - This daemon evaluates it CONTINUOUSLY as the current, still-forming
    minute's high/low/volume update in real time via ccxt.pro's
    watch_ohlcv() (sub-second updates per Binance) -- `minutes_elapsed` is
    generalized from an integer bar count to a fractional
    (closed-minutes-so-far + fraction-of-the-current-minute-elapsed)
    value, so the SAME volume-projection formula and threshold check that
    was holdout-validated at whole-minute boundaries now also gives a
    sensible answer mid-minute. At an exact minute boundary the fractional
    value reduces to the same integer the REST path would have used, so
    this is a strict generalization, not a different rule.
  - Only the CURRENT (still-forming) minute's own high/low is checked
    against thresholds, matching detect_entry()'s existing per-bar (not
    running-max) semantics exactly -- once a minute closes, its high/low
    is no longer separately checked, same as the REST path.

Market data (WS klines) is read from Binance's PUBLIC stream, no
credentials -- same "signals from real market data, only orders touch
testnet" convention as everywhere else in live_trading/. Uses ccxt.pro,
bundled with the already-installed ccxt package (confirmed 2026-09-26,
no separate pip install needed).

Meant to run 24/7, started at Windows boot via Task Scheduler (an
"At startup" trigger, not an interval -- see README's Scheduling section)
and restarted by watchdog.py if its heartbeat file goes stale.
"""
import asyncio
import os
import sys
import time

import pandas as pd
import ccxt.pro as ccxtpro

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'paper_trading'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import momentum_monitor_v7 as v7
import live_v7 as lv
from state_lock import state_lock
from src.notifier import send_telegram_msg
from binance_client import make_exchange, TRADING_MODE

MODE_TAG = f"[{TRADING_MODE.upper()}-v7-WS]"
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
HEARTBEAT_PATH = os.path.join(THIS_DIR, 'state', 'ws_detector_heartbeat.txt')

REFRESH_SECONDS = 60       # how often each symbol's closed-bar setup (thresholds/ATR/ADX) is recomputed via REST
THRESHOLDS_REFRESH_SECONDS = 300  # how often threshold_report.py's output file is re-read, to pick up updates live
HEARTBEAT_SECONDS = 20
RECONNECT_BACKOFF_SECONDS = 5

per_symbol = {s: {
    'setup': None,
    'minute_volumes': {},   # {minute_open_ts (pd.Timestamp): volume so far for that minute}
    'current_minute_ts': None,
    'current_bar_high': None,
    'current_bar_low': None,
} for s in v7.SYMBOLS}

shared = {'th': None}  # live_v7.load_thresholds_meta() result, refreshed periodically


def refresh_setup(symbol):
    """Blocking REST call -- run via asyncio.to_thread so it never stalls
    the event loop's WebSocket processing. Same pipeline live_v7.py/the
    paper monitor use to build the indicator columns detect_entry() needs,
    just calling compute_entry_thresholds() directly instead of the full
    detect_entry() (which also does its own REST 1-minute fetch we don't
    want here -- we're feeding it from the WS stream instead)."""
    df = v7.fetch_recent_1h(symbol)
    if len(df) < 21:
        return None
    avg_gain, avg_loss = v7.compute_rsi_state(df['close'])
    df['avg_gain'] = avg_gain
    df['avg_loss'] = avg_loss
    df['atr'] = v7.compute_atr(df)
    df['adx'] = v7.compute_adx(df)
    return v7.compute_entry_thresholds(symbol, df)


async def refresh_setup_loop(symbol):
    while True:
        try:
            setup = await asyncio.to_thread(refresh_setup, symbol)
            if setup is not None:
                per_symbol[symbol]['setup'] = setup
        except Exception as e:
            print(f"{MODE_TAG} {symbol}: refresh_setup failed ({e}), keeping previous setup")
        await asyncio.sleep(REFRESH_SECONDS)


async def refresh_thresholds_loop():
    while True:
        try:
            shared['th'] = lv.load_thresholds_meta()
        except Exception as e:
            print(f"{MODE_TAG} load_thresholds_meta failed ({e}), keeping previous thresholds")
        await asyncio.sleep(THRESHOLDS_REFRESH_SECONDS)


async def heartbeat_loop():
    os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
    while True:
        with open(HEARTBEAT_PATH, 'w') as f:
            f.write(str(pd.Timestamp.now('UTC').tz_localize(None)))
        await asyncio.sleep(HEARTBEAT_SECONDS)


def handle_signal(testnet_ex, symbol, cand):
    """Runs off the event loop (asyncio.to_thread) since it makes real,
    blocking REST calls to testnet (balance, entry, SL/TP) and takes the
    cross-process state lock. Always loads FRESH state under the lock, so
    concurrent WS ticks that raced to detect the same touch (there can be
    many per second) each independently see whatever the previous one
    already committed -- the second one onward will see the position (or
    the cooldown attempt_entry() sets even on a skip) already in state and
    no-op, so this is safe to call redundantly without a separate
    per-symbol debounce."""
    with state_lock(lv.STATE_PATH):
        state = lv.load_state()
        state = lv.attempt_entry(testnet_ex, state, symbol, cand, shared['th'])
        lv.save_state(state)


async def watch_symbol(testnet_ex, symbol):
    exchange = ccxtpro.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    try:
        while True:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, '1m')
            except Exception as e:
                print(f"{MODE_TAG} {symbol}: WS error ({e}), reconnecting in {RECONNECT_BACKOFF_SECONDS}s")
                await asyncio.sleep(RECONNECT_BACKOFF_SECONDS)
                continue

            bar_ts, o, h, l, c, v = ohlcv[-1]
            bar_minute = pd.Timestamp(bar_ts, unit='ms')
            st = per_symbol[symbol]
            st['current_minute_ts'] = bar_minute
            st['current_bar_high'] = h
            st['current_bar_low'] = l
            st['minute_volumes'][bar_minute] = v
            # Bound memory -- only ever need the current hour's minutes.
            cutoff = bar_minute - pd.Timedelta(hours=1)
            for old_ts in [ts for ts in st['minute_volumes'] if ts < cutoff]:
                del st['minute_volumes'][old_ts]

            setup = st['setup']
            th = shared['th']
            if setup is None or th is None:
                continue
            hour_start, hour_end = setup['hour_start'], setup['hour_end']
            if not (hour_start <= bar_minute < hour_end):
                continue  # setup is for a different hour than the bar we just got (rollover in progress)

            closed_minutes = [ts for ts in st['minute_volumes'] if hour_start <= ts < bar_minute]
            closed_vol_sum = sum(st['minute_volumes'][ts] for ts in closed_minutes)
            cum_vol = closed_vol_sum + v
            now = pd.Timestamp.now('UTC').tz_localize(None)
            frac = min(max((now - bar_minute).total_seconds() / 60.0, 0.0), 1.0)
            minutes_elapsed = len(closed_minutes) + frac
            if minutes_elapsed <= 0:
                continue

            causal_cutoff = th['causal_cutoffs'][symbol]
            cand = v7.check_bar_for_signal(setup, h, l, cum_vol, minutes_elapsed, causal_cutoff)
            if cand is None:
                continue
            cand['entry_time'] = now
            print(f"{MODE_TAG} {symbol} {cand['direction']} signal @ {cand['entry_price']} "
                  f"(vol_ratio={cand['projected_vol_ratio']:.2f}, minutes_elapsed={minutes_elapsed:.2f})")
            await asyncio.to_thread(handle_signal, testnet_ex, symbol, cand)
    finally:
        await exchange.close()


async def main():
    testnet_ex = make_exchange()
    shared['th'] = lv.load_thresholds_meta()
    for s in v7.SYMBOLS:
        per_symbol[s]['setup'] = await asyncio.to_thread(refresh_setup, s)

    startup_msg = f"🟢 {MODE_TAG} 即時WebSocket訊號偵測器啟動，追蹤 {', '.join(v7.SYMBOLS)}"
    print(startup_msg)
    send_telegram_msg(startup_msg)

    tasks = [asyncio.create_task(watch_symbol(testnet_ex, s)) for s in v7.SYMBOLS]
    tasks.append(asyncio.create_task(refresh_thresholds_loop()))
    tasks.append(asyncio.create_task(heartbeat_loop()))
    for s in v7.SYMBOLS:
        tasks.append(asyncio.create_task(refresh_setup_loop(s)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
