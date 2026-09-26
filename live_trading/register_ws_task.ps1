# Registers LiveTrading-WsEntryDetector as an "At startup" Task Scheduler task
# (2026-09-26). Requires an elevated (Administrator) PowerShell -- a boot
# trigger can't be registered as a regular user. Run this file directly
# (e.g. right-click -> "Run with PowerShell" in an elevated context, or
# `& .\register_ws_task.ps1` from an Administrator PowerShell already cd'd
# here) rather than copy-pasting lines individually, since $repo/$pythonw
# need to survive from one line to the next in the SAME session.

$repo = $PSScriptRoot
$pythonw = (Resolve-Path (Join-Path $repo "..\venv\Scripts\pythonw.exe")).Path

Write-Host "repo    = $repo"
Write-Host "pythonw = $pythonw"

$wsSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$wsAction = New-ScheduledTaskAction -Execute $pythonw -Argument "ws_entry_detector.py" -WorkingDirectory $repo
$wsTrigger = New-ScheduledTaskTrigger -AtStartup

Register-ScheduledTask -TaskName "LiveTrading-WsEntryDetector" -Action $wsAction -Trigger $wsTrigger -Settings $wsSettings -Description "Always-on real-time WebSocket entry-signal detector for v7 (2026-09-26)."

Start-ScheduledTask -TaskName "LiveTrading-WsEntryDetector"

Start-Sleep -Seconds 3
Get-ScheduledTask -TaskName "LiveTrading-WsEntryDetector" | Get-ScheduledTaskInfo
