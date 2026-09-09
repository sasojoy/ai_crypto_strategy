"""
Hourly Telegram report: the 2 symbols currently closest to a v3 anticipatory
entry trigger (RSI-cross threshold price), so you can eyeball how close the
market is without watching all 5 symbols. Read-only -- reuses momentum_monitor_v3's
threshold math and live-price fetch, never opens/closes any paper or real position,
and doesn't touch any monitor's state files.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import momentum_monitor_v3 as v3


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

    rows = []
    for s in v3.SYMBOLS:
        r = compute_symbol_status(s, causal_cutoffs)
        if r is not None:
            rows.append(r)

    if not rows:
        print("No symbols had enough data this run.")
        return

    rows.sort(key=lambda r: abs(r['nearer_pct']))
    top2 = rows[:2]

    lines = ["\U0001F4CA 【入場門檻快報】最接近觸發的兩個幣種"]
    for r in top2:
        dir_label = '做多' if r['nearer_dir'] == 'LONG' else '做空'
        vol_ok = "✅" if (not np.isnan(r['vol_ratio']) and r['vol_ratio'] >= r['vol_cutoff']) else "❌"
        lines.append(
            f"\n{r['symbol']}  RSI={r['rsi']:.1f}  現價={r['live_price']:.4f}\n"
            f"最接近方向: {dir_label}  距門檻 {r['nearer_pct']:+.2f}%\n"
            f"  多: {r['thr_long']:.4f}({r['pct_long']:+.2f}%)  空: {r['thr_short']:.4f}({r['pct_short']:+.2f}%)\n"
            f"  量能比 {r['vol_ratio']:.2f}/{r['vol_cutoff']:.2f} {vol_ok}"
        )
    msg = "\n".join(lines)
    print(msg)
    v3.send_telegram_msg(msg)


if __name__ == "__main__":
    main()
