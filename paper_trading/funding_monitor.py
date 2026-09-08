"""
PAPER-TRADING MONITOR for the locked delta-neutral funding-rate carry
strategy (RESEARCH_FINDINGS.md "第十二/十三次測試",
scripts/dev_funding_carry.py's CONDITIONAL variant: hold long-spot/short-
perp only while the trailing 3-day average funding rate is positive,
flip to cash otherwise). Read-only: fetches public funding-rate history
via ccxt (no API key / trade permission needed). Tracks paper P&L and
sends a Telegram notification whenever the position's on/off status
flips, so a human can decide whether to open/close the real hedge.
Never places a real order.

Per DEPLOYMENT_RISK_ASSESSMENT.md, single-asset (BTC, optionally +ETH) is
recommended over the 4-asset diversified version -- diversifying across
BTC/ETH/NEAR/AVAX was shown in dev_carry_portfolio.py to REDUCE risk-
adjusted return (funding goes negative across assets together during
deleveraging, so it isn't true diversification) -- so CARRY_SYMBOLS
defaults to just those two.

Run this periodically (e.g. every 8 hours, matching the funding
settlement cadence -- see paper_trading/README.md). Each run:
  1. Loads state (per-symbol on/off status, cumulative paper P&L, last-
     processed funding print) from state/funding_state.json.
  2. Fetches recent funding-rate history per symbol.
  3. Recomputes the trailing 3-day (9-print) average and the resulting
     on/off decision, exactly as dev_funding_carry.py's conditional().
  4. Adds any new (not yet counted) funding prints to the paper P&L while
     "on"; subtracts the round-trip cost on every on/off toggle.
  5. Sends a Telegram notification only when the on/off decision changes
     for a symbol (a real actionable regime shift), not on every run.

Sends Telegram messages via src/notifier.py's send_telegram_msg (same
notification infra as momentum_monitor.py -- configure
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in a .env file at the project root).

Not part of the deployed app (v600.46) -- standalone paper-trading system,
does not touch the live trading pipeline in src/market.py.
"""
import os
import sys
import json

import ccxt
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.notifier import send_telegram_msg

CARRY_SYMBOLS = ['BTC/USDT', 'ETH/USDT']  # see docstring; NEAR/AVAX can be added but aren't recommended
TRAILING_WINDOW = 9  # 3 days of 8h prints, matches scripts/dev_funding_carry.py

SPOT_FEE_PER_LEG = 0.001
PERP_FEE_PER_LEG = 0.0004
ROUND_TRIP_COST = 2 * SPOT_FEE_PER_LEG + 2 * PERP_FEE_PER_LEG  # 0.28%, matches dev_funding_carry.py

LOOKBACK_DAYS = 30  # enough for the 9-print trailing window plus buffer

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(THIS_DIR, 'state', 'funding_state.json')
LOG_PATH = os.path.join(THIS_DIR, 'state', 'funding_events_log.csv')

exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {s: {'position_on': False, 'last_processed': None, 'collected_pct': 0.0, 'switching_cost_pct': 0.0, 'toggles': 0} for s in CARRY_SYMBOLS}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def append_log(row):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    df = pd.DataFrame([row])
    header = not os.path.exists(LOG_PATH)
    df.to_csv(LOG_PATH, mode='a', header=header, index=False)


def fetch_recent_funding(symbol):
    since = exchange.parse8601((pd.Timestamp.now('UTC') - pd.Timedelta(days=LOOKBACK_DAYS)).isoformat())
    all_rows = []
    while True:
        batch = exchange.fetch_funding_rate_history(symbol, since=since, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        since = batch[-1]['timestamp'] + 1
    df = pd.DataFrame([{'timestamp': r['timestamp'], 'funding_rate': r['fundingRate']} for r in all_rows])
    if df.empty:
        return df
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)


def main():
    state = load_state()
    for s in CARRY_SYMBOLS:
        if s not in state:
            state[s] = {'position_on': False, 'last_processed': None, 'collected_pct': 0.0, 'switching_cost_pct': 0.0, 'toggles': 0}
        sym_state = state[s]

        df = fetch_recent_funding(s)
        if df.empty:
            print(f"{s}: no funding data returned")
            continue
        df['trailing_avg'] = df['funding_rate'].rolling(TRAILING_WINDOW, min_periods=1).mean()
        want_on = bool(df['trailing_avg'].iloc[-1] > 0)
        was_on = sym_state['position_on']
        first_run = sym_state['last_processed'] is None

        last_ts = sym_state['last_processed']
        new_rows = df if last_ts is None else df[df['timestamp'] > pd.Timestamp(last_ts)]
        if was_on and not first_run:
            sym_state['collected_pct'] += new_rows['funding_rate'].sum() * 100

        if first_run:
            sym_state['position_on'] = want_on
            print(f"{s}: first run, baseline established -- position_on={want_on}, "
                  f"trailing_3d_avg={df['trailing_avg'].iloc[-1]*100:.4f}% (no toggle cost charged for this initial state)")
        elif want_on != was_on:
            sym_state['toggles'] += 1
            sym_state['switching_cost_pct'] += ROUND_TRIP_COST / 2 * 100
            sym_state['position_on'] = want_on
            net = sym_state['collected_pct'] - sym_state['switching_cost_pct']
            direction = "轉為持有對沖部位（trailing 3日均資金費率轉正）" if want_on else "轉為空手退出（trailing 3日均資金費率轉負）"
            msg = (f"💱 【資金費率套利：狀態變更】{s}\n"
                   f"{direction}\n"
                   f"最新3日均資金費率: {df['trailing_avg'].iloc[-1]*100:.4f}%\n"
                   f"累計已收資金費率: {sym_state['collected_pct']:+.3f}%  累計切換成本: {sym_state['switching_cost_pct']:.3f}%\n"
                   f"淨額（未含開平倉手續費以外的滑價）: {net:+.3f}%")
            print(msg)
            send_telegram_msg(msg)
            append_log({'symbol': s, 'timestamp': str(df['timestamp'].iloc[-1]), 'event': 'toggle',
                        'new_status_on': want_on, 'trailing_avg_pct': df['trailing_avg'].iloc[-1] * 100,
                        'collected_pct': sym_state['collected_pct'], 'switching_cost_pct': sym_state['switching_cost_pct']})
        else:
            print(f"{s}: no change, position_on={was_on}, trailing_3d_avg={df['trailing_avg'].iloc[-1]*100:.4f}%, "
                  f"collected={sym_state['collected_pct']:+.3f}%")

        if len(df):
            sym_state['last_processed'] = str(df['timestamp'].iloc[-1])

    save_state(state)
    print("\nRun complete.")
    for s in CARRY_SYMBOLS:
        st = state[s]
        net = st['collected_pct'] - st['switching_cost_pct']
        print(f"  {s}: position_on={st['position_on']}  net_pct={net:+.3f}%  toggles={st['toggles']}")


if __name__ == "__main__":
    main()
