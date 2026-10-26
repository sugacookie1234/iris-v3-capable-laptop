@echo off
setlocal
cd /d "%~dp0"
title IRIS phone connection
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat and setup-phone.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m iris.phone serve
if errorlevel 1 pause
