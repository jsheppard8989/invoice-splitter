@echo off
cd /d "%~dp0"
title Invoice Splitter — Fix Setup (Python 3.14)

echo.
echo Fixing pytesseract for Python 3.14 and applying setup hotfix...
echo.

set "PY_CMD="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3")
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
  echo Python 3 was not found.
  pause
  exit /b 1
)

echo [1/2] Upgrading pytesseract to 0.3.13+ ...
%PY_CMD% -m pip install "pytesseract>=0.3.13" --upgrade
if %ERRORLEVEL% neq 0 (
  echo pip upgrade failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Patching project files for Python 3.14 ...
%PY_CMD% fix_setup_hotfix.py
if %ERRORLEVEL% neq 0 (
  echo Hotfix failed.
  pause
  exit /b 1
)

echo.
echo Done. Now double-click "Setup Invoice Splitter.bat" again.
echo.
pause
