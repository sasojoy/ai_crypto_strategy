"""
Reusable health-check template (added 2026-09-25 at the user's request --
"把這個檢查流程做一個模板以後可以快速套用"): one script that answers
"is everything running normally, and does local state match the real
exchange" in one pass. Read-only throughout -- never places an order,
never modifies state.

Covers three things, in order (cheap/broad first, expensive/narrow only
if something looks off -- same "lightweight first pass" principle used
elsewhere in this project):
  1. Scheduled task health (all PaperTrading-*/LiveTrading-* tasks):
     LastTaskResult, staleness relative to each task's own interval.
  2. live_v7: full reconciliation between local state
     (state/live_v7_state.json) and the REAL testnet exchange (positions,
     SL/TP conditional orders, balance) -- the exact checks this session
     has been doing by hand via one-off `python -c` commands, several
     times, now consolidated into one script instead of re-deriving it
     from scratch each time.
  3. Paper monitors (v1/v7/v8): quick sanity summary (open positions,
     cumulative P&L, closed-trade count) -- not a full audit, just
     "does this look like a plausible number", matching this project's
     established "lightweight first pass, go deep only if something
     looks wrong" convention for paper-monitor checks.

Run: ../venv/Scripts/python.exe health_check.py
Exit code is 0 if nothing looked wrong, 1 if any check flagged something
(so this can also be used as a quick yes/no gate, e.g. before deciding
whether to dig further).
"""
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from binance_client import make_exchange, get_open_position, fetch_open_conditional_orders

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PAPER_STATE_DIR = os.path.join(os.path.dirname(THIS_DIR), 'paper_trading', 'state')
LIVE_STATE_DIR = os.path.join(THIS_DIR, 'state')
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NEAR/USDT', 'AVAX/USDT']

# name -> expected interval in minutes -- mirrors paper_trading/watchdog.py's TASKS dict;
# kept as a separate copy deliberately (this script doesn't import watchdog.py, since watchdog's
# job is "silently auto-heal known issues", this one's job is "always print a full status report").
TASKS = {
    'PaperTrading-MomentumV1': 60,
    'PaperTrading-MomentumV7': 5,
    'PaperTrading-MomentumV8': 60,
    'PaperTrading-Funding': 60,
    'PaperTrading-ThresholdReport': 60,
    'PaperTrading-Watchdog': 15,
    'LiveTrading-V7Testnet': 1,
}


def run_ps(cmd):
    result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd],
                             capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def check_scheduled_tasks():
    print(f"{'='*78}\n1. 排程任務健康狀態\n{'='*78}")
    ok = True
    names = ",".join(f"'{n}'" for n in TASKS)
    out = run_ps(
        f"Get-ScheduledTask -TaskName {names} -ErrorAction SilentlyContinue | ForEach-Object {{ "
        f"$i = $_ | Get-ScheduledTaskInfo; "
        f"[PSCustomObject]@{{ Name=$_.TaskName; State=$_.State.ToString(); "
        f"LastResult=$i.LastTaskResult; LastRun=$i.LastRunTime.ToString('o') }} "
        f"}} | ConvertTo-Json -Compress"
    )
    try:
        rows = json.loads(out)
        if isinstance(rows, dict):
            rows = [rows]
    except json.JSONDecodeError:
        print("  ⚠️ 無法讀取排程任務資訊（PowerShell查詢失敗）")
        return False

    found_names = {r['Name'] for r in rows}
    for name, interval_min in TASKS.items():
        if name not in found_names:
            print(f"  ❓ {name}：找不到這個排程任務")
            ok = False
    for r in rows:
        name, state, result = r['Name'], r['State'], r['LastResult']
        if state == 'Disabled':
            print(f"  ⏸️  {name}：Disabled（暫停中，非異常）")
            continue
        flags = []
        if result not in (0, 267009, 267011):  # 0=success, running, has-not-run-yet
            flags.append(f"上次執行結果碼異常({result})")
            ok = False
        last_run = r.get('LastRun')
        # PowerShell's sentinel "never run yet" timestamp starts with 1999 or 0001 (same known
        # edge case watchdog.py already handles) -- skip staleness entirely for those, a real
        # multi-decade "age" would otherwise trip a false alarm.
        if last_run and not last_run.startswith('1999') and not last_run.startswith('0001'):
            try:
                age_min = (datetime.now().astimezone() - datetime.fromisoformat(last_run)).total_seconds() / 60
                interval = TASKS.get(name, 60)
                if age_min > interval * 3:
                    flags.append(f"已經{age_min:.0f}分鐘沒執行（預期每{interval}分鐘）")
                    ok = False
            except Exception:
                pass
        if flags:
            print(f"  ⚠️ {name}：{'；'.join(flags)}")
        else:
            print(f"  ✅ {name}：正常（State={state}）")
    return ok


def check_live_v7():
    print(f"\n{'='*78}\n2. live_v7 (testnet) 本機/交易所對帳\n{'='*78}")
    ok = True
    state_path = os.path.join(LIVE_STATE_DIR, 'live_v7_state.json')
    if not os.path.exists(state_path):
        print("  ⚠️ 找不到 live_v7_state.json")
        return False
    with open(state_path) as f:
        state = json.load(f)
    local_symbols = {p['symbol']: p for p in state.get('positions', [])}

    try:
        ex = make_exchange()
    except Exception as e:
        print(f"  ⚠️ 無法連線testnet：{e}")
        return False

    for s in SYMBOLS:
        real_pos = get_open_position(ex, s)
        orders = fetch_open_conditional_orders(ex, s)
        local = local_symbols.get(s)

        if real_pos is None and local is None:
            continue  # both agree: flat, nothing to report

        if real_pos is not None and local is None:
            print(f"  🚨 {s}：交易所有真實部位但本機state不知道（孤兒部位）！")
            ok = False
            continue
        if real_pos is None and local is not None:
            print(f"  🚨 {s}：本機記錄有持倉但交易所已經是空的（本機state未同步）！")
            ok = False
            continue

        # both have it -- check qty/price match and SL/TP order health. Collect ALL problems for
        # this symbol first, then print exactly one verdict line (a mismatch found above must
        # never be followed by a contradicting "✅ consistent" for the same symbol -- that
        # confusing double-print was itself a bug in an earlier version of this script, found
        # 2026-09-25 while using it for real).
        # Price comparisons use a RELATIVE tolerance (0.05%), not an absolute one -- the exchange
        # rounds SL/TP triggerPrice (and sometimes entryPrice) to its own tick size, which can
        # legitimately differ from the unrounded value this project stores locally by a fraction
        # of a percent. 0.05% is comfortably above ordinary tick-size rounding but well below the
        # ~0.3%+ gaps the real theoretical-vs-real-fill-price bugs this session found actually
        # produced -- found necessary 2026-09-25 after an absolute 1e-6 tolerance flagged normal
        # rounding as a false-positive mismatch.
        PRICE_TOL = 0.0005

        def price_close(a, b):
            return abs(a - b) <= PRICE_TOL * max(abs(a), abs(b), 1e-9)

        problems = []
        if abs(float(real_pos['contracts']) - local['qty']) >= 1e-9:
            problems.append(f"數量不符（本機{local['qty']} vs 交易所{real_pos['contracts']}）")
        if not price_close(float(real_pos['entryPrice']), local['entry_price']):
            problems.append(f"進場價不符（本機{local['entry_price']} vs 交易所{real_pos['entryPrice']}）")

        expected_order_ids = {str(local.get('sl_order_id')), str(local.get('tp_order_id'))}
        real_order_ids = {str(o['id']) for o in orders}
        if len(orders) != 2 or not expected_order_ids.issubset(real_order_ids):
            problems.append(f"SL/TP保護單數量或ID不符（交易所目前{len(orders)}張："
                             f"{[(o['type'], o['triggerPrice']) for o in orders]}）")
        else:
            for o in orders:
                is_sl = str(o['id']) == str(local.get('sl_order_id'))
                expected_price = local['sl_price'] if is_sl else local['tp_price']
                if not price_close(float(o['triggerPrice']), expected_price):
                    problems.append(f"{'SL' if is_sl else 'TP'}觸發價不符（本機{expected_price} vs "
                                     f"交易所{o['triggerPrice']}）")

        if problems:
            print(f"  ⚠️ {s}：{'；'.join(problems)}")
            ok = False
        else:
            print(f"  ✅ {s}：{real_pos['side']} {real_pos['contracts']} @ {real_pos['entryPrice']}，"
                  f"本機記錄一致，SL/TP兩張都在且價位正確")

    if not local_symbols and all(get_open_position(ex, s) is None for s in SYMBOLS):
        print("  ✅ 目前無任何持倉，本機與交易所皆為空倉")

    try:
        bal = ex.fetch_balance()['USDT']
        print(f"  帳戶權益: ${bal['total']:.2f}  可用: ${bal['free']:.2f}")
    except Exception as e:
        print(f"  ⚠️ 無法查詢帳戶餘額：{e}")
        ok = False

    return ok


def check_paper_monitors():
    print(f"\n{'='*78}\n3. 模擬盤現況（v1/v7/v8）\n{'='*78}")
    files = [
        ('v1整點版', 'momentum_state.json', 'open_positions'),
        ('v7提早進場+重倉版', 'momentum_v7_state.json', 'positions'),
        ('v8快停利版', 'momentum_v8_state.json', 'open_positions'),
    ]
    for label, fname, pos_key in files:
        path = os.path.join(PAPER_STATE_DIR, fname)
        if not os.path.exists(path):
            print(f"  ❓ {label}：找不到state檔案")
            continue
        with open(path) as f:
            d = json.load(f)
        n_open = len(d.get(pos_key, []))
        cum = d.get('cumulative_pnl_pct', 0)
        n_closed = d.get('n_closed', d.get('n_closed_legs', 0))
        print(f"  {label}：持倉{n_open}筆  累計損益{cum:+.2f}%（{n_closed}筆已平倉）")


def main():
    ok1 = check_scheduled_tasks()
    ok2 = check_live_v7()
    check_paper_monitors()  # informational only, doesn't affect exit code

    print(f"\n{'='*78}")
    if ok1 and ok2:
        print("✅ 全部檢查通過，沒有發現異常。")
        return 0
    else:
        print("⚠️ 有項目需要留意，請看上面標記的部分。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
