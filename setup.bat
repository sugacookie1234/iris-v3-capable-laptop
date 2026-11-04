@echo off
setlocal
cd /d "%~dp0"
title IRIS setup
set "IRIS_PY=python"
python -c "import sys,struct; sys.exit(not ((3,11) <= sys.version_info < (3,14) and struct.calcsize('P') == 8))" >nul 2>nul
if errorlevel 1 (
  set "IRIS_PY=py -3.13"
  py -3.13 -c "import struct; assert struct.calcsize('P') == 8" >nul 2>nul
  if errorlevel 1 (
    echo Install 64-bit Python 3.13 from python.org, then run setup again.
    pause
    exit /b 1
  )
)
if not exist ".venv\Scripts\python.exe" %IRIS_PY% -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes --index-url https://pypi.org/simple -r requirements-tooling.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m iris.desktop.setup
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m iris.desktop.install_speech --gpu-libraries
if errorlevel 1 goto failed
echo Setup complete. Double-click start-iris.bat. Use check-speech.bat to test local recognition.
pause
exit /b 0
:failed
echo Setup stopped. Review the message above.
pause
exit /b 1
