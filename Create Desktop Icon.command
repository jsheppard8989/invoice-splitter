#!/bin/bash
cd "$(dirname "$0")"
if command -v python3 &>/dev/null; then
  PY=python3
elif command -v python &>/dev/null; then
  PY=python
else
  echo "Python 3 is required."
  read -r -p "Press Enter to close."
  exit 1
fi
"$PY" setup_program.py --desktop-icon
read -r -p "Press Enter to close."
