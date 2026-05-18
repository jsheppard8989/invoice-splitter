#!/usr/bin/env python3
"""
One-time hotfix for work PCs still on pre-fix code (Python 3.14 + pytesseract 0.3.10).
Safe to run multiple times.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

SETUP_STATUS = ROOT / "ui" / "setup_status.py"
INVOICE_SPLITTER = ROOT / "invoice_splitter.py"
REQUIREMENTS = ROOT / "requirements.txt"


def patch_setup_status() -> None:
    text = SETUP_STATUS.read_text(encoding="utf-8")
    old = "from invoice_splitter import _PROJECT_ROOT"
    new = "_PROJECT_ROOT = Path(__file__).resolve().parent.parent"
    if old in text:
        SETUP_STATUS.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  Patched {SETUP_STATUS.name}")
    elif new in text:
        print(f"  {SETUP_STATUS.name} already OK")
    else:
        print(f"  WARNING: could not patch {SETUP_STATUS.name}")


def patch_invoice_splitter() -> None:
    text = INVOICE_SPLITTER.read_text(encoding="utf-8")
    if "import pytesseract  # lazy" in text:
        print(f"  {INVOICE_SPLITTER.name} already OK")
        return
    if "\nimport pytesseract\n" in text:
        text = text.replace("\nimport pytesseract\n", "\n", 1)
    needle = "    def _extract_image_based(self, pdf_path: str) -> str:\n        try:\n"
    insert = (
        "    def _extract_image_based(self, pdf_path: str) -> str:\n"
        "        try:\n"
        "            import pytesseract  # lazy; needs >=0.3.13 on Python 3.14+\n\n"
    )
    if needle in text:
        text = text.replace(needle, insert, 1)
        INVOICE_SPLITTER.write_text(text, encoding="utf-8")
        print(f"  Patched {INVOICE_SPLITTER.name}")
    else:
        print(f"  WARNING: could not patch {INVOICE_SPLITTER.name}")


def patch_requirements() -> None:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    if "pytesseract==0.3.10" in text:
        REQUIREMENTS.write_text(
            text.replace("pytesseract==0.3.10", "pytesseract>=0.3.13", 1),
            encoding="utf-8",
        )
        print(f"  Patched {REQUIREMENTS.name}")
    elif "pytesseract>=0.3.13" in text:
        print(f"  {REQUIREMENTS.name} already OK")
    else:
        print(f"  WARNING: could not patch {REQUIREMENTS.name}")


def main() -> int:
    print("Invoice Splitter setup hotfix")
    print(f"Folder: {ROOT}\n")
    patch_setup_status()
    patch_invoice_splitter()
    patch_requirements()
    print("\nHotfix complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
