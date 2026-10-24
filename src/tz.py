"""Display-time helper for paper_trading's Telegram messages. All monitor
state/logs (state/*.json, *_trades_log.csv) stay in UTC -- that's what ccxt/
Binance returns and what every internal comparison (last_processed, cooldowns,
max-hold windows) is keyed on, so it must not change. Only the human-facing
Telegram text gets converted, so a message doesn't force the reader to mentally
add 8 hours. Taiwan has no DST, so a fixed +8h offset is always correct and a
zoneinfo/pytz dependency isn't needed.
"""
import pandas as pd

TAIPEI_OFFSET_HOURS = 8


def fmt_taipei(ts):
    """ts: a naive pandas Timestamp (or anything pd.Timestamp() accepts),
    assumed UTC. Returns a display string in Taiwan local time, labeled so
    it's never mistaken for the UTC timestamps still used in state/logs."""
    local = pd.Timestamp(ts) + pd.Timedelta(hours=TAIPEI_OFFSET_HOURS)
    return f"{local.strftime('%Y-%m-%d %H:%M:%S')} 台灣時間"
