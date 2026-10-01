"""
Weekly forward-tracking report (scheduled task PaperTrading-ForwardReport).
Runs both frozen forward trackers -- v7 (forward_tracker.py) and BRK4H
(brk4h.py forward) -- and sends a short summary to Telegram. Neither
tracker's rules are touched here; this only runs them and reads their
output CSVs. Also appends the summary to data/forward/weekly_report.log.
"""
import contextlib
import io
import os
import sys
import traceback
from datetime import datetime

import pandas as pd
from scipy.stats import ttest_1samp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.notifier import send_telegram_msg
import forward_tracker
import brk4h

FWD = forward_tracker.OUT


def summarize(name, csv, final_n):
    d = pd.read_csv(csv)
    closed = d[d.status != 'OPEN']
    lines = [f"【{name}】訊號 {len(d)} 筆（已結束 {len(closed)}、持倉中 {int((d.status == 'OPEN').sum())}）"]
    if len(closed) >= 2:
        p = ttest_1samp(closed.r, 0, alternative='greater').pvalue
        lines.append(f"  勝率 {(closed.r > 0).mean()*100:.1f}%｜平均 {closed.r.mean():+.3f}R｜累計 {closed.r.sum():+.1f}R｜p={p:.3f}")
        for side, zh in (('long', '多'), ('short', '空')):
            x = closed[closed.direction == side]
            if len(x):
                lines.append(f"  {zh}單 {len(x)} 筆，平均 {x.r.mean():+.3f}R")
    if len(closed) >= final_n:
        p = ttest_1samp(closed.r, 0, alternative='greater').pvalue
        ok = closed.r.mean() > 0 and p < 0.05
        lines.append(f"  ★ 已達 {final_n} 筆，最終判定：{'優勢確認' if ok else '優勢未確認'}")
    else:
        lines.append(f"  進度 {len(closed)}/{final_n} 筆（期中只看不判定）")
    return '\n'.join(lines)


def main():
    buf = io.StringIO()
    parts, errors = [], []
    for name, fn in (('v7', forward_tracker.report), ('BRK4H', brk4h.forward)):
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                fn()
        except Exception:
            errors.append(f"{name} 執行失敗：\n{traceback.format_exc()[-600:]}")
    for name, csv, n in (('v7 前瞻追蹤', 'forward_trades.csv', forward_tracker.FINAL_N),
                         ('BRK4H 前瞻追蹤', 'forward_trades_brk4h.csv', brk4h.FINAL_N)):
        path = os.path.join(FWD, csv)
        if os.path.exists(path):
            parts.append(summarize(name, path, n))
    msg = f"📊 【前瞻追蹤週報】{datetime.now():%Y-%m-%d}\n（50幣、凍結規則、2026-10-01起）\n\n" + '\n\n'.join(parts)
    if errors:
        msg += '\n\n⚠️ ' + '\n'.join(errors)
    with open(os.path.join(FWD, 'weekly_report.log'), 'a', encoding='utf-8') as f:
        f.write(msg + '\n\n' + '=' * 40 + '\n')
    send_telegram_msg(msg)


if __name__ == '__main__':
    main()
