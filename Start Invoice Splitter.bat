@echo off
cd /d "%~dp0"
title Invoice Splitter

set "PY_CMD="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3")
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD where python3 >nul 2>&1 && set "PY_CMD=python3"

if not defined PY_CMD (
  echo Python was not found. Run Setup Invoice Splitter.bat first.
  pause
  exit /b 1
)

REM Starts in background and closes this window — no terminal to keep open.
%PY_CMD% run_ui.py --launch
timeout /t 3 >nul
