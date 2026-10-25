"""
LIVE EXECUTOR for H_K1 cross-sectional funding carry (RESEARCH_FINDINGS.md
"第三輪新方向 K", dev PASS 2026-10-25; 2026 holdout: Sharpe 1.20 but p=0.15,
below the pre-registered gate). The user chose a small-capital live
implementation ("小資金實作", 2026-10-25) knowing that.

RULE (frozen, identical to scripts/prereg_xs_funding.py; nothing here may
"improve" it):
  * Universe: the same 50 USDT perps the research used
    (scripts/fetch_holdout_2026.coins()), minus any no longer trading.
  * Reference time REF = the most recent Sunday 00:00 UTC. Score per coin =
    mean of the funding settlements in (REF - 7 days, REF]. (The backtest
    entered at the Sunday daily close = Monday 00:00 UTC using funding
    settled up to Sunday 00:00; this task runs Monday 08:05 Taipei =
    00:05 UTC, so the information set is the same.)
  * k = int(0.2 * n_eligible). LONG the k LOWEST scores, SHORT the k
    HIGHEST, weight 0.5/k of CAPITAL per leg (gross notional = CAPITAL).
  * Rebalance once per week to those targets with market orders; holds a
    week; no stops (the research rule has none -- the risk control is the
    small capital, 3x fixed leverage, and the circuit breaker below).

MODES (FUNDING_CARRY_MODE in .env; default 'dry'):
  dry   compute and log the weekly book, no exchange credentials needed,
        no orders. Every run still appends to state/funding_carry_book.csv,
        so dry runs double as a frozen forward track.
  live  real orders on Binance USDT-M MAINNET via
        binance_client.make_mainnet_exchange(). Also requires
        FUNDING_CARRY_CAPITAL_USDT in .env.

SAFETY
  * Refuses to trade unless the account is in one-way position mode, the
    equity is at least 50 % of CAPITAL (so effective leverage <= 2x), and
    the planned turnover is below 2.2x CAPITAL (a sanity bound; a normal
    week is far less).
  * Circuit breaker: if equity falls below 75 % of the equity recorded at
    the first live rebalance, everything is flattened, a STOP file is
    written and nothing trades again until a human deletes it.
  * STOP file (state/funding_carry_STOP): if present, flatten and exit.
  * Idempotent per week: a second run for the same REF only reconciles and
    reports (watchdog restarts or manual runs cannot double-trade).
  * `--close-all --yes` flattens everything; `--status` reports only.

RECORDS (live_trading/state/, gitignored)
  funding_carry_state.json   last REF, initial equity, current book
  funding_carry_book.csv     every week's scores/targets/fills/fees
  funding_carry_equity.csv   equity, funding and commission per run
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT)
sys.path.insert(0, THIS_DIR)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
load_dotenv(os.path.join(ROOT, '.env'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.notifier import send_telegram_msg  # noqa: E402
from fetch_holdout_2026 import coins as research_universe  # noqa: E402

MODE = os.getenv('FUNDING_CARRY_MODE', 'dry').strip().lower()
CAPITAL = float(os.getenv('FUNDING_CARRY_CAPITAL_USDT', '0') or 0)
LOOKBACK_DAYS, SIDE_FRACTION, TOP_FRACTION = 7, 0.5, 0.2
FIXED_LEVERAGE = 3
MIN_EQUITY_FRACTION, MAX_TURNOVER_MULT, BREAKER_FRACTION = 0.50, 2.2, 0.75
MIN_LEG_NOTIONAL = 10.0
FAPI = 'https://fapi.binance.com/fapi/v1'
STATE_DIR = os.path.join(THIS_DIR, 'state')
STATE_PATH = os.path.join(STATE_DIR, 'funding_carry_state.json')
BOOK_PATH = os.path.join(STATE_DIR, 'funding_carry_book.csv')
EQUITY_PATH = os.path.join(STATE_DIR, 'funding_carry_equity.csv')
STOP_PATH = os.path.join(STATE_DIR, 'funding_carry_STOP')
TAG = f'[{MODE.upper()}-carry]'


# ----------------------------------------------------------------- helpers
def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def last_sunday_00(now):
    d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def public(path, **params):
    r = requests.get(f'{FAPI}/{path}', params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {'last_ref': None, 'initial_equity': None, 'book': {}}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def append_csv(path, row, columns):
    os.makedirs(STATE_DIR, exist_ok=True)
    new = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, '') for c in columns})


BOOK_COLUMNS = ['ref', 'run_utc', 'mode', 'symbol', 'score_7d_mean', 'n_settlements', 'rank', 'side', 'weight',
                'target_notional', 'mark_price', 'target_qty', 'prev_qty', 'delta_qty', 'filled_qty', 'avg_fill', 'fee_usdt', 'note']
EQUITY_COLUMNS = ['run_utc', 'ref', 'mode', 'equity', 'available', 'unrealized', 'funding_week', 'commission_week', 'n_positions', 'note']


def notify(msg):
    print(msg)
    try:
        send_telegram_msg(msg)
    except Exception as e:  # noqa: BLE001
        print(f'telegram failed: {e}')


# ------------------------------------------------------------ the signal
def tradable_universe():
    info = {s['symbol']: s for s in public('exchangeInfo')['symbols']}
    out = []
    for base in research_universe():
        sid = f'{base}USDT'
        s = info.get(sid)
        if s and s['status'] == 'TRADING' and s.get('contractType') == 'PERPETUAL':
            out.append(base)
        else:
            print(f'  drop {sid}: {"missing" if not s else s["status"]}')
    return out


def funding_scores(bases, ref):
    start, end = ref - timedelta(days=LOOKBACK_DAYS), ref
    ms = lambda d: int(d.replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    scores = {}
    for b in bases:
        rows = public('fundingRate', symbol=f'{b}USDT', startTime=ms(start) + 1, endTime=ms(end), limit=100)
        rates = [float(x['fundingRate']) for x in rows
                 if start < datetime.fromtimestamp(x['fundingTime'] / 1000, timezone.utc).replace(tzinfo=None) <= end]
        if rates:
            scores[b] = (sum(rates) / len(rates), len(rates))
        time.sleep(0.05)
    return scores


def target_book(scores):
    """Returns {base: (weight, rank, side)} -- long the lowest 20 %, short the highest 20 %."""
    order = sorted(scores, key=lambda b: scores[b][0])  # ascending funding
    k = max(1, int(len(order) * TOP_FRACTION))
    book = {}
    for i, b in enumerate(order):
        if i < k:
            book[b] = (SIDE_FRACTION / k, i + 1, 'long')
        elif i >= len(order) - k:
            book[b] = (-SIDE_FRACTION / k, i + 1, 'short')
    return book, k


# --------------------------------------------------------------- exchange
def ccxt_symbol(base):
    return f'{base}/USDT:USDT'


def account_snapshot(ex):
    bal = ex.fetch_balance()
    info = bal.get('info', {})
    equity = float(info.get('totalMarginBalance') or bal['USDT'].get('total') or 0)
    available = float(info.get('availableBalance') or bal['USDT'].get('free') or 0)
    unreal = float(info.get('totalUnrealizedProfit') or 0)
    return equity, available, unreal


def current_positions(ex, bases):
    pos = {}
    for p in ex.fetch_positions([ccxt_symbol(b) for b in bases]):
        q = float(p.get('contracts') or 0)
        if q:
            side = (p.get('side') or '').lower()
            if side == 'short':
                q = -q
            pos[p['symbol'].split('/')[0]] = q
    return pos


def ensure_one_way(ex):
    r = ex.fapiPrivateGetPositionSideDual()
    if str(r.get('dualSidePosition')).lower() == 'true':
        raise RuntimeError('account is in HEDGE position mode; switch to one-way before running')


def income_since(ex, since_ms, kind):
    tot, start = 0.0, since_ms
    while True:
        rows = ex.fapiPrivateGetIncome({'incomeType': kind, 'startTime': start, 'limit': 1000})
        tot += sum(float(r['income']) for r in rows)
        if len(rows) < 1000:
            return tot
        start = int(rows[-1]['time']) + 1


def flatten_all(ex, bases, reason):
    pos = current_positions(ex, bases)
    for b, q in pos.items():
        ex.create_order(ccxt_symbol(b), 'market', 'sell' if q > 0 else 'buy', abs(q), None, params={'reduceOnly': True})
    notify(f'{TAG} FLATTENED {len(pos)} positions: {reason}')
    return pos


def fills_for(ex, base, order_id):
    for _ in range(4):
        tr = [t for t in ex.fetch_my_trades(ccxt_symbol(base), limit=20) if str(t['order']) == str(order_id)]
        if tr:
            q = sum(float(t['amount']) for t in tr)
            px = sum(float(t['price']) * float(t['amount']) for t in tr) / q
            fee = sum(float(t['fee']['cost']) for t in tr if t.get('fee'))
            return q, px, fee
        time.sleep(1.5)
    return None, None, None


# ------------------------------------------------------------------- main
def rebalance(args):
    now = utcnow()
    ref = last_sunday_00(now)
    state = load_state()
    live = MODE == 'live' and not args.dry
    print(f'{TAG} run {now:%Y-%m-%d %H:%M} UTC  ref={ref:%Y-%m-%d}  capital={CAPITAL:.0f}  live={live}')

    bases = tradable_universe()
    scores = funding_scores(bases, ref)
    book, k = target_book(scores)
    marks = {p['symbol'][:-4]: float(p['markPrice']) for p in public('premiumIndex') if p['symbol'].endswith('USDT')}
    print(f'  eligible={len(scores)}  k={k} per side')

    ex = None
    equity = available = unreal = 0.0
    prev = {}
    if live:
        from binance_client import make_mainnet_exchange
        ex = make_mainnet_exchange()
        ensure_one_way(ex)
        equity, available, unreal = account_snapshot(ex)
        prev = current_positions(ex, bases + list(state.get('book', {}).keys()))
        if os.path.exists(STOP_PATH):
            flatten_all(ex, bases, 'STOP file present')
            return
        if state.get('initial_equity') and equity < BREAKER_FRACTION * state['initial_equity']:
            flatten_all(ex, bases, f'circuit breaker: equity {equity:.2f} < {BREAKER_FRACTION:.0%} of initial {state["initial_equity"]:.2f}')
            open(STOP_PATH, 'w').write(f'breaker {now}\n')
            return
        if CAPITAL <= 0:
            raise RuntimeError('FUNDING_CARRY_CAPITAL_USDT not set')
        if equity < MIN_EQUITY_FRACTION * CAPITAL:
            notify(f'{TAG} ABORT: equity {equity:.2f} < {MIN_EQUITY_FRACTION:.0%} of capital {CAPITAL:.0f}')
            return

    already = state.get('last_ref') == ref.strftime('%Y-%m-%d')
    if already and live:
        print('  already rebalanced for this ref -> report only')

    # plan
    plan = []
    turnover = 0.0
    for b in sorted(set(list(book) + list(prev))):
        w, rank, side = book.get(b, (0.0, None, 'flat'))
        tgt_notional = w * CAPITAL
        mp = marks.get(b)
        tq = 0.0
        if mp and tgt_notional:
            tq = tgt_notional / mp
            if ex is not None:
                tq = float(ex.amount_to_precision(ccxt_symbol(b), abs(tq))) * (1 if tq > 0 else -1)
        pq = prev.get(b, 0.0)
        dq = tq - pq
        note = ''
        if mp and abs(dq) * mp < MIN_LEG_NOTIONAL and tq != 0:
            dq, note = 0.0, 'delta below min notional, kept'
        if mp and abs(tgt_notional) and abs(tgt_notional) < MIN_LEG_NOTIONAL:
            dq, tq, note = -pq, 0.0, 'target leg below min notional, skipped'
        turnover += abs(dq) * (mp or 0)
        plan.append(dict(symbol=b, score=scores.get(b, (None, 0))[0], n=scores.get(b, (None, 0))[1], rank=rank, side=side,
                         weight=w, tgt_notional=tgt_notional, mark=mp, tq=tq, pq=pq, dq=dq, note=note))

    if live and not already:
        if turnover > MAX_TURNOVER_MULT * CAPITAL:
            notify(f'{TAG} ABORT: planned turnover {turnover:.0f} > {MAX_TURNOVER_MULT}x capital')
            return
        # closes / reductions first, then opens
        for phase in ('reduce', 'open'):
            for p in plan:
                b, dq, pq, tq = p['symbol'], p['dq'], p['pq'], p['tq']
                if dq == 0:
                    continue
                reducing = pq != 0 and (tq == 0 or (pq > 0) == (dq < 0)) and abs(dq) <= abs(pq)
                if (phase == 'reduce') != reducing:
                    continue
                try:
                    set_leverage_quiet(ex, b)
                    params = {'reduceOnly': True} if reducing else {}
                    o = ex.create_order(ccxt_symbol(b), 'market', 'buy' if dq > 0 else 'sell', abs(dq), None, params=params)
                    fq, fpx, fee = fills_for(ex, b, o['id'])
                    p.update(filled=fq, avg=fpx, fee=fee)
                except Exception as e:  # noqa: BLE001
                    p['note'] = f'ORDER FAILED: {e}'[:200]
                    notify(f'{TAG} order failed {b} dq={dq}: {e}')
        if state.get('initial_equity') is None:
            state['initial_equity'] = equity
        state['last_ref'] = ref.strftime('%Y-%m-%d')
        state['book'] = {p['symbol']: p['tq'] for p in plan if p['tq']}
        save_state(state)
    elif not live:
        state['last_ref'] = ref.strftime('%Y-%m-%d')
        state['book'] = {p['symbol']: p['weight'] for p in plan if p['weight']}
        save_state(state)

    # records
    for p in plan:
        if p['weight'] == 0 and p['pq'] == 0:
            continue
        append_csv(BOOK_PATH, dict(ref=ref.strftime('%Y-%m-%d'), run_utc=now.strftime('%Y-%m-%d %H:%M'), mode='live' if live else 'dry',
                                   symbol=p['symbol'], score_7d_mean=p['score'], n_settlements=p['n'], rank=p['rank'], side=p['side'],
                                   weight=round(p['weight'], 4), target_notional=round(p['tgt_notional'], 2), mark_price=p['mark'],
                                   target_qty=p['tq'], prev_qty=p['pq'], delta_qty=p['dq'], filled_qty=p.get('filled', ''),
                                   avg_fill=p.get('avg', ''), fee_usdt=p.get('fee', ''), note=p['note']), BOOK_COLUMNS)
    funding_week = comm_week = ''
    if live:
        since = int((now - timedelta(days=7)).timestamp() * 1000)
        try:
            funding_week = round(income_since(ex, since, 'FUNDING_FEE'), 4)
            comm_week = round(income_since(ex, since, 'COMMISSION'), 4)
        except Exception as e:  # noqa: BLE001
            print(f'income lookup failed: {e}')
        equity, available, unreal = account_snapshot(ex)
    append_csv(EQUITY_PATH, dict(run_utc=now.strftime('%Y-%m-%d %H:%M'), ref=ref.strftime('%Y-%m-%d'), mode='live' if live else 'dry',
                                 equity=equity, available=available, unrealized=unreal, funding_week=funding_week, commission_week=comm_week,
                                 n_positions=sum(1 for p in plan if p['tq']) if live else sum(1 for p in plan if p['weight']),
                                 note='report only' if already and live else ''), EQUITY_COLUMNS)

    longs = [p for p in plan if p['side'] == 'long']
    shorts = [p for p in plan if p['side'] == 'short']
    fmt = lambda ps: ', '.join(f"{p['symbol']} {p['score']*100:+.3f}%" for p in ps)  # noqa: E731
    msg = (f"{TAG} 週換倉 ref {ref:%m-%d}  本金 {CAPITAL:.0f} USDT  每邊 {k} 幣，每幣 {SIDE_FRACTION/k*100:.1f}%\n"
           f"多（費率最低）: {fmt(longs)}\n空（費率最高）: {fmt(shorts)}\n"
           f"預計換手 {turnover:.0f} USDT")
    if live:
        failed = [p['symbol'] for p in plan if p['note'].startswith('ORDER FAILED')]
        msg += (f"\n權益 {equity:.2f}（可用 {available:.2f}，未實現 {unreal:+.2f}）"
                f"  本週資金費率 {funding_week}  手續費 {comm_week}" + (f"\n失敗: {failed}" if failed else ''))
    notify(msg)


def set_leverage_quiet(ex, base):
    try:
        ex.set_leverage(FIXED_LEVERAGE, ccxt_symbol(base))
    except Exception:  # noqa: BLE001
        pass


def status():
    from binance_client import make_mainnet_exchange
    ex = make_mainnet_exchange()
    equity, available, unreal = account_snapshot(ex)
    pos = current_positions(ex, research_universe())
    print(f'equity={equity:.2f} available={available:.2f} unrealized={unreal:+.2f} positions={len(pos)}')
    for b, q in sorted(pos.items()):
        print(f'  {b:10s} {q:+.6f}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true', help='force dry run even if FUNDING_CARRY_MODE=live')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--close-all', action='store_true')
    ap.add_argument('--yes', action='store_true')
    args = ap.parse_args()
    if args.status:
        return status()
    if args.close_all:
        if not args.yes:
            raise SystemExit('add --yes to really flatten every position in the research universe')
        from binance_client import make_mainnet_exchange
        ex = make_mainnet_exchange()
        flatten_all(ex, research_universe(), 'manual --close-all')
        return
    try:
        rebalance(args)
    except Exception as e:  # noqa: BLE001
        notify(f'{TAG} RUN FAILED: {e}')
        raise


if __name__ == '__main__':
    main()
