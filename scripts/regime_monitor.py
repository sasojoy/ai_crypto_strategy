"""
Daily frenzy-regime monitor (scheduled task PaperTrading-RegimeMonitor,
09:05 Taipei). Added 2026-10-18 after RESEARCH_FINDINGS.md "更正與方法檢討".

Two state indicators, both observable in real time, no prediction:

  FUNDING  BTC perp funding, trailing 30-day mean, annualised
           (90 x 8h settlements x 3 x 365). History: the three directional
           sleeves (v7, BRK4H, long beta) had Sharpe >= 0.6 only in weeks
           with this above 10 %; ~0 or negative otherwise.
  BASIS    BTC quarterly futures, ln(mark / index) * 365 / days-to-expiry,
           contracts with 20..120 days left. History: entering cash-and-
           carry at >= 10 % annualised and holding to expiry paid ~+3 %
           net every time (2021 / 2023 / 2024 only).

Every run appends the values to data/forward/regime_log.csv. A Telegram
message is sent when either flag changes state (crosses 10 % up or down),
and a one-line status every Monday regardless. Nothing here trades or
touches any tracker.
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.notifier import send_telegram_msg  # noqa: E402

OUT_DIR = os.path.join(ROOT, 'data', 'forward')
LOG = os.path.join(OUT_DIR, 'regime_log.csv')
STATE = os.path.join(OUT_DIR, 'regime_state.json')
FAPI = 'https://fapi.binance.com/fapi/v1'
FUNDING_THRESHOLD = 0.10
BASIS_THRESHOLD = 0.10
DTE_MIN, DTE_MAX = 20, 120


def get(path, **params):
    r = requests.get(f'{FAPI}/{path}', params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def funding_30d():
    rows = get('fundingRate', symbol='BTCUSDT', limit=100)[-90:]
    rates = [float(x['fundingRate']) for x in rows]
    ann30 = sum(rates) / len(rates) * 3 * 365
    ann7 = sum(rates[-21:]) / 21 * 3 * 365
    return ann30, ann7, len(rates)


def quarterly_basis(now):
    delivery = {s['symbol']: s['deliveryDate'] for s in get('exchangeInfo')['symbols']
                if s['symbol'].startswith('BTCUSDT_') and s['status'] == 'TRADING'}
    out = []
    for p in get('premiumIndex'):
        if p['symbol'] not in delivery:
            continue
        dte = (datetime.fromtimestamp(delivery[p['symbol']] / 1000, tz=timezone.utc) - now).total_seconds() / 86400
        basis = math.log(float(p['markPrice']) / float(p['indexPrice']))
        out.append(dict(symbol=p['symbol'], dte=dte, basis=basis, ann=basis * 365 / dte if dte > 0 else float('nan'),
                        mark=float(p['markPrice']), index=float(p['indexPrice'])))
    return sorted(out, key=lambda x: x['dte'])


def load_state():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    now = datetime.now(timezone.utc)
    ann30, ann7, n = funding_30d()
    contracts = quarterly_basis(now)
    eligible = [c for c in contracts if DTE_MIN <= c['dte'] <= DTE_MAX]
    best = max(eligible, key=lambda c: c['ann']) if eligible else None
    best_ann = best['ann'] if best else float('nan')

    funding_on = ann30 >= FUNDING_THRESHOLD
    basis_on = bool(best) and best_ann >= BASIS_THRESHOLD

    os.makedirs(OUT_DIR, exist_ok=True)
    new_file = not os.path.exists(LOG)
    with open(LOG, 'a', encoding='utf-8') as f:
        if new_file:
            f.write('timestamp_utc,funding_ann30,funding_ann7,basis_best_symbol,basis_best_dte,basis_best_ann,contracts\n')
        detail = '|'.join('{}:{:.1f}%@{:.0f}d'.format(c['symbol'][-6:], c['ann'] * 100, c['dte']) for c in contracts)
        f.write('{},{:.5f},{:.5f},{},{:.1f},{:.5f},{}\n'.format(
            now.strftime('%Y-%m-%d %H:%M'), ann30, ann7, best['symbol'] if best else '',
            best['dte'] if best else float('nan'), best_ann, detail))

    prev = load_state()
    changed = (prev.get('funding_on') is not None and prev.get('funding_on') != funding_on) or \
              (prev.get('basis_on') is not None and prev.get('basis_on') != basis_on)
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(dict(funding_on=funding_on, basis_on=basis_on, funding_ann30=ann30, basis_best_ann=best_ann,
                       updated_utc=now.isoformat()), f, ensure_ascii=False, indent=1)

    local = (now + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
    lines = [f"【市況監控 {local}】",
             f"BTC 資金費率 30日年化 {ann30*100:+.1f}%（7日 {ann7*100:+.1f}%）→ "
             + ("狂熱：方向性策略歷史上有優勢" if funding_on else "平靜：方向性策略歷史上無優勢"),
             "季度基差年化：" + ("、".join(f"{c['symbol'][-6:]} {c['ann']*100:+.1f}%（{c['dte']:.0f}天）" for c in contracts) or "無合約"),
             ("★ 基差 ≥10%：現貨＋季度空單持有到期的條件成立" if basis_on else "基差 <10%：現貨套利條件未成立")]
    if changed:
        lines.insert(1, "⚠ 狀態改變：" + ("資金費率" if prev.get('funding_on') != funding_on else "") +
                     (" 基差" if prev.get('basis_on') != basis_on else ""))
    msg = '\n'.join(lines)
    print(msg)
    if changed or now.weekday() == 0 or '--send' in sys.argv:
        send_telegram_msg(msg)


if __name__ == '__main__':
    main()
