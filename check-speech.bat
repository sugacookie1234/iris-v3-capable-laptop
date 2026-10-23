@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m iris.desktop.check_speech
set "IRIS_RESULT=%errorlevel%"
pause
exit /b %IRIS_RESULT%
