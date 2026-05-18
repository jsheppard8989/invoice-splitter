"""First-run / install checks shown in the web UI (Windows, Mac, Linux)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from ocr_paths import find_pdftoppm, find_tesseract

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _check_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def get_setup_status() -> Dict[str, Any]:
    root = _PROJECT_ROOT
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)
    platform = sys.platform
    if platform == "win32":
        os_name = "Windows"
        launcher = "Start Invoice Splitter.vbs"
        setup_launcher = "Setup Invoice Splitter.bat"
    elif platform == "darwin":
        os_name = "macOS"
        launcher = "Start Invoice Splitter.command"
        setup_launcher = "Setup Invoice Splitter.command"
    else:
        os_name = "Linux"
        launcher = "python run_ui.py"
        setup_launcher = "python setup_program.py"

    steps: List[Dict[str, Any]] = []

    py_ver = sys.version.split()[0]
    py_detail = f"Using {py_ver} ({sys.executable})"
    py_ok = sys.version_info >= (3, 9)
    if sys.version_info >= (3, 14):
        py_detail += " — Python 3.12 or 3.13 is recommended on Windows for best compatibility"
    steps.append(
        {
            "id": "python",
            "label": "Python 3 installed",
            "ok": py_ok,
            "detail": py_detail,
            "fix": "Install Python 3.12 from https://www.python.org/downloads/ "
            "(Windows: check “Add Python to PATH”). Avoid 3.14 until all tools support it.",
        }
    )

    packages = [
        ("flask", "flask"),
        ("pydantic", "pydantic"),
        ("PyPDF2", "PyPDF2"),
        ("requests", "requests"),
        ("dotenv", "dotenv"),
        ("pdf2image", "pdf2image"),
        ("pytesseract", "pytesseract"),
    ]
    missing = [pip_name for pip_name, mod in packages if not _check_import(mod)]
    steps.append(
        {
            "id": "packages",
            "label": "Program dependencies installed",
            "ok": not missing,
            "detail": "OK" if not missing else f"Missing: {', '.join(missing)}",
            "fix": f'Double-click "{setup_launcher}" in the program folder, '
            f"or run: pip install -r requirements.txt",
        }
    )

    has_env = env_path.is_file()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    steps.append(
        {
            "id": "env_file",
            "label": "Configuration file (.env) present",
            "ok": has_env,
            "detail": str(env_path) if has_env else "File not found",
            "fix": f'Double-click "{setup_launcher}" to create .env, or copy .env.example to .env',
        }
    )
    steps.append(
        {
            "id": "api_key",
            "label": "OpenAI API key configured",
            "ok": bool(api_key and api_key.startswith("sk")),
            "detail": "Key loaded from .env" if api_key else "OPENAI_API_KEY not set",
            "fix": f'Run "{setup_launcher}" or edit .env and set OPENAI_API_KEY=sk-your-key-here',
        }
    )

    poppler = find_pdftoppm()
    steps.append(
        {
            "id": "poppler",
            "label": "Poppler (pdftoppm)",
            "sublabel": "Step 1 for scanned PDFs: converts each page to an image",
            "ok": poppler is not None,
            "detail": poppler or "Not found on PATH",
            "fix": "Windows: install Poppler and add its bin folder to PATH "
            "(https://github.com/oschwartz10612/poppler-windows/releases/). "
            "Mac: brew install poppler",
        }
    )

    tesseract = find_tesseract()
    steps.append(
        {
            "id": "tesseract",
            "label": "Tesseract OCR",
            "sublabel": "Step 2 for scanned PDFs: reads text from those images",
            "ok": tesseract is not None,
            "detail": tesseract or "Not found on PATH",
            "fix": "Windows: install from https://github.com/UB-Mannheim/tesseract/wiki "
            "Mac: brew install tesseract",
        }
    )

    required_ok = all(s["ok"] for s in steps if not s.get("optional"))

    return {
        "ready": required_ok,
        "platform": os_name,
        "launcher": launcher,
        "setup_launcher": setup_launcher,
        "project_root": str(root.resolve()),
        "steps": steps,
    }
