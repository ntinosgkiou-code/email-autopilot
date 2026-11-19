# Email Autopilot: Windows setup. Run from the package folder:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Safe to run again any time (for example after you change the schedule in config.yaml).
param([ValidateSet('claude', 'codex')][string]$Agent, [switch]$ScheduleOnly)

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$env:Path"

function Write-Step($n, $t) { Write-Host "`n[$n/4] $t" -ForegroundColor Cyan }
function Confirm-Yes($q) { (Read-Host "$q [Y/n]") -notmatch '^(n|no)$' }

if (-not $ScheduleOnly) {
# 1. uv (runs the Python tools; it brings its own Python)
Write-Step 1 'Checking uv'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (-not (Confirm-Yes 'uv is not installed. Install it now from astral.sh (~20 MB)?')) { throw 'uv is required.' }
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv --version

# 2. Which AI agent runs the routines
Write-Step 2 'Choosing the AI agent'
$hasClaude = [bool](Get-Command claude -ErrorAction SilentlyContinue)
$hasCodex = [bool](Get-Command codex -ErrorAction SilentlyContinue)
if (-not $Agent) {
    if ($hasClaude -and $hasCodex) { $Agent = if ((Read-Host 'Use (1) Claude Code or (2) Codex? [1/2]') -eq '2') { 'codex' } else { 'claude' } }
    elseif ($hasClaude) { $Agent = 'claude' }
    elseif ($hasCodex) { $Agent = 'codex' }
    else {
        Write-Host 'No AI agent found. Claude Code needs a paid Claude plan (Pro or higher).'
        if (-not (Confirm-Yes 'Install Claude Code now?')) { throw 'Install Claude Code or Codex, then run this again.' }
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw 'Claude Code did not install. Close this window and run START.bat again.' }
        $Agent = 'claude'
        Write-Host 'Claude Code installed. Sign in to it from the dashboard checklist.' -ForegroundColor Green
    }
}
New-Item -ItemType Directory -Force (Join-Path $Root 'data') | Out-Null
Set-Content -Path (Join-Path $Root 'data\.agent') -Value $Agent -Encoding ascii
Write-Host "Agent: $Agent"
}  # end of: if (-not $ScheduleOnly)

# 3. Schedule (Windows Task Scheduler)
Write-Step 3 'Scheduling'
$sched = (uv run --quiet tools/guard.py schedule) | Out-String | ConvertFrom-Json
$dayMap = @{ Mon = 'Monday'; Tue = 'Tuesday'; Wed = 'Wednesday'; Thu = 'Thursday'; Fri = 'Friday'; Sat = 'Saturday'; Sun = 'Sunday' }
$workDays = @($sched.work_days | ForEach-Object { $dayMap[$_] })
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 90) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$runPs1 = Join-Path $Root 'scripts\run.ps1'

function Register-Routine($name, $task, $days, $times) {
    $act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runPs1`" -Task $task" -WorkingDirectory $Root
    $trig = @($times | ForEach-Object { New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $_ })
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $name -TaskPath '\EmailAutopilot\' -Action $act -Trigger $trig -Settings $settings -Description "Email Autopilot: $task" | Out-Null
    Write-Host ("  {0,-10} {1} at {2}" -f $task, ($days -join ','), ($times -join ', '))
}
Register-Routine 'Outreach' 'outreach' $workDays @($sched.outreach_runs)
Register-Routine 'Inbox' 'inbox' $workDays @($sched.inbox_run)

# 4. Done
Write-Step 4 'Done'
uv run --quiet tools/guard.py report | Out-Null
Write-Host @"

Email Autopilot is scheduled. Your PC must be on, and you must be logged in to Windows.
It starts in TEST mode: nothing is sent until you switch to live mode in the dashboard (START.bat).
"@ -ForegroundColor Green
