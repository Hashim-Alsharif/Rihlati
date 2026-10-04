@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_rihlati.ps1" %*
if errorlevel 1 (
  echo.
  echo Rihlati could not start. Please read the message above.
  pause
  exit /b 1
)
exit /b 0
