@echo off
cd /d "%~dp0"
title Invoice Splitter — Desktop Icon

set "PY_CMD="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3")
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD where python3 >nul 2>&1 && set "PY_CMD=python3"

if not defined PY_CMD (
  echo Python 3 was not found. Run Setup Invoice Splitter.bat first.
  pause
  exit /b 1
)

%PY_CMD% setup_program.py --desktop-icon
pause
