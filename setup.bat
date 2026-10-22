@echo off
setlocal
cd /d "%~dp0"
title IRIS setup
set "IRIS_PY=python"
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>nul
if errorlevel 1 (
  set "IRIS_PY=py -3"
  py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.11 or newer from python.org, then run setup again.
    pause
    exit /b 1
  )
)
if not exist ".venv\Scripts\python.exe" %IRIS_PY% -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m iris.desktop.setup
if errorlevel 1 goto failed
echo Setup complete. Double-click start-iris.bat.
pause
exit /b 0
:failed
echo Setup stopped. Review the message above.
pause
exit /b 1
