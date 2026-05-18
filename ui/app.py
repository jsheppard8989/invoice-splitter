"""
Local web UI — drag-and-drop PDFs, process, open today's folders in Explorer/Finder.
Run: python run_ui.py
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from invoice_splitter import (
    InvoiceSplitter,
    RunStatus,
    _PROJECT_ROOT,
    default_day_discard_dir,
    default_day_input_dir,
    default_day_output_dir,
    open_path_in_explorer,
)
from ui.setup_status import get_setup_status

UI_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(UI_DIR / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB per request

logging.getLogger().setLevel(logging.WARNING)


def _folder_payload() -> Dict[str, str]:
    today = date.today().isoformat()
    return {
        "date": today,
        "input": str(default_day_input_dir()),
        "output": str(default_day_output_dir()),
        "discard": str(default_day_discard_dir()),
    }


def _result_to_dict(result: Any, saved_name: str) -> Dict[str, Any]:
    return {
        "filename": saved_name,
        "status": result.status.value,
        "headline": result.headline(),
        "invoice_count": len(result.invoice_files),
        "discard_count": len(result.discard_files),
        "reasons": result.reasons,
        "warnings": result.warnings,
        "review_file": str(result.review_file) if result.review_file else None,
        "report_path": str(result.report_path) if result.report_path else None,
        "invoice_files": [p.name for p in result.invoice_files],
    }


@app.get("/")
def index():
    return render_template("index.html", folders=_folder_payload())


@app.get("/api/setup-status")
def api_setup_status():
    status = get_setup_status()
    for key in ("input", "output", "discard"):
        Path(_folder_payload()[key]).mkdir(parents=True, exist_ok=True)
    status["folders"] = _folder_payload()
    return jsonify(status)


@app.post("/api/open-folder")
def api_open_folder():
    which = (request.json or {}).get("which") or request.args.get("which", "output")
    if which == "program":
        open_path_in_explorer(_PROJECT_ROOT)
        return jsonify({"opened": str(_PROJECT_ROOT.resolve())})
    mapping = {
        "input": default_day_input_dir,
        "output": default_day_output_dir,
        "discard": default_day_discard_dir,
    }
    fn = mapping.get(which)
    if not fn:
        return jsonify({"error": f"Unknown folder: {which}"}), 400
    path = fn()
    open_path_in_explorer(path)
    return jsonify({"opened": str(path)})


@app.post("/api/process")
def api_process():
    setup = get_setup_status()
    if not setup["ready"]:
        return (
            jsonify(
                {
                    "error": "Setup is incomplete. Fix the items in the Setup checklist above, then try again.",
                    "setup": setup,
                }
            ),
            503,
        )

    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    uploaded = request.files.getlist("files")
    if not uploaded or all(f.filename == "" for f in uploaded):
        return jsonify({"error": "No files selected"}), 400

    input_dir = default_day_input_dir()
    input_dir.mkdir(parents=True, exist_ok=True)
    default_day_output_dir().mkdir(parents=True, exist_ok=True)
    default_day_discard_dir().mkdir(parents=True, exist_ok=True)

    splitter = InvoiceSplitter()
    results: List[Dict[str, Any]] = []

    for storage in uploaded:
        if not storage.filename:
            continue
        safe = secure_filename(storage.filename)
        if not safe.lower().endswith(".pdf"):
            results.append(
                {
                    "filename": storage.filename,
                    "status": "failed",
                    "headline": "Only PDF files are supported.",
                    "invoice_count": 0,
                    "discard_count": 0,
                    "reasons": ["Not a PDF file"],
                    "warnings": [],
                }
            )
            continue

        dest = input_dir / safe
        if dest.exists():
            dest = input_dir / f"{dest.stem}_{datetime.now().strftime('%H%M%S')}{dest.suffix}"

        storage.save(dest)

        try:
            logging.getLogger("invoice_splitter").setLevel(logging.WARNING)
            run = splitter.split_pdf(str(dest), print_summary=False)
            # split_pdf prints summary; avoid double noise in server console
            results.append(_result_to_dict(run, dest.name))
        except Exception as e:
            results.append(
                {
                    "filename": dest.name,
                    "status": "failed",
                    "headline": f"FAILED — {e}",
                    "invoice_count": 0,
                    "discard_count": 0,
                    "reasons": [str(e)],
                    "warnings": [],
                }
            )

    all_ok = all(r["status"] == RunStatus.SUCCESS.value for r in results)
    any_review = any(r["status"] == RunStatus.NEEDS_REVIEW.value for r in results)

    return jsonify(
        {
            "results": results,
            "folders": _folder_payload(),
            "summary": {
                "processed": len(results),
                "success": sum(1 for r in results if r["status"] == RunStatus.SUCCESS.value),
                "needs_review": sum(
                    1 for r in results if r["status"] == RunStatus.NEEDS_REVIEW.value
                ),
                "failed": sum(1 for r in results if r["status"] == "failed"),
                "all_ok": all_ok,
                "any_review": any_review,
            },
        }
    )
