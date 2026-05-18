"""Locate Poppler and Tesseract on Windows when not on system PATH."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional


def _win_poppler_bin_dirs() -> List[Path]:
    candidates: List[Path] = [
        Path(r"C:\poppler\Library\bin"),
        Path(r"C:\Program Files\poppler\Library\bin"),
        Path(r"C:\Program Files (x86)\poppler\Library\bin"),
    ]
    for base in (Path(r"C:\Program Files"), Path.home() / "poppler"):
        if base.is_dir():
            candidates.extend(base.glob("poppler*/Library/bin"))
    seen: set[str] = set()
    out: List[Path] = []
    for p in candidates:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        if (p / "pdftoppm.exe").is_file() or (p / "pdftocairo.exe").is_file():
            out.append(p)
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
