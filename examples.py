"""
Invoice Splitter — usage examples (RunResult API).

Run: python examples.py
Requires OPENAI_API_KEY in .env and a PDF path you pass or place in test_docs/.
"""

from __future__ import annotations

import sys
from pathlib import Path

from invoice_splitter import InvoiceSplitter, RunStatus


def example_single_pdf(pdf_path: str) -> None:
    """Split one PDF; default output is processed/<today>/."""
    splitter = InvoiceSplitter()
    result = splitter.split_pdf(pdf_path, print_summary=True)

    print(result.headline())
    if result.status == RunStatus.SUCCESS:
        for path in result.invoice_files:
            print(f"  invoice: {path.name}")
        for path in result.discard_files:
            print(f"  discard: {path.name}")
    if result.report_path:
        print(f"Report: {result.report_path}")


def example_custom_output(pdf_path: str, output_dir: str) -> None:
    """Split into a specific folder."""
    splitter = InvoiceSplitter()
    result = splitter.split_pdf(pdf_path, output_dir, print_summary=False)
    print(f"{result.status.value}: {len(result.invoice_files)} invoice file(s) in {output_dir}")


def example_batch(pdf_paths: list[str]) -> None:
    """Process several PDFs; continue on failure."""
    splitter = InvoiceSplitter()
    for path in pdf_paths:
        try:
            result = splitter.split_pdf(path, print_summary=False)
            print(f"  {path}: {result.headline()}")
        except Exception as exc:
            print(f"  {path}: FAILED — {exc}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    default_pdf = root / "test_docs" / "freight.pdf"

    if len(sys.argv) > 1:
        pdf = sys.argv[1]
    elif default_pdf.is_file():
        pdf = str(default_pdf)
    else:
        print("Usage: python examples.py [path/to/invoices.pdf]")
        sys.exit(1)

    print("Example 1 — single PDF")
    example_single_pdf(pdf)
