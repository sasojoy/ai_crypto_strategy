"""
Watchdog for the PaperTrading-* Windows Scheduled Tasks (momentum v1-v8,
funding, threshold_report). Runs every 15 minutes. Read-only towards the
monitors themselves (never opens/closes positions, never touches state.json
trade data) -- it only inspects/repairs the Task Scheduler registrations.

Checks per task:
  1. LastTaskResult -- nonzero (other than "has not run yet") means the
     script itself errored out. Alert only (auto-restarting a script that's
     actively erroring would likely just error again and spam Telegram).
  2. Staleness -- LastRunTime older than STALE_MULTIPLIER x its expected
     interval means it silently failed to fire. Auto-heals the ONE root
     cause already hit in production (2026-09-09): DisallowStartIfOnBatteries
     / StopIfGoingOnBatteries left True blocks a trigger with no error
     recorded anywhere. If found True, resets it, then force-starts the
     task immediately via Start-ScheduledTask so it catches up right away
     instead of waiting for its next natural trigger.
  3. Missing task -- alerts if a task was deleted/unregistered.
  4. Stuck 'Running' state well past its interval -- alerted only, never
     auto-killed (killing a script mid-write is a judgment call for a human,
     not something to automate).
  5. A task in the 'Disabled' state (e.g. v2/v4/v5, paused 2026-09-19 in
     favor of v7/v8) is skipped entirely -- no staleness alert, no
     force-run. Its LastRunTime only gets older forever once disabled,
     which would otherwise look identical to a silently-failed trigger.

ALSO checks LiveTrading-WsEntryDetector (2026-09-26), the always-on
WebSocket real-time signal daemon (live_trading/ws_entry_detector.py) --
per the user's explicit choice ("簡單版：仍然用Task Scheduler，但設成開機就
啟動+別的看守程式定期檢查活著沒、死掉就重啟"), it's registered with an
"At startup" trigger rather than an interval, so the staleness logic above
(which compares LastRunTime against an expected interval) doesn't apply to
it. Instead its liveness is judged by a heartbeat FILE the daemon writes
every ~20s (state/ws_detector_heartbeat.txt) -- if that file is missing or
older than WS_HEARTBEAT_STALE_MINUTES, the daemon is presumed dead or
hung and is forcibly stopped-then-started (Stop- before Start- specifically
to also catch "hung but the process is technically still alive", which
`-MultipleInstances IgnoreNew` would otherwise block a plain restart on).

Only sends a Telegram message when it finds and/or heals something -- silent
on a clean run, consistent with keeping notification volume low.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.notifier import send_telegram_msg

WS_DETECTOR_TASK = 'LiveTrading-WsEntryDetector'
WS_HEARTBEAT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  'live_trading', 'state', 'ws_detector_heartbeat.txt')
WS_HEARTBEAT_STALE_MINUTES = 3

# task name -> expected interval in minutes (matches the Register-ScheduledTask
# calls in README.md's Scheduling section)
TASKS = {
    'PaperTrading-MomentumV1': 60,
    'PaperTrading-MomentumV2': 5,
    'PaperTrading-MomentumV3': 5,
    'PaperTrading-MomentumV4': 60,
    'PaperTrading-MomentumV5': 60,
    'PaperTrading-MomentumV6': 60,
    'PaperTrading-MomentumV7': 5,
    'PaperTrading-MomentumV8': 60,
    'PaperTrading-Funding': 60,
    'PaperTrading-ThresholdReport': 60,
    'LiveTrading-V7Testnet': 1,  # 2026-09-22: shortened from 5min to 1min to cut the signal-to-
                                 # execution slippage window (real (testnet) order-execution loop
                                 # -- a stalled run here means open positions aren't being
                                 # monitored for SL/TP reconciliation, so this one matters even
                                 # more than the paper monitors do).
}
STALE_MULTIPLIER = 2.5
TASK_HAS_NOT_RUN = 267011  # 0x41303, SCHED_S_TASK_HAS_NOT_RUN -- not an error


def run_ps(cmd, timeout=30):
    result = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip()


def get_task_info(name):
    out = run_ps(
        f"$t = Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue; "
        f"if (-not $t) {{ Write-Output '{{}}'; exit }}; "
        f"$i = $t | Get-ScheduledTaskInfo; "
        f"$lr = if ($i.LastRunTime) {{ $i.LastRunTime.ToString('o') }} else {{ $null }}; "
        f"[PSCustomObject]@{{ "
        f"State = $t.State.ToString(); "
        f"DisallowStartIfOnBatteries = [bool]$t.Settings.DisallowStartIfOnBatteries; "
        f"StopIfGoingOnBatteries = [bool]$t.Settings.StopIfGoingOnBatteries; "
        f"LastRunTime = $lr; "
        f"LastTaskResult = [int]$i.LastTaskResult "
        f"}} | ConvertTo-Json -Compress"
    )
    try:
        return json.loads(out) if out else {}
    except json.JSONDecodeError:
        return {}


def fix_battery_settings(name):
    run_ps(
        f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        f"-MultipleInstances IgnoreNew; Set-ScheduledTask -TaskName '{name}' -Settings $s | Out-Null"
    )


def force_run(name):
    run_ps(f"Start-ScheduledTask -TaskName '{name}'")


def restart_task(name):
    # Stop first (not just Start) so this also recovers a HUNG-but-still-alive process --
    # `-MultipleInstances IgnoreNew` on the task's own settings would otherwise silently no-op
    # a plain Start-ScheduledTask against a process Task Scheduler still considers "Running".
    run_ps(f"Stop-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue; "
           f"Start-Sleep -Seconds 1; Start-ScheduledTask -TaskName '{name}'")


def check_ws_detector():
    """live_trading/ws_entry_detector.py runs on an "At startup" trigger,
    not an interval, so it needs a different liveness check than every
    other task here -- see this module's docstring."""
    info = get_task_info(WS_DETECTOR_TASK)
    if not info:
        return [f"❓ {WS_DETECTOR_TASK}：排程工作不存在（可能被移除或改名）"]
    if info.get('State') == 'Disabled':
        return []

    age_min = None
    if os.path.exists(WS_HEARTBEAT_PATH):
        try:
            with open(WS_HEARTBEAT_PATH) as f:
                last_beat = datetime.fromisoformat(f.read().strip())
            age_min = (datetime.utcnow() - last_beat).total_seconds() / 60.0
        except (ValueError, OSError):
            age_min = None  # unparseable/unreadable -- treat the same as "no heartbeat yet"

    if age_min is None or age_min > WS_HEARTBEAT_STALE_MINUTES:
        restart_task(WS_DETECTOR_TASK)
        detail = "從未寫過心跳檔" if age_min is None else f"心跳已超過 {age_min:.1f} 分鐘沒更新"
        return [f"🔧 {WS_DETECTOR_TASK}：{detail}（懷疑已死掉或卡住），已強制重啟"]
    return []


def main():
    now = datetime.now().astimezone()
    reports = []

    for name, interval_min in TASKS.items():
        info = get_task_info(name)
        if not info:
            reports.append(f"❓ {name}：排程工作不存在（可能被移除或改名）")
            continue

        if info.get('State') == 'Disabled':
            continue  # intentionally paused (e.g. v2/v4/v5 on 2026-09-19) -- not a failure

        healed = []
        if info.get('DisallowStartIfOnBatteries') or info.get('StopIfGoingOnBatteries'):
            fix_battery_settings(name)
            healed.append("重設電池限制設定（改為允許用電池執行）")

        last_run_iso = info.get('LastRunTime')
        result_code = info.get('LastTaskResult')
        state = info.get('State')

        stale = False
        age_min = None
        # A task that has genuinely never fired yet (freshly registered) reports
        # LastTaskResult == TASK_HAS_NOT_RUN and a sentinel LastRunTime (Task
        # Scheduler's classic ~1899/1999 "never run" date, not null) -- treating
        # that as a real timestamp would compute a bogus multi-decade "age" and
        # wrongly fire the staleness alert/force-run. Skip staleness entirely here;
        # it's an expected, harmless transient state that resolves at the first
        # natural trigger.
        if last_run_iso and result_code != TASK_HAS_NOT_RUN:
            last_run = datetime.fromisoformat(last_run_iso)
            age_min = (now - last_run).total_seconds() / 60.0
            stale = age_min > interval_min * STALE_MULTIPLIER

        if stale and state != 'Running':
            force_run(name)
            healed.append(f"已超過 {age_min:.0f} 分鐘沒執行（預期每 {interval_min} 分鐘一次），已立即強制觸發一次補跑")

        errored = result_code not in (0, TASK_HAS_NOT_RUN)

        if state == 'Running' and age_min is not None and age_min > interval_min * STALE_MULTIPLIER:
            reports.append(
                f"⚠️ {name}：狀態顯示執行中已超過 {age_min:.0f} 分鐘（預期每 {interval_min} 分鐘一次），"
                f"疑似卡住，需要你手動確認是否要中止重啟（不會自動關閉執行中的程序）"
            )
        elif errored:
            reports.append(f"❌ {name}：上次執行回傳錯誤代碼 {result_code}")

        if healed:
            reports.append(f"\U0001F527 {name}：" + "；".join(healed))

    reports.extend(check_ws_detector())

    if not reports:
        return  # everything healthy, stay silent

    msg = "\U0001F6A8 【看門狗】偵測到排程異常\n\n" + "\n".join(reports)
    print(msg)
    send_telegram_msg(msg)


if __name__ == "__main__":
    main()
