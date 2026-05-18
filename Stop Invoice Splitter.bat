@echo off
cd /d "%~dp0"
title Invoice Splitter — Stop

set "PY_CMD="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3")
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"

if not defined PY_CMD (
  echo Python was not found.
  pause
  exit /b 1
)

%PY_CMD% run_ui.py --stop
pause
