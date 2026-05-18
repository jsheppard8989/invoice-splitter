"""Create a desktop shortcut to launch Invoice Splitter (Windows, Mac, Linux)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHORTCUT_NAME = "Invoice Splitter"


def _desktop_folder() -> Path:
    home = Path.home()
    if sys.platform == "win32":
        for candidate in (
            home / "Desktop",
            home / "OneDrive" / "Desktop",
        ):
            if candidate.is_dir():
                return candidate
        return home / "Desktop"
    return home / "Desktop"


def _launcher_path() -> Path:
    if sys.platform == "win32":
        return ROOT / "Start Invoice Splitter.bat"
    if sys.platform == "darwin":
        return ROOT / "Start Invoice Splitter.command"
    return ROOT / "run_ui.py"


def create_desktop_shortcut() -> Path:
    """
    Create or refresh a desktop shortcut. Returns the path to the shortcut file.
    """
    desktop = _desktop_folder()
    desktop.mkdir(parents=True, exist_ok=True)
    launcher = _launcher_path()
    if not launcher.is_file() and sys.platform != "linux":
        raise FileNotFoundError(f"Launcher not found: {launcher}")

    if sys.platform == "win32":
        return _create_windows_shortcut(desktop, launcher)
    if sys.platform == "darwin":
        return _create_mac_alias(desktop, launcher)
    return _create_linux_desktop_entry(desktop)


def _create_windows_shortcut(desktop: Path, launcher: Path) -> Path:
    shortcut = desktop / f"{SHORTCUT_NAME}.lnk"
    target = str(launcher.resolve())
    workdir = str(ROOT.resolve())
    desc = "Split multi-invoice PDFs for accounts payable"
    ps = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut}')
$Shortcut.TargetPath = '{target}'
$Shortcut.WorkingDirectory = '{workdir}'
$Shortcut.Description = '{desc}'
$Shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True,
    )
    return shortcut


def _create_mac_alias(desktop: Path, launcher: Path) -> Path:
    alias = desktop / SHORTCUT_NAME
    target = str(launcher.resolve())
    # Remove old alias/app with same name so we can recreate cleanly
    if alias.exists():
        if alias.is_symlink() or alias.is_file():
            alias.unlink()
        else:
            subprocess.run(["rm", "-rf", str(alias)], check=False)
    script = f'''
tell application "Finder"
    set dest to POSIX file "{desktop}"
    set src to POSIX file "{target}"
    set theAlias to make alias file to src at dest
    set name of theAlias to "{SHORTCUT_NAME}"
end tell
'''
    subprocess.run(["osascript", "-e", script], check=True)
    if not alias.exists():
        raise RuntimeError(f"Expected desktop alias at {alias}")
    return alias


def _create_linux_desktop_entry(desktop: Path) -> Path:
    entry = desktop / f"{SHORTCUT_NAME}.desktop"
    python = sys.executable
    run_ui = str((ROOT / "run_ui.py").resolve())
    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={SHORTCUT_NAME}
Comment=Split multi-invoice PDFs for accounts payable
Exec={python} {run_ui}
Path={ROOT.resolve()}
Terminal=true
Categories=Office;
"""
    entry.write_text(content, encoding="utf-8")
    os.chmod(entry, 0o755)
    return entry


def main() -> int:
    try:
        path = create_desktop_shortcut()
    except Exception as exc:
        print(f"Could not create desktop icon: {exc}")
        return 1
    print(f"Desktop icon created:\n  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
