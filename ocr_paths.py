"""Locate Poppler and Tesseract on Windows when not on system PATH."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional


def _win_poppler_bin_dirs() -> List[Path]:
    """Folders containing pdftoppm.exe (oschwartz10612 zip uses .../Library/bin)."""
    seen: set[str] = set()
    out: List[Path] = []

    def add(folder: Path) -> None:
        key = str(folder.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(folder)

    env_bin = os.environ.get("POPPLER_BIN", "").strip()
    if env_bin:
        p = Path(env_bin)
        if (p / "pdftoppm.exe").is_file() or p.name.lower() == "pdftoppm.exe":
            add(p if p.is_dir() else p.parent)

    candidates: List[Path] = [
        Path(r"C:\poppler\Library\bin"),
        Path(r"C:\Program Files\poppler\Library\bin"),
    ]
    for base in (
        Path(r"C:\poppler"),
        Path(r"C:\Program Files"),
        Path.home() / "Downloads",
        Path.home() / "poppler",
    ):
        if base.is_dir():
            candidates.extend(base.glob("**/Library/bin"))
            candidates.extend(base.glob("**/bin"))

    for p in candidates:
        if (p / "pdftoppm.exe").is_file() or (p / "pdftocairo.exe").is_file():
            add(p)

    for root in (Path(r"C:\poppler"), Path.home() / "Downloads"):
        if not root.is_dir():
            continue
        try:
            for exe in root.rglob("pdftoppm.exe"):
                add(exe.parent)
                break
        except OSError:
            pass
    return out


def _win_tesseract_dirs() -> List[Path]:
    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR"),
    ]
    return [p for p in candidates if (p / "tesseract.exe").is_file()]


def configure_ocr_path() -> None:
    """Prepend common Windows OCR tool folders to PATH for this process."""
    if sys.platform != "win32":
        return
    prepend: List[str] = []
    for folder in _win_poppler_bin_dirs() + _win_tesseract_dirs():
        prepend.append(str(folder))
    if not prepend:
        return
    existing = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(prepend) + (os.pathsep + existing if existing else "")


def find_pdftoppm() -> Optional[str]:
    configure_ocr_path()
    return shutil.which("pdftoppm") or shutil.which("pdftocairo")


def find_tesseract() -> Optional[str]:
    configure_ocr_path()
    return shutil.which("tesseract")


def poppler_bin_dir() -> Optional[str]:
    """Directory passed to pdf2image.convert_from_path(poppler_path=...)."""
    exe = find_pdftoppm()
    if exe:
        return str(Path(exe).parent)
    env_bin = os.environ.get("POPPLER_BIN", "").strip()
    if env_bin:
        p = Path(env_bin)
        return str(p if p.is_dir() else p.parent)
    return None


def tesseract_cmd() -> Optional[str]:
    """Full path to tesseract.exe for pytesseract."""
    return find_tesseract()
