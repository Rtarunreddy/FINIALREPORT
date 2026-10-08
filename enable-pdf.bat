@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 launcher.py --enable-pdf
) else (
  python launcher.py --enable-pdf
)
pause
endlocal
