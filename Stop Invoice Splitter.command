#!/bin/bash
cd "$(dirname "$0")"
PY=python3
command -v python3 &>/dev/null || PY=python
"$PY" run_ui.py --stop
read -r -p "Press Enter to close."
