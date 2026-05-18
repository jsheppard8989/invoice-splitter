@echo off
cd /d "%~dp0"
title Invoice Splitter

set "PY_CMD="
where py >nul 2>&1 && (
  py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
)
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD where python3 >nul 2>&1 && set "PY_CMD=python3"

if not defined PY_CMD (
  echo Python was not found. Install Python 3 from https://www.python.org/downloads/
  echo On the installer, check "Add python.exe to PATH".
  echo Then run "Setup Invoice Splitter.bat" once before starting the program.
  pause
  exit /b 1
)

echo Starting Invoice Splitter...
echo Your browser should open to http://127.0.0.1:5050
echo Leave this window open while using the program. Close it to stop.
echo.

%PY_CMD% run_ui.py
if %ERRORLEVEL% neq 0 pause
