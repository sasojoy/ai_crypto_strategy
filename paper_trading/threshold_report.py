"""
Hourly Telegram report, sent as TWO separate messages so a fast proximity
check and a full portfolio snapshot don't get conflated into one:
  1. The 2 symbols currently closest to a v3 anticipatory entry trigger
     (RSI-cross threshold price), so you can eyeball how close the market is
     without watching all 5 symbols.
  2. A full holdings overview -- EVERY currently open leg across
     v1-v8, not just symbols near a threshold, with entry/SL/TP/
     current price for each. Added 2026-09-11 because message 1 only ever
     surfaces a held symbol if it also happens to be one of the 2 nearest
     to a NEW threshold that hour -- a held symbol sitting quietly mid-
     range between its SL and TP would never appear at all otherwise.
Read-only throughout -- reuses momentum_monitor_v3's threshold math and
live-price fetch, never opens/closes any paper or real position, and only
READS (never writes) the other monitors' state files.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import momentum_monitor_v3 as v3

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state')


def load_all_legs():
    """Every currently open leg across v1-v8, flattened to one dict per
    leg (v2's pyramid add, if any, is its own separate leg alongside v2's
    original). Read-only."""
    legs = []

    def add(symbol, label, leg_name, direction, entry_price, sl_price, tp_price):
        legs.append({
            'symbol': symbol, 'label': label, 'leg': leg_name, 'direction': direction,
            'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
        })

    try:
        with open(os.path.join(STATE_DIR, 'momentum_state.json')) as f:
            for p in json.load(f).get('open_positions', []):
                add(p['symbol'], 'v1基準版', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v2_state.json')) as f:
            for p in json.load(f).get('positions', []):
                orig = p['original']
                if not orig['closed']:
                    add(p['symbol'], 'v2', '原始', p['direction'], orig['entry_price'], orig['sl_price'], orig['tp_price'])
                add_leg = p.get('add')
                if add_leg and not add_leg['closed']:
                    add(p['symbol'], 'v2', '加倉', p['direction'], add_leg['entry_price'], add_leg['sl_price'], add_leg['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v3_state.json')) as f:
            for p in json.load(f).get('positions', []):
                add(p['symbol'], 'v3', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v4_state.json')) as f:
            for p in json.load(f).get('open_positions', []):
                add(p['symbol'], 'v4', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v5_state.json')) as f:
            for p in json.load(f).get('open_positions', []):
                add(p['symbol'], 'v5', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v6_state.json')) as f:
            for p in json.load(f).get('open_positions', []):
                add(p['symbol'], 'v6', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v7_state.json')) as f:
            for p in json.load(f).get('positions', []):
                add(p['symbol'], 'v7強化版', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        with open(os.path.join(STATE_DIR, 'momentum_v8_state.json')) as f:
            for p in json.load(f).get('open_positions', []):
                add(p['symbol'], 'v8穩健版', None, p['direction'], p['entry_price'], p['sl_price'], p['tp_price'])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return legs


def build_holdings_message(legs, live_price_by_symbol):
    if not legs:
        return "\U0001F4C2 【持倉總覽】目前 v1-v8 皆無持倉"

    by_symbol = {}
    for leg in legs:
        by_symbol.setdefault(leg['symbol'], []).append(leg)

    lines = ["\U0001F4C2 【持倉總覽】"]
    for symbol, symbol_legs in by_symbol.items():
        live_price = live_price_by_symbol.get(symbol)
        price_str = f"  現價={live_price:.4f}" if live_price is not None else ""
        lines.append(f"\n{symbol}{price_str}")
        for leg in symbol_legs:
            dir_label = '多' if leg['direction'] == 'long' else '空'
            leg_label = leg['label'] + (f"({leg['leg']})" if leg['leg'] else "")
            lines.append(
                f"  {leg_label} {dir_label}  進場 {leg['entry_price']:.4f}"
                f"  停損 {leg['sl_price']:.4f}  停利 {leg['tp_price']:.4f}"
            )
    return "\n".join(lines)


def compute_symbol_status(s, causal_cutoffs):
    df = v3.fetch_recent_1h(s)
    if len(df) < 21:
        return None
    avg_gain, avg_loss = v3.compute_rsi_state(df['close'])
    df['avg_gain'] = avg_gain
    df['avg_loss'] = avg_loss
    last_close = df['close'].iloc[-1]
    ag_prev = df['avg_gain'].iloc[-1]
    al_prev = df['avg_loss'].iloc[-1]
    if np.isnan(ag_prev) or np.isnan(al_prev):
        return None
    rs = ag_prev / al_prev if al_prev != 0 else np.inf
    current_rsi = 100 - 100 / (1 + rs)
    vol_ma20_causal = df['volume'].iloc[-20:].mean()
    if vol_ma20_causal <= 0:
        return None

    thr_long = v3.threshold_price(last_close, ag_prev, al_prev, 70)
    thr_short = v3.threshold_price(last_close, ag_prev, al_prev, 30)

    hour_start = df['timestamp'].iloc[-1] + pd.Timedelta(hours=1)
    dfm = v3.fetch_1m_since(s, hour_start)
    if not dfm.empty:
        live_price = dfm['close'].iloc[-1]
        minutes_elapsed = len(dfm)
        cum_vol = dfm['volume'].sum()
        projected_ratio = (cum_vol * (60.0 / minutes_elapsed)) / vol_ma20_causal if minutes_elapsed else np.nan
    else:
        live_price = last_close
        minutes_elapsed = 0
        projected_ratio = np.nan

    pct_long = (thr_long - live_price) / live_price * 100
    pct_short = (thr_short - live_price) / live_price * 100

    if abs(pct_long) <= abs(pct_short):
        nearer_dir, nearer_pct = 'LONG', pct_long
    else:
        nearer_dir, nearer_pct = 'SHORT', pct_short

    return {
        'symbol': s, 'rsi': current_rsi, 'live_price': live_price,
        'thr_long': thr_long, 'thr_short': thr_short,
        'pct_long': pct_long, 'pct_short': pct_short,
        'nearer_dir': nearer_dir, 'nearer_pct': nearer_pct,
        'vol_ratio': projected_ratio, 'vol_cutoff': causal_cutoffs[s],
    }


def main():
    thresholds = v3.load_thresholds()
    causal_cutoffs = thresholds['vol_ratio_top_tercile_cutoff_causal_by_symbol']
    legs = load_all_legs()
    held_by_symbol = {}
    for leg in legs:
        held_by_symbol.setdefault(leg['symbol'], set()).add((leg['label'], leg['direction']))

    rows = []
    for s in v3.SYMBOLS:
        r = compute_symbol_status(s, causal_cutoffs)
        if r is not None:
            rows.append(r)

    if not rows:
        print("No symbols had enough data this run.")
        return

    live_price_by_symbol = {r['symbol']: r['live_price'] for r in rows}
    top2 = sorted(rows, key=lambda r: abs(r['nearer_pct']))[:2]

    lines = ["\U0001F4CA 【入場門檻快報】最接近觸發的兩個幣種"]
    for r in top2:
        dir_label = '做多' if r['nearer_dir'] == 'LONG' else '做空'
        vol_ok = "✅" if (not np.isnan(r['vol_ratio']) and r['vol_ratio'] >= r['vol_cutoff']) else "❌"
        held = held_by_symbol.get(r['symbol'])
        if held:
            held_str = "、".join(f"{label}({'多' if d == 'long' else '空'})" for label, d in sorted(held))
            holding_line = f"\n  ⚠️ 目前已持倉: {held_str}"
        else:
            holding_line = "\n  目前無持倉"
        lines.append(
            f"\n{r['symbol']}  RSI={r['rsi']:.1f}  現價={r['live_price']:.4f}\n"
            f"最接近方向: {dir_label}  距門檻 {r['nearer_pct']:+.2f}%\n"
            f"  多: {r['thr_long']:.4f}({r['pct_long']:+.2f}%)  空: {r['thr_short']:.4f}({r['pct_short']:+.2f}%)\n"
            f"  量能比 {r['vol_ratio']:.2f}/{r['vol_cutoff']:.2f} {vol_ok}"
            f"{holding_line}"
        )
    msg1 = "\n".join(lines)
    print(msg1)
    v3.send_telegram_msg(msg1)

    msg2 = build_holdings_message(legs, live_price_by_symbol)
    print(msg2)
    v3.send_telegram_msg(msg2)


if __name__ == "__main__":
    main()
