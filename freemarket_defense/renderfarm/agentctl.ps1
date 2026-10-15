# agentctl.ps1 -- helper used by start_agent.bat / stop_agent.bat (CIM instead of deprecated wmic).
#   agentctl.ps1 running   -> exit code 1 if an agent.py is running, else 0
#   agentctl.ps1 stop      -> stop supervisor cmd, agent.py and headless blender started by it
param([Parameter(Mandatory = $true)][ValidateSet("running", "stop")][string]$Action)

function AgentProcs {
    Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -ieq "python.exe" -and $_.CommandLine -like "*agent.py*") -or
        ($_.Name -ieq "cmd.exe"    -and $_.CommandLine -like "*start_agent.bat*")
    }
}

if ($Action -eq "running") {
    $n = @(AgentProcs | Where-Object { $_.Name -ieq "python.exe" }).Count
    exit ([int]($n -gt 0))
}

if ($Action -eq "stop") {
    foreach ($p in AgentProcs) {
        Write-Host ("stopping {0} {1}" -f $p.Name, $p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
    Get-CimInstance Win32_Process -Filter "name='blender.exe'" |
        Where-Object { $_.CommandLine -like "* -b *" -or $_.CommandLine -like "*--background*" } |
        ForEach-Object {
            Write-Host ("stopping headless blender {0}" -f $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    exit 0
}
