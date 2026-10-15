<#
setup_drive.ps1 -- make frame delivery fully automatic: rclone -> Google Drive.
Installs rclone, signs in to Google Drive once (browser window), creates My Drive/renderfarm,
points config.json at it and restarts the agent. Re-runnable.

    powershell -ExecutionPolicy Bypass -File C:\renderfarm\VAS\freemarket_defense\renderfarm\setup_drive.ps1
#>
param([string]$Remote = "gdrive", [string]$Folder = "renderfarm")
$ErrorActionPreference = "Continue"
$RF = Split-Path -Parent $MyInvocation.MyCommand.Path

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    Write-Host "installing rclone" -ForegroundColor Cyan
    winget install --id Rclone.Rclone -e --source winget --accept-package-agreements --accept-source-agreements
    Refresh-Path
}
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\rclone*" -Recurse -Filter rclone.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $env:Path += ";" + $found.DirectoryName }
}
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) { throw "rclone not found after install; reopen PowerShell and run this script again" }
$rclone = (Get-Command rclone).Source
Write-Host "rclone: $rclone" -ForegroundColor Green

if (-not ((& rclone listremotes) -contains "$Remote`:")) {
    Write-Host "A browser window will open: sign in to the Google account whose Drive should receive the frames, click Allow." -ForegroundColor Yellow
    & rclone config create $Remote drive scope=drive config_is_local=true | Out-Null
}
& rclone lsd "$Remote`:" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "rclone cannot list Drive; run: rclone config reconnect $Remote`:" }
& rclone mkdir "$Remote`:$Folder"
Write-Host "Drive folder ready: $Remote`:$Folder" -ForegroundColor Green

# point config.json at it (write without BOM)
$py = @"
import json,sys
p=r'$RF\config.json'
c=json.load(open(p,encoding='utf-8-sig'))
c['rclone_remote']='$Remote`:$Folder'; c['rclone']=r'$rclone'; c['uploader']='auto'
open(p,'w',encoding='utf-8').write(json.dumps(c,indent=2))
print('config updated:',c['rclone_remote'])
"@
& python -c $py

Write-Host "restarting agent" -ForegroundColor Cyan
& cmd.exe /c (Join-Path $RF "stop_agent.bat")
Start-ScheduledTask -TaskName RenderfarmAgent -ErrorAction SilentlyContinue
if (-not $?) { Start-Process cmd.exe -ArgumentList "/c `"$(Join-Path $RF 'start_agent.bat')`"" }
Write-Host "done. Frames now upload to My Drive/$Folder/<job>/frames automatically." -ForegroundColor Green
