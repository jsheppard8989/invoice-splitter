#!/usr/bin/env python3
"""
Launch the Invoice Splitter web UI in your browser.

Usage:
  python run_ui.py

Then drag PDFs onto the page. Use the buttons to open today's folders in Finder/Explorer.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

# Ensure project root is on path when run from anywhere
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui.app import app  # noqa: E402

DEFAULT_PORT = 5050
DEFAULT_HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoice Splitter web UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local port (default 5050)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    url = f"http://{DEFAULT_HOST}:{args.port}/"

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    print()
    print("=" * 50)
    print("  Invoice Splitter — Web UI")
    print("=" * 50)
    print(f"  Open in browser: {url}")
    print("  Press Ctrl+C to stop.")
    print("=" * 50)
    print()

    app.run(host=DEFAULT_HOST, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
