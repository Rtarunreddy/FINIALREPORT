@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 launcher.py
) else (
  python launcher.py
)
if errorlevel 1 (
  echo.
  echo Setup or startup failed. Check the message above.
  echo Python 3.10 or newer is required. Select Add Python to PATH during installation.
  pause
)
endlocal
