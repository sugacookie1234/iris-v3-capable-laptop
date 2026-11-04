@echo off
setlocal
cd /d "%~dp0"
title IRIS phone setup
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes --index-url https://pypi.org/simple -r requirements-tooling.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements-phone.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m iris.phone.setup
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Phone setup stopped. Review the message above.
pause
exit /b 1
