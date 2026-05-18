@echo off
cd /d "%~dp0"
title Invoice Splitter — Install from scratch

echo.
echo ============================================================
echo   Invoice Splitter — Command-line install helper
echo ============================================================
echo.
echo BEFORE this script, install manually if you have not yet:
echo   1. Python 3.12  (python.org — check Add to PATH)
echo   2. Tesseract    (github.com/UB-Mannheim/tesseract/wiki)
echo   3. Poppler      (github.com/oschwartz10612/poppler-windows/releases/)
echo      Release-....zip only — add Library\bin to PATH
echo.
echo See INSTALL-FROM-SCRATCH.txt for full copy/paste commands.
echo.
pause

set "PY_CMD="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3")
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
  echo ERROR: Python not found. Install Python 3.12 and run this again.
  pause
  exit /b 1
)

echo Using: %PY_CMD%
echo.
echo [1/3] Upgrading pip and installing Python packages...
%PY_CMD% -m pip install --upgrade pip
%PY_CMD% -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
  echo pip install failed.
  pause
  exit /b 1
)

echo.
echo [2/3] Running setup (API key, checklist, desktop icons)...
%PY_CMD% setup_program.py
if %ERRORLEVEL% neq 0 (
  echo Setup did not finish. Fix checklist items and run Setup Invoice Splitter.bat again.
  pause
  exit /b 1
)

echo.
echo [3/3] Done.
echo   Start: Invoice Splitter (desktop) or Start Invoice Splitter.vbs
echo   Stop:  Stop Invoice Splitter (desktop)
echo.
pause
