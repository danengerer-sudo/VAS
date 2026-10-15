<#
install.ps1 -- one-shot setup of the render agent on a Windows 11 mini PC.

Run in an *elevated* PowerShell (right-click > Run as administrator):

    Set-ExecutionPolicy -Scope Process Bypass -Force
    irm https://raw.githubusercontent.com/danengerer-sudo/VAS/claude/low-poly-helicopter-glb-d0l1zs/freemarket_defense/renderfarm/install.ps1 -OutFile install.ps1
    .\install.ps1

or, if the repo is already cloned:   powershell -ExecutionPolicy Bypass -File install.ps1

What it does:
  1. creates C:\renderfarm and shallow-clones the repo (--depth 1 --filter=blob:none, the repo
     contains large library thumbnails that the agent does not need)
  2. writes freemarket_defense\renderfarm\config.json from prompts
  3. registers a Task Scheduler task "RenderfarmAgent" that starts start_agent.bat at logon,
     restarts it on failure and never stops it for running long
  4. sets the power plan so the PC never sleeps/hibernates while plugged in
  5. optionally runs the benchmark
Everything is idempotent: re-running updates config / the task.
#>
[CmdletBinding()]
param(
    [string]$Root = "C:\renderfarm",
    [string]$RepoUrl = "https://github.com/danengerer-sudo/VAS",
    [string]$Branch = "",
    [string]$Worker = "",
    [string]$BlenderExe = "",
    [string]$RcloneRemote = "",
    [string]$BenchUrl = "",
    [switch]$NoTask,
    [switch]$NoPower,
    [switch]$RunBench,
    [switch]$Quiet
)
$ErrorActionPreference = "Stop"

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "MISSING: $cmd  -> $hint" -ForegroundColor Red
        return $false
    }
    return $true
}
function Ask($prompt, $default) {
    if ($Quiet) { Write-Host "$prompt -> $default"; return $default }
    $v = Read-Host "$prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($v)) { return $default }
    return $v
}

Write-Host "== renderfarm agent installer ==" -ForegroundColor Cyan

# --- 0. prerequisites -------------------------------------------------------------------------
$ok = $true
$ok = (Need "git"    "install Git for Windows: winget install --id Git.Git -e") -and $ok
$ok = (Need "python" "install Python 3.11+: winget install --id Python.Python.3.12 -e  (tick 'Add to PATH')") -and $ok
if (-not $ok) { throw "install the missing tools, reopen PowerShell, run again" }
$pyver = (& python -c "import sys;print('%d.%d'%sys.version_info[:2])")
if ([version]$pyver -lt [version]"3.11") { throw "Python $pyver found; need 3.11+" }

if (-not $BlenderExe -or -not (Test-Path $BlenderExe)) {
    $cands = @(
        "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
        "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
    ) + (Get-ChildItem "C:\Program Files\Blender Foundation\*\blender.exe" -ErrorAction SilentlyContinue | % FullName)
    $BlenderExe = ($cands | ? { Test-Path $_ } | Select-Object -First 1)
    if (-not $BlenderExe) { $BlenderExe = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" }
}

# --- 1. clone ---------------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $Root | Out-Null
$RepoDir = Join-Path $Root "VAS"
if (-not $Branch) { $Branch = Ask "git branch the jobs are pushed to" "claude/low-poly-helicopter-glb-d0l1zs" }
if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    Write-Host "cloning $RepoUrl ($Branch) -> $RepoDir (shallow, blobless)" -ForegroundColor Cyan
    & git clone --depth 1 --filter=blob:none --branch $Branch $RepoUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed (private repo? Git Credential Manager will ask you to sign in to GitHub in the browser)" }
} else {
    Write-Host "repo already present, pulling" -ForegroundColor Cyan
    & git -C $RepoDir fetch --depth 1 origin $Branch
    & git -C $RepoDir checkout -q $Branch 2>$null
    & git -C $RepoDir pull --rebase --autostash origin $Branch
}
& git -C $RepoDir config pull.rebase true
& git -C $RepoDir config rebase.autoStash true
& git -C $RepoDir config core.longpaths true
if (-not (& git -C $RepoDir config user.name))  { & git -C $RepoDir config user.name  "renderfarm-$env:COMPUTERNAME" }
if (-not (& git -C $RepoDir config user.email)) { & git -C $RepoDir config user.email "renderfarm-$env:COMPUTERNAME@users.noreply.github.com" }
if (Get-Command "git-lfs" -ErrorAction SilentlyContinue) { & git -C $RepoDir lfs install --local | Out-Null }

$RF = Join-Path $RepoDir "freemarket_defense\renderfarm"
if (-not (Test-Path (Join-Path $RF "agent.py"))) { throw "agent.py not found under $RF - wrong branch?" }

# --- 2. config.json ---------------------------------------------------------------------------
$cfgPath = Join-Path $RF "config.json"
$existing = @{}
if (Test-Path $cfgPath) { $existing = Get-Content $cfgPath -Raw | ConvertFrom-Json }
function Prev($k, $d) { if ($existing.PSObject.Properties[$k]) { return $existing.$k } else { return $d } }

if (-not $Worker)       { $Worker       = Ask "worker name (unique per PC)" (Prev "worker" $env:COMPUTERNAME.ToLower()) }
$BlenderExe             = Ask "blender.exe path" (Prev "blender" $BlenderExe)
if (-not (Test-Path $BlenderExe)) { Write-Host "WARNING: $BlenderExe does not exist yet - install Blender 4.2 LTS from blender.org" -ForegroundColor Yellow }
if (-not $RcloneRemote) { $RcloneRemote = Ask "rclone remote:path for frames (empty = zip to outbox/)" (Prev "rclone_remote" "") }
if (-not $BenchUrl)     { $BenchUrl     = Ask "bench_url (direct link to bench.blend, may be empty)" (Prev "bench_url" "https://raw.githubusercontent.com/danengerer-sudo/VAS/claude/low-poly-helicopter-glb-d0l1zs/freemarket_defense/bench/bench.blend") }
$poll = Ask "poll interval minutes" (Prev "poll_minutes" 5)

$cfg = [ordered]@{
    blender           = $BlenderExe
    repo              = $RepoDir
    branch            = $Branch
    worker            = $Worker
    poll_minutes      = [double]$poll
    push_minutes      = 10
    uploader          = "auto"
    rclone_remote     = $RcloneRemote
    rclone            = "rclone"
    git               = "git"
    outbox_dir        = (Join-Path $Root "outbox")
    zip_part_bytes    = 1900000000
    claim_stale_hours = 12
    bench_url         = $BenchUrl
    blender_extra_args = @()
}
[System.IO.File]::WriteAllText($cfgPath, (($cfg | ConvertTo-Json -Depth 3) -replace "`r`n", "`n") + "`n", (New-Object System.Text.UTF8Encoding $false))
Write-Host "wrote $cfgPath" -ForegroundColor Green
New-Item -ItemType Directory -Force -Path (Join-Path $Root "outbox") | Out-Null

if ($RcloneRemote) {
    if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
        Write-Host "WARNING: rclone not on PATH (winget install Rclone.Rclone), frames will be zipped to outbox until it is" -ForegroundColor Yellow
    } else {
        $remoteName = $RcloneRemote.Split(":")[0]
        if (-not ((& rclone listremotes) -contains "$remoteName`:")) {
            Write-Host "WARNING: rclone remote '$remoteName' not configured - run: rclone config  (New remote > drive)" -ForegroundColor Yellow
        }
    }
}

# --- 3. scheduled task ------------------------------------------------------------------------
$TaskName = "RenderfarmAgent"
$startBat = Join-Path $RF "start_agent.bat"
if (-not $NoTask) {
    Write-Host "registering scheduled task $TaskName (at logon, restart on failure)" -ForegroundColor Cyan
    $action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$startBat`"" -WorkingDirectory $RF
    $trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT1M"
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 2) `
        -MultipleInstances IgnoreNew -StartWhenAvailable -DontStopOnIdleEnd `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -User $env:USERNAME -RunLevel Limited -Force | Out-Null
    Write-Host "task registered. Equivalent schtasks: schtasks /Create /TN $TaskName /SC ONLOGON /TR `"$startBat`"" -ForegroundColor Green
}

# --- 4. power plan ----------------------------------------------------------------------------
if (-not $NoPower) {
    Write-Host "setting power plan: never sleep / hibernate on AC, high performance" -ForegroundColor Cyan
    $ErrorActionPreference = "Continue"
    $pc = "$env:SystemRoot\System32\powercfg.exe"
    foreach ($a in @("/setactive SCHEME_MIN", "/change standby-timeout-ac 0", "/change hibernate-timeout-ac 0",
                     "/change monitor-timeout-ac 15", "/change disk-timeout-ac 0", "/hibernate off",
                     "/setacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 0", "/setactive SCHEME_CURRENT")) {
        try { cmd.exe /c "`"$pc`" $a >nul 2>&1" } catch { }
    }
    $ErrorActionPreference = "Stop"
}

# --- 5. optional bench, then start ------------------------------------------------------------
Write-Host ""
Write-Host "install done." -ForegroundColor Green
Write-Host "  manual start : $startBat"
Write-Host "  manual stop  : $(Join-Path $RF 'stop_agent.bat')"
Write-Host "  benchmark    : $(Join-Path $RF 'bench.bat')"
Write-Host "  log          : $(Join-Path $RF 'logs\agent.log')"
if ($RunBench -or ((Ask "run the benchmark now? (y/n)" "n") -eq "y")) {
    & cmd.exe /c (Join-Path $RF "bench.bat")
}
if ((Ask "start the agent now? (y/n)" "y") -eq "y") {
    if (-not $NoTask) { Start-ScheduledTask -TaskName $TaskName } else { Start-Process cmd.exe -ArgumentList "/c `"$startBat`"" }
    Write-Host "agent started; watch logs\agent.log" -ForegroundColor Green
}
