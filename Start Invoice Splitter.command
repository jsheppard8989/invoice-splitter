#!/bin/bash
cd "$(dirname "$0")"
if command -v python3 &>/dev/null; then
  exec python3 run_ui.py
elif command -v python &>/dev/null; then
  exec python run_ui.py
else
  echo "Python 3 is required. Install Python from https://www.python.org/downloads/"
  read -r -p "Press Enter to close."
  exit 1
fi
