"""
Pre-trade checker for discretionary short-term perp trades (user request
2026-11-08: "我需要一個可以輔助我開合約短期單的策略").

This is NOT a signal generator. The research in RESEARCH_FINDINGS.md found
no short-term directional signal with a detectable edge in the current
regime. What it DID find, repeatedly, is a handful of regularities that
make a planned trade systematically worse or better. This tool checks a
trade you already intend to take against those, with live public data:

  1. REGIME   BTC funding 30-day annualised. Directional momentum only had
              edge when > 10% (walk-forward 2026-10-18, funding gate 10-24,
              P1 11-08: V7 Sharpe on/off +1.46 / -0.12).
  2. CARRY    the coin's 7-day mean funding rank among the 50 research
              coins. Long the top-20% funding / short the bottom-20% is
              against the one factor that held everywhere (K1, price part
              alone +23%/yr dev, 2024-25 Sharpe 1.9, 2026 Sharpe 1.2).
  3. EXTENSION  24-bar run-up / ATR in the trade direction (D1). In funding
              < 5% regimes the most extended quintile did -0.50R in 2026;
              in > 10% regimes it was the BEST quintile (+0.32R, dev).
  4. VOLUME   last closed 1h bar volume / 20-bar mean vs the coin's frozen
              v7 cutoff (volume confirmation held across all coin sizes).
  5. SETTLEMENT  extreme funding settlement within the next hour: price
              drifts against the paying side into settlement and reverts
              after (~6-8 bp, below taker fees; timing only).
  6. FRAME    SL 2 x ATR / TP 4 x ATR / max 7 days, and the management
              rules every tested alternative lost to.

Usage:
  python scripts/trade_check.py SOL long
  python scripts/trade_check.py XMR short --risk 20      # size for 20 USDT risk
  python scripts/trade_check.py BTC long --telegram
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv, _ARGV = sys.argv[:1], sys.argv  # some research modules parse argv on import
from fetch_holdout_2026 import coins  # noqa: E402
sys.argv = _ARGV

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
GATE_ON, GATE_OFF = 0.10, 0.05


def ann30(ex, base='BTC'):
    h = ex.fetch_funding_rate_history(f'{base}/USDT:USDT', limit=90)
    rates = [x['fundingRate'] for x in h]
    return float(np.mean(rates) * 3 * 365), len(rates)


def funding_7d(ex, bases):
    out = {}
    for b in bases:
        try:
            h = ex.fetch_funding_rate_history(f'{b}/USDT:USDT', limit=21)
            if h:
                out[b] = float(np.mean([x['fundingRate'] for x in h]))
        except Exception:
            pass
    return pd.Series(out)


def own_funding(ex, base):
    cur = ex.fetch_funding_rate(f'{base}/USDT:USDT')
    hist = ex.fetch_funding_rate_history(f'{base}/USDT:USDT', limit=90)
    rates = np.array([abs(x['fundingRate']) for x in hist])
    thr = max(np.quantile(rates, 0.9), 1e-4) if len(rates) >= 30 else np.inf
    rate = cur.get('fundingRate')
    nxt = cur.get('fundingTimestamp')
    return rate, nxt, float(thr)


def ohlcv_1h(ex, base, n=400):
    o = ex.fetch_ohlcv(f'{base}/USDT:USDT', '1h', limit=n)
    df = pd.DataFrame(o, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    return df.iloc[:-1].reset_index(drop=True)  # drop the still-forming bar


def atr(df, n=14):
    pc = df['close'].shift(1)
    tr = pd.concat([df['high'] - df['low'], (df['high'] - pc).abs(), (df['low'] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def rsi(close, n=14):
    d = close.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + g / l.replace(0, np.nan))).fillna(50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('base', help='coin, e.g. SOL')
    ap.add_argument('direction', choices=['long', 'short'])
    ap.add_argument('--risk', type=float, default=None, help='USDT you are willing to lose at the stop')
    ap.add_argument('--telegram', action='store_true')
    a = ap.parse_args()
    base, sgn = a.base.upper(), 1 if a.direction == 'long' else -1
    ex = ccxt.binanceusdm({'enableRateLimit': True})
    ex.load_markets()
    red, yellow, green, lines = 0, 0, 0, []

    def flag(kind, text):
        nonlocal red, yellow, green
        mark = {'red': '🔴', 'yellow': '🟡', 'green': '🟢', 'info': '⚪'}[kind]
        if kind == 'red':
            red += 1
        elif kind == 'yellow':
            yellow += 1
        elif kind == 'green':
            green += 1
        lines.append(f'{mark} {text}')

    now = datetime.now(timezone.utc)
    lines.append(f'開單檢查 {base} {"多" if sgn > 0 else "空"}  {now:%Y-%m-%d %H:%M} UTC')

    # 1. regime
    g, n = ann30(ex)
    if g > GATE_ON:
        flag('green', f'市場狀態：BTC 費率 30 日年化 {g*100:.1f}% > 10%，方向性動能歷史上有優勢的狀態（V7 開 Sharpe +1.46）')
        regime = 'on'
    elif g < GATE_OFF:
        flag('red', f'市場狀態：BTC 費率 30 日年化 {g*100:.1f}% < 5%，方向性動能歷史上沒有優勢（V7 關 Sharpe −0.12；2026 此狀態下延伸進場 −0.5R）')
        regime = 'off'
    else:
        flag('yellow', f'市場狀態：BTC 費率 30 日年化 {g*100:.1f}%，介於 5～10%，方向性動能無明確證據（P3：此區 D1 效果約 0）')
        regime = 'mid'

    # 2. cross-sectional carry
    f7 = funding_7d(ex, coins())
    if base in f7.index:
        pct = float((f7 < f7[base]).mean())
        txt = f'橫截面費率：{base} 7 日平均費率 {f7[base]*100:.4f}%，在 {len(f7)} 個研究幣中第 {pct*100:.0f} 百分位'
        if (sgn > 0 and pct >= 0.8) or (sgn < 0 and pct <= 0.2):
            flag('red', txt + '。這筆單站在套息因子的反面（K1 價格部分 +23%/年，是全研究唯一到處都成立的因子）')
        elif (sgn > 0 and pct <= 0.2) or (sgn < 0 and pct >= 0.8):
            flag('green', txt + '。與套息因子同向')
        else:
            flag('info', txt + '。中段，因子無明顯方向')
    else:
        f7b = funding_7d(ex, [base]).get(base, np.nan)
        pct = float((f7 < f7b).mean())
        txt = f'橫截面費率：{base} 不在 50 個研究幣內；7 日平均費率 {f7b*100:.4f}%，對照 50 幣分布約第 {pct*100:.0f} 百分位（參考用）'
        if (sgn > 0 and pct >= 0.8) or (sgn < 0 and pct <= 0.2):
            flag('yellow', txt + '。站在套息因子的反面')
        elif (sgn > 0 and pct <= 0.2) or (sgn < 0 and pct >= 0.8):
            flag('info', txt + '。與套息因子同向')
        else:
            flag('info', txt)

    # 3-4. price structure
    df = ohlcv_1h(ex, base)
    df['atr'] = atr(df)
    df['rsi'] = rsi(df['close'])
    i = len(df) - 1
    px, a14 = float(df['close'].iloc[i]), float(df['atr'].iloc[i])
    h24, l24 = df['high'].iloc[i - 23:i + 1], df['low'].iloc[i - 23:i + 1]
    d1 = (px - l24.min()) / a14 if sgn > 0 else (h24.max() - px) / a14
    with open(os.path.join(S, 'entry_location_cuts.json')) as fh:
        cuts = json.load(fh)['cuts']['runup24_atr']
    q = int(np.searchsorted(cuts, d1, side='right')) + 1
    txt = f'走勢延伸：順方向 24 根走幅 {d1:.1f} ATR，開發區第 {q}/5 分位'
    if q == 5 and regime == 'off':
        flag('red', txt + '。低費率狀態下最延伸的一組 2026 平均 −0.50R（最後一漲／最後一跌就是這種）')
    elif q == 5 and regime == 'on':
        flag('green', txt + '。高費率狀態下最延伸的一組反而最好（開發區 +0.32R）')
    elif q == 5:
        flag('yellow', txt + '。中間狀態，延伸的方向效應不明')
    else:
        flag('info', txt)
    vr = float(df['volume'].iloc[i] / df['volume'].iloc[i - 19:i + 1].mean())
    with open(os.path.join(S, 'forward_frozen_cutoffs.json')) as fh:
        allcuts = json.load(fh)
    cut = allcuts.get(base)
    if cut is None:
        ref = float(np.median(list(allcuts.values())))
        if vr > ref:
            flag('info', f'量能：最後一根 1H 量比 {vr:.2f}，高於 50 幣門檻中位數 {ref:.2f}（此幣無自己的凍結門檻，參考用）')
        else:
            flag('yellow', f'量能：最後一根 1H 量比 {vr:.2f}，低於 50 幣門檻中位數 {ref:.2f}（此幣無自己的凍結門檻，參考用）')
    elif vr > cut:
        flag('green', f'量能：最後一根 1H 量比 {vr:.2f} > 該幣凍結門檻 {cut:.2f}，有量能確認（各種規模的幣都成立）')
    else:
        flag('yellow', f'量能：最後一根 1H 量比 {vr:.2f} ≤ 門檻 {cut:.2f}，沒有量能確認（無確認的訊號開發區平均為負）')
    r = float(df['rsi'].iloc[i])
    lines.append(f'⚪ RSI(14) {r:.0f}，ATR(14) {a14:.6g}（{a14/px*100:.2f}%），價格 {px:.6g}')

    # 5. settlement timing
    rate, nxt, thr = own_funding(ex, base)
    if rate is not None and nxt:
        mins = (nxt - ex.milliseconds()) / 60000
        paying = 1 if rate > 0 else -1  # longs pay when positive
        txt = f'結算：目前費率 {rate*100:.4f}%，下次結算 {mins:.0f} 分鐘後'
        if abs(rate) > thr and mins <= 60:
            if sgn == paying:
                flag('yellow', txt + f'。極端費率（>該幣 90 分位 {thr*100:.3f}%），結算前價格傾向往付費方的反向走、結算後回彈（約 6～8 bp）。你跟付費方同向，等結算後再進比較好')
            else:
                flag('info', txt + '。極端費率，你站在收費方；結算前的順風只有 6～8 bp，低於手續費，不值得為它開單')
        else:
            flag('info', txt)

    # 6. frame
    sl = px - sgn * 2 * a14
    tp = px + sgn * 4 * a14
    lines.append(f'⚪ 框架：停損 {sl:.6g}（{2*a14/px*100:.2f}%）、停利 {tp:.6g}（{4*a14/px*100:.2f}%）、最長持有 7 天')
    if a.risk:
        qty = a.risk / (2 * a14)
        lines.append(f'⚪ 以 {a.risk:g} USDT 風險計：數量 {qty:.6g}，名目約 {qty*px:.0f} USDT')
    lines.append('⚪ 進場後：抱到停損或停利。下一根反向＋量縮時出場（−0.34R）、停損移到保本、等回踩再進、確認後加碼，全部測過都比抱著差')

    verdict = ('🔴 建議不開：踩到 %d 個系統性的坑' % red if red else
               '🟢 條件齊：%d 個綠旗、沒有紅黃旗。仍然不是訊號，開發區這種單平均不到 +0.1R' % green if (green >= 2 and yellow == 0) else
               '🟡 可以開但沒有優勢證據（綠 %d／黃 %d）：這類單開發區平均約 +0.03R，靠框架管風險' % (green, yellow))
    lines.append(verdict)
    msg = '\n'.join(lines)
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # Windows consoles default to cp950
    except Exception:
        pass
    print(msg)
    if a.telegram:
        from src.notifier import send_telegram_msg
        send_telegram_msg(msg)


if __name__ == '__main__':
    main()
