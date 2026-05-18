#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "=================================================="
echo "  Invoice Splitter — First-time setup (Mac)"
echo "=================================================="
echo ""

if command -v python3 &>/dev/null; then
  PY=python3
elif command -v python &>/dev/null; then
  PY=python
else
  echo "Python 3 is required. Install from https://www.python.org/downloads/"
  read -r -p "Press Enter to close."
  exit 1
fi

echo "Using: $PY"
echo ""

"$PY" setup_program.py
SETUP_EXIT=$?

if [ "$SETUP_EXIT" -ne 0 ]; then
  echo "Setup did not complete. Fix the issues above and run this file again."
  read -r -p "Press Enter to close."
  exit "$SETUP_EXIT"
fi

echo ""
read -r -p "Start Invoice Splitter now? (Y/n): " LAUNCH
if [[ ! "$LAUNCH" =~ ^[Nn]$ ]]; then
  open "$(dirname "$0")/Start Invoice Splitter.command"
fi

read -r -p "Press Enter to close."
