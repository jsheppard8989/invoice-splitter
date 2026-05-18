@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Invoice Splitter — Setup

echo.
echo ==================================================
echo   Invoice Splitter - First-time setup (Windows)
echo ==================================================
echo.
echo This installs required packages and helps you add
echo your OpenAI API key. Run once on a new computer.
echo.

REM Prefer Windows Python launcher, then python, then python3
set "PY_CMD="
where py >nul 2>&1 && (
  py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
)
if not defined PY_CMD where python >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD where python3 >nul 2>&1 && set "PY_CMD=python3"

if not defined PY_CMD (
  echo Python 3 was not found.
  echo.
  echo 1. Install Python 3.9+ from https://www.python.org/downloads/
  echo 2. On the installer, check "Add python.exe to PATH"
  echo 3. Run this setup file again
  echo.
  pause
  exit /b 1
)

echo Using: %PY_CMD%
echo.

%PY_CMD% setup_program.py
set SETUP_EXIT=%ERRORLEVEL%

if %SETUP_EXIT% neq 0 (
  echo Setup did not complete. Fix the issues above and run this file again.
  pause
  exit /b %SETUP_EXIT%
)

echo.
set /p LAUNCH="Start Invoice Splitter now? (Y/n): "
if /i "!LAUNCH!"=="n" goto :done
echo.
start "" "%~dp0Start Invoice Splitter.bat"

:done
echo.
pause
exit /b 0
