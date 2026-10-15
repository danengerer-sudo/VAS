@echo off
REM stop_agent.bat -- stops the agent supervisor loop, agent.py and any headless Blender it started.
REM The chunk being rendered resumes from the last finished frame on the next start.
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo stop > logs\stop.flag
schtasks /End /TN RenderfarmAgent >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agentctl.ps1" stop
del logs\stop.flag 2>nul
echo agent stopped.
echo To disable autostart:  schtasks /Change /TN RenderfarmAgent /DISABLE
echo To re-enable:          schtasks /Change /TN RenderfarmAgent /ENABLE
