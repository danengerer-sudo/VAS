@echo off
REM start_agent.bat -- runs the render agent in a loop and restarts it if it crashes.
REM Used by the "RenderfarmAgent" scheduled task; also fine to double-click.
REM Extra arguments are passed to agent.py (e.g.  start_agent.bat --once).
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
if not exist config.json (
  echo config.json missing - copy config.example.json to config.json and edit it, or run install.ps1
  pause
  exit /b 1
)
REM refuse to start a second copy
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agentctl.ps1" running
if %ERRORLEVEL%==1 (
  echo agent.py is already running - use stop_agent.bat first
  exit /b 0
)
del logs\stop.flag 2>nul
title renderfarm agent
:loop
echo [%date% %time%] starting agent.py >> logs\agent_supervisor.log
python agent.py %*
set RC=%ERRORLEVEL%
echo [%date% %time%] agent.py exited with %RC% >> logs\agent_supervisor.log
if exist logs\stop.flag (
  del logs\stop.flag
  echo stop requested, not restarting
  exit /b 0
)
if %RC%==130 exit /b 0
if %RC%==0 exit /b 0
echo agent exited with %RC%, restarting in 60 s ...
timeout /t 60 /nobreak >nul
goto loop
