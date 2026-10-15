@echo off
REM bench.bat -- renders frames 1-48 of bench\bench.blend with EEVEE at 1080p and pushes bench\bench_result.json
setlocal
cd /d "%~dp0"
if not exist config.json (
  echo config.json missing - run install.ps1 first
  pause
  exit /b 1
)
python agent.py --bench %*
echo.
echo result saved to bench\bench_result.json (and pushed to the repo). Also in logs\agent.log.
pause
