#!/usr/bin/env python3
"""
Launch the Invoice Splitter web UI in your browser.

Usage:
  python run_ui.py --launch          # start in background (no terminal needed), open browser
  python run_ui.py                   # foreground with console (for troubleshooting)
  python run_ui.py --stop            # stop background server
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui.app import app  # noqa: E402

DEFAULT_PORT = 5050
DEFAULT_HOST = "127.0.0.1"
PID_FILE = _ROOT / ".invoice_splitter.pid"
LOG_DIR = _ROOT / "logs"


def _url(port: int) -> str:
    return f"http://{DEFAULT_HOST}:{port}/"


def is_server_running(port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex((DEFAULT_HOST, port)) == 0
    except OSError:
        return False


def _python_for_background() -> str:
    """Prefer pythonw on Windows so no console window appears."""
    exe = Path(sys.executable)
    if sys.platform == "win32":
        pyw = exe.parent / "pythonw.exe"
        if pyw.is_file():
            return str(pyw)
    return sys.executable


def setup_background_logging() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "app.log"
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)
    return log_path


def write_pid_file() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def stop_background_server() -> bool:
    """Stop server using pid file. Returns True if a stop was attempted."""
    if not PID_FILE.is_file():
        if is_server_running():
            print("Server is running but pid file is missing — restart your PC or ask IT.")
            return False
        print("Invoice Splitter is not running.")
        return False

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        remove_pid_file()
        print("Could not read pid file.")
        return False

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=False,
            capture_output=True,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    time.sleep(0.5)
    remove_pid_file()
    if is_server_running():
        print("Server may still be stopping — wait a few seconds and try again.")
        return False
    print("Invoice Splitter stopped.")
    return True


def launch_background(port: int, open_browser: bool = True) -> None:
    """Start server detached, or open browser if already running."""
    if is_server_running(port):
        if open_browser:
            webbrowser.open(_url(port))
        print("Invoice Splitter is already running — opened in your browser.")
        return

    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )

    cmd = [
        _python_for_background(),
        str(_ROOT / "run_ui.py"),
        "--background",
        "--no-browser",
        "--port",
        str(port),
    ]
    subprocess.Popen(
        cmd,
        cwd=_ROOT,
        creationflags=creationflags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(40):
        if is_server_running(port):
            break
        time.sleep(0.25)

    if open_browser:
        webbrowser.open(_url(port))

    if is_server_running(port):
        print("Invoice Splitter is running in the background (no terminal window).")
        print(f"  Browser: {_url(port)}")
        print(f"  Log file: {LOG_DIR / 'app.log'}")
        print('  When finished for the day, use "Stop Invoice Splitter" on your desktop.')
    else:
        print("Could not start the server. See logs/app.log or run Setup again.")


def serve_foreground(port: int, background: bool) -> None:
    url = _url(port)
    if background:
        log_path = setup_background_logging()
        write_pid_file()
        logging.info("Invoice Splitter started (background mode)")
        logging.info("Log file: %s", log_path)
    else:
        print()
        print("=" * 50)
        print("  Invoice Splitter — Web UI")
        print("=" * 50)
        print(f"  Open in browser: {url}")
        print("  Press Ctrl+C to stop.")
        print("=" * 50)
        print()

    try:
        from waitress import serve

        if not background:
            print("  Server: Waitress")
        serve(
            app,
            host=DEFAULT_HOST,
            port=port,
            threads=4,
            channel_timeout=3600,
        )
    except ImportError:
        if not background:
            print("  Server: Flask dev (pip install waitress recommended)")
        app.run(
            host=DEFAULT_HOST,
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    finally:
        remove_pid_file()


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoice Splitter web UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Start in background (no terminal) and open browser",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--stop", action="store_true", help="Stop background server")
    args = parser.parse_args()

    if args.stop:
        raise SystemExit(0 if stop_background_server() else 1)

    if args.launch:
        launch_background(args.port, open_browser=not args.no_browser)
        return

    if args.background:
        serve_foreground(args.port, background=True)
        return

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(_url(args.port))).start()
    serve_foreground(args.port, background=False)


if __name__ == "__main__":
    main()
