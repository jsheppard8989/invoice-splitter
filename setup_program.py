#!/usr/bin/env python3
"""
First-time setup: install Python packages, create .env, show status.

Used by Setup Invoice Splitter.bat (Windows) and Setup Invoice Splitter.command (Mac).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
REQUIREMENTS = ROOT / "requirements.txt"
PLACEHOLDER_KEY = "sk-your-key-here"


def install_dependencies() -> None:
    if not REQUIREMENTS.is_file():
        raise FileNotFoundError(f"Missing {REQUIREMENTS}")
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    print("Installing dependencies (this may take a minute)...")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        print("Standard install failed — retrying with --user (common on work PCs)...")
        subprocess.check_call(cmd + ["--user"])

    # pytesseract <0.3.13 breaks on Python 3.14+ (removed pkgutil.find_loader)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "pytesseract>=0.3.13", "--upgrade"],
    )


def ensure_env_file() -> bool:
    """Copy .env.example to .env if needed. Returns True if a new file was created."""
    if ENV_FILE.is_file():
        return False
    if not ENV_EXAMPLE.is_file():
        ENV_FILE.write_text(f"OPENAI_API_KEY={PLACEHOLDER_KEY}\n", encoding="utf-8")
        return True
    shutil.copy(ENV_EXAMPLE, ENV_FILE)
    return True


def api_key_needs_edit() -> bool:
    if not ENV_FILE.is_file():
        return True
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("OPENAI_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return not value or value == PLACEHOLDER_KEY or not value.startswith("sk")
    return True


def open_env_in_editor() -> None:
    if not ENV_FILE.is_file():
        ensure_env_file()
    path = str(ENV_FILE.resolve())
    print(f"Opening {path} — paste your OpenAI API key, save, and close the editor.")
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 — opens with default app (usually Notepad)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-t", path], check=False)
    else:
        editor = os.environ.get("EDITOR") or "nano"
        subprocess.run([editor, path], check=False)


def print_status_report() -> bool:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from ui.setup_status import get_setup_status

    status = get_setup_status()
    print()
    print("=" * 50)
    print("  Setup status")
    print("=" * 50)
    for step in status["steps"]:
        mark = "OK" if step["ok"] else ("opt" if step.get("optional") else "!!")
        print(f"  [{mark:>3}] {step['label']}")
        if not step["ok"]:
            print(f"         {step['detail']}")
            if step.get("fix"):
                print(f"         → {step['fix']}")
    print()
    if status["ready"]:
        print("  Ready to run. Double-click:")
        print(f"    {status['launcher']}")
    else:
        print("  Finish the items marked [!!], then run setup again or start the app.")
    print("=" * 50)
    print()
    return bool(status["ready"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Invoice Splitter first-time setup")
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Start the web UI after setup if everything is ready",
    )
    parser.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip pip install (packages already installed)",
    )
    parser.add_argument(
        "--desktop-icon",
        action="store_true",
        help="Only create or refresh the desktop shortcut",
    )
    args = parser.parse_args()

    if args.desktop_icon:
        from desktop_shortcut import create_desktop_shortcut

        try:
            path = create_desktop_shortcut()
            print(f"Desktop icon created:\n  {path}")
            return 0
        except Exception as exc:
            print(f"Could not create desktop icon: {exc}")
            return 1

    print()
    print("Invoice Splitter — Setup")
    print(f"Folder: {ROOT}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print()

    if not args.skip_pip:
        try:
            install_dependencies()
        except subprocess.CalledProcessError:
            print()
            print("Could not install packages. On a work PC you may need IT to allow")
            print("pip, or run this from a terminal as Administrator:")
            print(f'  cd "{ROOT}"')
            print(f'  "{sys.executable}" -m pip install -r requirements.txt')
            print()
            return 1

    created = ensure_env_file()
    if created:
        print(f"Created {ENV_FILE.name} from .env.example")

    if api_key_needs_edit():
        open_env_in_editor()
        print()
        input("Press Enter after you have saved your API key in .env... ")

    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE, override=True)
    except ImportError:
        pass

    ready = print_status_report()

    if ready:
        from desktop_shortcut import create_desktop_shortcut

        try:
            shortcut = create_desktop_shortcut()
            print(f"Desktop icon created: {shortcut}")
        except Exception as exc:
            print(f"Note: could not create desktop icon ({exc}).")
            print('Run "Create Desktop Icon.bat" (Windows) or ".command" (Mac) to try again.')
        print()

    if args.launch and ready:
        print("Starting web UI...")
        subprocess.Popen([sys.executable, str(ROOT / "run_ui.py")], cwd=ROOT)
    elif ready:
        launcher = (
            "Start Invoice Splitter.bat"
            if sys.platform == "win32"
            else "Start Invoice Splitter.command"
            if sys.platform == "darwin"
            else "python run_ui.py"
        )
        print(f"Next: double-click “{launcher}” to open the program.")
    print()
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
