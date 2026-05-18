#!/usr/bin/env python3
"""
Invoice Splitter - Split large PDF files into individual invoices
Handles both text-based and image-based (scanned) PDFs with AI-powered detection
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from ocr_paths import configure_ocr_path
import requests
from pdf2image import convert_from_path
from pydantic import BaseModel, ConfigDict, Field
from PyPDF2 import PdfReader, PdfWriter

# Load OPENAI_API_KEY (and other vars) from .env next to this file so CLI runs work from any cwd.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
configure_ocr_path()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent


def default_day_output_dir() -> Path:
    """Default folder for split invoices: processed/<local YYYY-MM-DD>/ under this project."""
    return _PROJECT_ROOT / "processed" / date.today().isoformat()


def default_day_discard_dir() -> Path:
    """Non-invoice pages (summary, boilerplate): processed/<local YYYY-MM-DD>/discard/."""
    return default_day_output_dir() / "discard"


def default_day_input_dir() -> Path:
    """Dropped/uploaded originals for today: input/<local YYYY-MM-DD>/."""
    return _PROJECT_ROOT / "input" / date.today().isoformat()


def open_path_in_explorer(path: Path) -> None:
    """Open a folder in the system file manager (macOS Finder, Windows Explorer, etc.)."""
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "darwin":
            import subprocess

            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":
            import subprocess

            subprocess.run(["explorer", str(path)], check=False)
        else:
            import subprocess

            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        logger.warning("Could not open folder automatically: %s", e)


# Vendor-agnostic rules shared across all LLM prompts (no per-vendor anchor phrases).
SPLITTING_RULES = """
You classify every page of a multi-page PDF. Each page belongs to exactly one category:

1) INVOICE PACKET (invoices[]): A contiguous range that forms ONE payable bill for accounts payable.
   It begins where a new single bill is introduced (primary billing header for one transaction).
   Include all pages that belong only to that same bill: line items, fee tables, delivery receipts,
   proof-of-delivery, supporting documents, or attachments that lack their own separate bill identity.
   Extend end_page through those continuation pages. Do not start a new invoice on supporting-only
   or fee-detail-only pages.

2) DISCARD (discards[]): Pages that are not a billable invoice and should not be forwarded for AP:
   - summary / cover / manifest / index listing multiple separate bills or shipments in one table
   - global boilerplate: payment instructions, remittance info, or legal text for the whole mailing
     with no single-invoice identity
   - other clearly non-invoice administrative pages

Infer from document structure (one bill vs many vs none), not vendor-specific keywords.
Partition: every page 1..N appears in exactly one invoices[] or discards[] range. No gaps, no overlaps.
A page listed in discards[] must NOT appear in any invoices[] range, and vice versa.
When unsure about a boundary, keep ambiguous continuation pages with the preceding invoice packet.
Pages with the same bill identifier (invoice number, load number, etc.) belong in one packet even when
separated by blank or non-billable pages.
""".strip()

# Pages with less extracted text than this are treated as blank separators (not a new bill).
MIN_BILLABLE_PAGE_CHARS = 20

_INVOICE_NUMBER_RE = re.compile(
    r"(?:invoice|inv\.?)\s*(?:no\.?|number|#)\s*[:#]?\s*([A-Z0-9][-A-Z0-9_/]*)",
    re.IGNORECASE,
)
_LOAD_NUMBER_RE = re.compile(
    r"load\s*(?:no\.?|number|#)\s*[:#]?\s*([A-Z0-9][-A-Z0-9_/]*)",
    re.IGNORECASE,
)


# --- Tunables: coverage vs. cost ---
# Single-call path when total prompt payload stays under this (chars, rough budget).
FULL_DOC_CHAR_BUDGET = 70_000
# Per-page cap when building the single-call prompt.
PER_PAGE_CHAR_CAP_SINGLE = 4_000
# Batched boundary detection: max chars of snippets per request (incl. markers).
BOUNDARY_BATCH_CHAR_BUDGET = 32_000
# Snippet length per page for boundary batches (keep low for many pages).
BOUNDARY_SNIPPET_CHARS = 900
# Context page before each batch (so page-boundary at batch start is visible).
BOUNDARY_CONTEXT_PREV_CHARS = 400
# Metadata enrichment: max chars for the "catalog" of segment first pages.
METADATA_BATCH_CHAR_BUDGET = 48_000
# First-page excerpt per segment for vendor / invoice # extraction.
METADATA_FIRST_PAGE_CHARS = 2_500


class InvoiceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    vendor: str
    invoice_number: str


class DiscardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    kind: str = Field(
        description="summary for cover/manifest/index; boilerplate for global payment/legal pages; other otherwise"
    )


class InvoiceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoices: List[InvoiceRecord]


class SplitAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoices: List[InvoiceRecord]
    discards: List[DiscardRecord]


class DiscardListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discards: List[DiscardRecord]


class BoundaryBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Required for strict JSON schema consumers; may be empty when no new starts in range.
    starts_in_batch: List[int]


def sanitize_filename_component(value: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", value.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "UNKNOWN"


def pages_from_marked_text(text: str) -> List[Tuple[int, str]]:
    """
    Split text produced by this tool (markers --- PAGE n ---) into (page_num, body).
    If no markers, treat entire blob as page 1.
    """
    text = text.strip()
    marker = re.compile(r"(?:^|\n)--- PAGE (\d+) ---\s*", re.MULTILINE)
    matches = list(marker.finditer(text))
    if not matches:
        return [(1, text)]

    pages: List[Tuple[int, str]] = []
    for i, m in enumerate(matches):
        page_num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        pages.append((page_num, text[start:end].strip()))
    pages.sort(key=lambda x: x[0])
    return pages


def starts_to_segments(sorted_starts: List[int], total_pages: int) -> List[Tuple[int, int]]:
    """1-based inclusive segments from sorted unique start pages (does not assume page 1)."""
    if total_pages < 1:
        return []
    cleaned = sorted({s for s in sorted_starts if 1 <= s <= total_pages})
    if not cleaned:
        return []
    segments: List[Tuple[int, int]] = []
    for i, s in enumerate(cleaned):
        nxt_end = cleaned[i + 1] - 1 if i + 1 < len(cleaned) else total_pages
        end = min(max(nxt_end, s), total_pages)
        segments.append((s, end))
    return segments


def _normalize_ranges(
    rows: List[Dict[str, Any]], label: str, total_pages: int
) -> Tuple[List[Tuple[int, int]], List[str]]:
    """Parse and validate range dicts; return (ranges, errors)."""
    ranges: List[Tuple[int, int]] = []
    errors: List[str] = []
    for i, row in enumerate(rows):
        try:
            s = int(row["start_page"])
            e = int(row["end_page"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label} index {i}: invalid start_page/end_page")
            continue
        if s < 1 or e < s or e > total_pages or s > total_pages:
            errors.append(
                f"{label} index {i}: out-of-range pages start={s} end={e} (total_pages={total_pages})"
            )
            continue
        ranges.append((s, e))
    return ranges, errors


def _pages_covered_by_rows(
    rows: List[Dict[str, Any]], use_page_list: bool
) -> Tuple[set[int], List[str]]:
    """Return page numbers covered by rows; optional page_list on invoice rows."""
    covered: set[int] = set()
    errors: List[str] = []
    for i, row in enumerate(rows):
        try:
            if use_page_list and row.get("page_list"):
                pages = {int(p) for p in row["page_list"]}
            else:
                s, e = int(row["start_page"]), int(row["end_page"])
                pages = set(range(s, e + 1))
        except (KeyError, TypeError, ValueError):
            errors.append(f"Row index {i}: invalid page coverage")
            continue
        covered |= pages
    return covered, errors


def validate_split_partition(
    invoices: List[Dict[str, Any]],
    discards: List[Dict[str, Any]],
    total_pages: int,
) -> Tuple[bool, List[str]]:
    """
    Ensure pages 1..total_pages are covered exactly once by invoice + discard ranges.
    Supports non-contiguous invoice page_list (e.g. pages 3 and 5 with blank 4 discarded).
    """
    errors: List[str] = []
    if total_pages < 1:
        return False, ["PDF has no pages"]

    _, inv_err = _normalize_ranges(invoices, "invoice", total_pages)
    _, dis_err = _normalize_ranges(discards, "discard", total_pages)
    errors.extend(inv_err)
    errors.extend(dis_err)
    if errors:
        return False, errors

    if not invoices and not discards:
        return False, ["No invoice or discard ranges returned from model"]

    use_page_list = any(inv.get("page_list") for inv in invoices)
    inv_pages, inv_cov_err = _pages_covered_by_rows(invoices, use_page_list)
    dis_pages, dis_cov_err = _pages_covered_by_rows(discards, False)
    errors.extend(inv_cov_err)
    errors.extend(dis_cov_err)
    if errors:
        return False, errors

    overlap = inv_pages & dis_pages
    if overlap:
        errors.append(f"Invoice and discard overlap on pages: {sorted(overlap)}")
        return False, errors

    covered = inv_pages | dis_pages
    expected = set(range(1, total_pages + 1))
    missing = expected - covered
    extra = covered - expected
    if missing:
        errors.append(f"Uncovered pages: {sorted(missing)}")
        return False, errors
    if extra:
        errors.append(f"Out-of-range pages in partition: {sorted(extra)}")
        return False, errors

    if not inv_pages:
        errors.append("No invoice pages (at least one billable packet required)")
        return False, errors

    return True, []


def reconcile_split_with_discards(
    invoices: List[Dict[str, Any]],
    discards: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Remove discard pages from invoice ranges and split invoices into contiguous runs.
    Fixes common model mistakes where summary pages overlap the first invoice packet.
    """
    discard_pages: set[int] = set()
    for d in discards:
        try:
            for p in range(int(d["start_page"]), int(d["end_page"]) + 1):
                discard_pages.add(p)
        except (KeyError, TypeError, ValueError):
            continue

    reconciled: List[Dict[str, Any]] = []
    for inv in invoices:
        try:
            s, e = int(inv["start_page"]), int(inv["end_page"])
        except (KeyError, TypeError, ValueError):
            reconciled.append(inv)
            continue
        billable = [p for p in range(s, e + 1) if p not in discard_pages]
        if not billable:
            continue
        run_start = billable[0]
        prev = billable[0]
        for p in billable[1:]:
            if p == prev + 1:
                prev = p
                continue
            reconciled.append(
                {
                    **inv,
                    "start_page": run_start,
                    "end_page": prev,
                }
            )
            run_start = p
            prev = p
        reconciled.append({**inv, "start_page": run_start, "end_page": prev})

    return reconciled, discards


def extract_bill_identifier_from_text(text: str) -> Optional[str]:
    """Best-effort single-bill identifier from page text (vendor-agnostic)."""
    for pattern in (_INVOICE_NUMBER_RE, _LOAD_NUMBER_RE):
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    return None


def looks_like_multi_bill_index(text: str) -> bool:
    """True when the page lists many bills (cover manifest / print summary), not one payable packet."""
    ids = set()
    for pattern in (_INVOICE_NUMBER_RE, _LOAD_NUMBER_RE):
        ids.update(m.group(1).upper() for m in pattern.finditer(text))
    if len(ids) >= 2:
        return True
    upper = text.upper()
    return bool(
        re.search(r"\bSUMMARY\b", upper)
        and re.search(r"\b(INVOICE|BILLS?|MANIFEST|INDEX|REPORT)\b", upper)
        and not extract_bill_identifier_from_text(text)
    )


def discard_page_set(discards: List[Dict[str, Any]]) -> set[int]:
    pages: set[int] = set()
    for d in discards:
        try:
            for p in range(int(d["start_page"]), int(d["end_page"]) + 1):
                pages.add(p)
        except (KeyError, TypeError, ValueError):
            continue
    return pages


def effective_discard_pages(
    discards: List[Dict[str, Any]], pages: List[Tuple[int, str]]
) -> set[int]:
    """
    Discard pages used during packet refinement: always summary/boilerplate;
    other/blank only when the page has little or no extractable text.
    """
    page_map = {p: t for p, t in pages}
    result: set[int] = set()
    for d in discards:
        kind = str(d.get("kind", "other")).lower()
        try:
            span = range(int(d["start_page"]), int(d["end_page"]) + 1)
        except (KeyError, TypeError, ValueError):
            continue
        for p in span:
            text = page_map.get(p, "")
            if kind in ("summary", "boilerplate"):
                result.add(p)
            elif len(text.strip()) < MIN_BILLABLE_PAGE_CHARS:
                result.add(p)
    return result


def invoice_page_list(invoice: Dict[str, Any]) -> List[int]:
    """1-based page numbers to include in an output invoice PDF."""
    if "page_list" in invoice and invoice["page_list"]:
        return [int(p) for p in invoice["page_list"]]
    return list(range(int(invoice["start_page"]), int(invoice["end_page"]) + 1))


def merge_invoices_by_identifier(
    invoices: List[Dict[str, Any]],
    discards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge split segments that share the same vendor + bill identifier."""
    discard_pages = discard_page_set(discards)
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    passthrough: List[Dict[str, Any]] = []

    for inv in sorted(invoices, key=lambda x: int(x.get("start_page", 0))):
        inv_no = str(inv.get("invoice_number", "")).strip()
        vendor = str(inv.get("vendor", "Unknown")).strip()
        if not inv_no or inv_no.upper() == "UNKNOWN":
            passthrough.append(inv)
            continue
        key = (vendor.upper(), inv_no.upper())
        groups.setdefault(key, []).append(inv)

    merged: List[Dict[str, Any]] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        page_set: set[int] = set()
        for g in group:
            for p in range(int(g["start_page"]), int(g["end_page"]) + 1):
                if p not in discard_pages:
                    page_set.add(p)
        if not page_set:
            continue
        pages_sorted = sorted(page_set)
        merged.append(
            {
                **group[0],
                "start_page": pages_sorted[0],
                "end_page": pages_sorted[-1],
                "page_list": pages_sorted,
            }
        )

    merged.extend(passthrough)
    merged.sort(key=lambda x: int(x["start_page"]))
    return merged


def refine_invoice_packets_from_pages(
    pages: List[Tuple[int, str]],
    discards: List[Dict[str, Any]],
    model_invoices: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Rebuild invoice packets by walking pages in order: same bill identifier or
    continuation pages (no new identifier) stay in one packet across blank/discarded gaps.
    """
    discard_pages = effective_discard_pages(discards, pages)
    vendor_by_id: Dict[str, str] = {}
    for inv in model_invoices:
        inv_no = str(inv.get("invoice_number", "")).strip()
        if inv_no and inv_no.upper() != "UNKNOWN":
            vendor_by_id[inv_no.upper()] = str(inv.get("vendor", "Unknown"))

    packets: List[Tuple[str, List[int]]] = []
    current_norm: Optional[str] = None
    current_label: Optional[str] = None
    current_pages: List[int] = []
    identified_pages = 0

    for pnum, text in sorted(pages, key=lambda x: x[0]):
        if pnum in discard_pages:
            continue
        stripped = text.strip()
        if len(stripped) < MIN_BILLABLE_PAGE_CHARS:
            continue

        bill_id = extract_bill_identifier_from_text(stripped)
        if bill_id:
            identified_pages += 1
            norm = bill_id.upper()
            if current_norm is not None and norm != current_norm:
                packets.append((current_label or current_norm, current_pages))
                current_pages = [pnum]
                current_norm = norm
                current_label = bill_id
            elif current_norm == norm:
                current_pages.append(pnum)
            else:
                current_norm = norm
                current_label = bill_id
                current_pages = [pnum]
        elif current_pages:
            if looks_like_multi_bill_index(stripped):
                packets.append((current_label or current_norm, current_pages))
                current_norm = None
                current_label = None
                current_pages = []
                continue
            current_pages.append(pnum)

    if current_norm and current_pages:
        packets.append((current_label or current_norm, current_pages))

    # Use text walk when we found identifiers on a meaningful share of billable pages.
    billable_count = sum(
        1
        for pnum, text in pages
        if pnum not in discard_pages and len(text.strip()) >= MIN_BILLABLE_PAGE_CHARS
    )
    if identified_pages < 2 or (billable_count and identified_pages / billable_count < 0.25):
        return merge_invoices_by_identifier(model_invoices, discards)

    refined: List[Dict[str, Any]] = []
    for bill_id, plist in packets:
        refined.append(
            {
                "vendor": vendor_by_id.get(bill_id.upper(), "Unknown"),
                "invoice_number": bill_id,
                "start_page": min(plist),
                "end_page": max(plist),
                "page_list": plist,
            }
        )
    return refined


def build_final_discards(
    pages: List[Tuple[int, str]],
    invoices: List[Dict[str, Any]],
    model_discards: List[Dict[str, Any]],
    total_pages: int,
) -> List[Dict[str, Any]]:
    """
    Build discard ranges from refined invoices: summary/boilerplate from model plus
    blank/index pages not assigned to any invoice packet.
    """
    inv_pages: set[int] = set()
    for inv in invoices:
        inv_pages.update(invoice_page_list(inv))

    page_map = {p: t for p, t in pages}
    discard_pages: Dict[int, str] = {}

    for d in model_discards:
        kind = str(d.get("kind", "other")).lower()
        if kind not in ("summary", "boilerplate"):
            continue
        try:
            for p in range(int(d["start_page"]), int(d["end_page"]) + 1):
                if p not in inv_pages and 1 <= p <= total_pages:
                    discard_pages[p] = kind
        except (KeyError, TypeError, ValueError):
            continue

    for pnum in range(1, total_pages + 1):
        if pnum in inv_pages or pnum in discard_pages:
            continue
        text = page_map.get(pnum, "")
        stripped = text.strip()
        if len(stripped) < MIN_BILLABLE_PAGE_CHARS:
            discard_pages[pnum] = "other"
        elif looks_like_multi_bill_index(stripped):
            discard_pages[pnum] = "summary"

    if not discard_pages:
        return []

    discards: List[Dict[str, Any]] = []
    sorted_pages = sorted(discard_pages)
    start = sorted_pages[0]
    prev = start
    kind = discard_pages[start]
    for p in sorted_pages[1:]:
        if p == prev + 1 and discard_pages[p] == kind:
            prev = p
            continue
        discards.append({"start_page": start, "end_page": prev, "kind": kind})
        start = p
        prev = p
        kind = discard_pages[p]
    discards.append({"start_page": start, "end_page": prev, "kind": kind})
    return discards


class RunStatus(str, Enum):
    SUCCESS = "success"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


@dataclass
class RunResult:
    """Outcome of one split_pdf run — read this instead of logs."""

    status: RunStatus
    input_pdf: Path
    output_dir: Path
    discard_dir: Path
    total_pages: int
    invoice_files: List[Path] = field(default_factory=list)
    discard_files: List[Path] = field(default_factory=list)
    review_file: Optional[Path] = None
    manifest_path: Optional[Path] = None
    report_path: Optional[Path] = None
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    invoices: List[Dict[str, Any]] = field(default_factory=list)
    discards: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == RunStatus.SUCCESS

    def headline(self) -> str:
        if self.status == RunStatus.SUCCESS:
            n = len(self.invoice_files)
            return f"SUCCESS — {n} invoice PDF{'s' if n != 1 else ''} ready in your output folder."
        if self.status == RunStatus.NEEDS_REVIEW:
            return "NEEDS REVIEW — automatic split was not trusted; use the review file below."
        return "FAILED — nothing was split; see reasons below."


def assess_run_quality(
    invoices: List[Dict[str, Any]],
    *,
    validation_ok: bool,
    validation_errors: List[str],
) -> Tuple[RunStatus, List[str], List[str]]:
    """
    Decide pass/fail before writing invoice PDFs.
    Any hard reason => NEEDS_REVIEW (fail closed).
    """
    reasons: List[str] = []
    warnings: List[str] = []

    if not validation_ok:
        reasons.extend(validation_errors or ["Page layout validation failed."])

    numbers = [str(inv.get("invoice_number", "")).strip() for inv in invoices]
    billable = [n for n in numbers if n and n.upper() != "UNKNOWN"]
    if not billable:
        reasons.append("No invoice numbers were identified.")

    counts = Counter(n.upper() for n in billable)
    dupes = [num for num, ct in counts.items() if ct > 1]
    if dupes:
        shown = ", ".join(dupes[:8])
        suffix = "…" if len(dupes) > 8 else ""
        reasons.append(f"Duplicate invoice numbers: {shown}{suffix}")

    unknown_n = sum(1 for n in numbers if not n or n.upper() == "UNKNOWN")
    if unknown_n:
        reasons.append(
            f"{unknown_n} invoice packet(s) missing a readable invoice number."
        )

    unknown_v = sum(
        1
        for inv in invoices
        if str(inv.get("vendor", "Unknown")).strip().lower() in ("", "unknown")
    )
    if unknown_v:
        warnings.append(
            f"{unknown_v} invoice(s) have vendor listed as Unknown — quick visual check recommended."
        )

    if reasons:
        return RunStatus.NEEDS_REVIEW, reasons, warnings
    return RunStatus.SUCCESS, reasons, warnings


def _format_page_label(inv: Dict[str, Any]) -> str:
    pages = invoice_page_list(inv)
    if not pages:
        return "?"
    if len(pages) == 1:
        return f"p{pages[0]}"
    if pages[-1] - pages[0] + 1 == len(pages):
        return f"p{pages[0]}-{pages[-1]}"
    return "p" + ",".join(str(p) for p in pages)


def format_run_report(result: RunResult) -> str:
    lines: List[str] = [
        "INVOICE SPLITTER — RUN REPORT",
        "=" * 50,
        "",
        result.headline(),
        "",
        f"Input file:    {result.input_pdf.name}",
        f"Total pages:   {result.total_pages}",
        f"Output folder: {result.output_dir}",
        "",
    ]

    if result.status == RunStatus.SUCCESS:
        lines.append(f"INVOICES FOR AP ({len(result.invoice_files)} files):")
        lines.append("(Send these to your accounting / AP workflow.)")
        lines.append("")
        for i, inv in enumerate(result.invoices):
            fname = (
                result.invoice_files[i].name
                if i < len(result.invoice_files)
                else "(file missing)"
            )
            lines.append(
                f"  • {fname}"
            )
            lines.append(
                f"      {inv.get('vendor', 'Unknown')}  "
                f"Invoice #{inv.get('invoice_number', '?')}  "
                f"({_format_page_label(inv)} in original)"
            )
        lines.append("")
        if result.discard_files or result.discards:
            lines.append("DISCARDED — NOT FOR AP (discard/ folder):")
            lines.append("(Summary pages, blanks, boilerplate — do not forward.)")
            lines.append("")
            for path in result.discard_files:
                lines.append(f"  • {path.name}")
            for d in result.discards:
                if d["start_page"] == d["end_page"]:
                    pg = f"page {d['start_page']}"
                else:
                    pg = f"pages {d['start_page']}-{d['end_page']}"
                lines.append(f"  • {pg}  ({d.get('kind', 'other')})")
            lines.append("")
        lines.append("NEXT STEP:")
        lines.append(f"  Open: {result.output_dir}")
        lines.append("  Use only the output_*.pdf files (not the discard/ folder).")
    elif result.status == RunStatus.NEEDS_REVIEW:
        lines.append("WHAT HAPPENED:")
        lines.append("  The program could not split this PDF with enough confidence.")
        lines.append("  Individual invoice files were NOT created (fail-safe).")
        lines.append("")
        lines.append("WHAT TO DO:")
        if result.review_file:
            lines.append(f"  1. Open this file (full original): {result.review_file.name}")
            lines.append(f"     Location: {result.review_file.parent}")
        lines.append("  2. Split manually or ask someone with access to fix the file.")
        lines.append("")
        lines.append("WHY:")
        for r in result.reasons:
            lines.append(f"  • {r}")
    else:
        lines.append("WHY:")
        for r in result.reasons:
            lines.append(f"  • {r}")

    if result.warnings and result.status == RunStatus.SUCCESS:
        lines.append("")
        lines.append("OPTIONAL SPOT-CHECK:")
        for w in result.warnings:
            lines.append(f"  • {w}")

    if result.manifest_path:
        lines.append("")
        lines.append(f"Technical log (optional): {result.manifest_path.name}")

    lines.append("")
    return "\n".join(lines)


def print_run_summary(result: RunResult) -> None:
    """Plain-English summary for the operator (always shown)."""
    border = "=" * 50
    print()
    print(border)
    print(result.headline())
    print(border)
    if result.status == RunStatus.SUCCESS:
        print(f"\n  {len(result.invoice_files)} invoice PDF(s) → {result.output_dir}")
        if result.discard_files:
            print(f"  {len(result.discard_files)} discarded page file(s) → {result.discard_dir}")
        print("\n  Open the output folder and use the files that start with output_")
    elif result.status == RunStatus.NEEDS_REVIEW:
        print("\n  No invoice files were created.")
        if result.review_file:
            print(f"  Open for manual handling: {result.review_file}")
        print("\n  Reasons:")
        for r in result.reasons:
            print(f"    - {r}")
    else:
        print("\n  Reasons:")
        for r in result.reasons:
            print(f"    - {r}")
    if result.warnings:
        print("\n  Notes:")
        for w in result.warnings:
            print(f"    - {w}")
    if result.report_path:
        print(f"\n  Full report saved to:\n  {result.report_path}")
    print()


def write_run_report(result: RunResult) -> Path:
    stem = sanitize_filename_component(result.input_pdf.stem)
    report_path = result.output_dir / f"RESULTS_{stem}.txt"
    report_path.write_text(format_run_report(result), encoding="utf-8")
    result.report_path = report_path
    return report_path


class InvoiceSplitter:
    """Main class for splitting invoices from PDFs"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. "
                "Set OPENAI_API_KEY environment variable or pass api_key parameter."
            )

        self.model = "gpt-4o-mini"
        self.api_url = "https://api.openai.com/v1/chat/completions"

    def _json_schema_response_format(self, name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema,
            },
        }

    def _chat_completion_json(
        self,
        user_prompt: str,
        response_model: type[BaseModel],
        schema_name: str,
        *,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> BaseModel:
        schema = response_model.model_json_schema()
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": self._json_schema_response_format(schema_name, schema),
        }
        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        if not content:
            raise ValueError("Empty message content from model")
        data = json.loads(content)
        return response_model.model_validate(data)

    def _is_text_based_pdf(self, pdf_path: str) -> bool:
        try:
            reader = PdfReader(pdf_path)
            first_page = reader.pages[0]
            text = first_page.extract_text()
            return len(text.strip()) > 50
        except Exception as e:
            logger.warning("Error checking PDF type: %s. Assuming image-based.", e)
            return False

    def _extract_text_based(self, pdf_path: str) -> str:
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                text += f"\n--- PAGE {page_num + 1} ---\n{page_text}"
            return text
        except Exception as e:
            logger.error("Error extracting text from text-based PDF: %s", e)
            raise

    def _extract_image_based(self, pdf_path: str) -> str:
        try:
            import pytesseract  # lazy: keeps setup/UI importable; needs >=0.3.13 on Python 3.14+

            logger.info("Detected image-based PDF. Running OCR...")
            images = convert_from_path(pdf_path)
            text = ""
            for page_num, image in enumerate(images, 1):
                logger.info("  OCR processing page %s/%s...", page_num, len(images))
                page_text = pytesseract.image_to_string(image)
                text += f"\n--- PAGE {page_num} ---\n{page_text}"
            return text
        except Exception as e:
            logger.error("Error extracting text with OCR: %s", e)
            logger.error(
                "Ensure Tesseract OCR is installed:\n"
                "  Linux: sudo apt-get install tesseract-ocr\n"
                "  Mac: brew install tesseract\n"
                "  Windows: Download installer from "
                "https://github.com/UB-Mannheim/tesseract/wiki"
            )
            raise

    def _extract_text(self, pdf_path: str) -> str:
        logger.info("Analyzing PDF: %s", pdf_path)
        if self._is_text_based_pdf(pdf_path):
            logger.info("Detected text-based PDF")
            return self._extract_text_based(pdf_path)
        return self._extract_image_based(pdf_path)

    def _align_pages_with_pdf(
        self, pages: List[Tuple[int, str]], total_pages: int
    ) -> List[Tuple[int, str]]:
        """
        Ensure we have exactly total_pages entries, renumbered 1..total_pages when counts match
        but labels drift; otherwise fail fast in caller by returning as-is and letting validation catch it.
        """
        if not pages:
            return [(1, "")]
        by_num = {p: t for p, t in pages}
        if len(by_num) != len(pages):
            logger.warning("Duplicate page markers in extracted text; last wins per page label.")
        ordered = [by_num[k] for k in sorted(by_num)]
        if len(ordered) == total_pages:
            return [(i + 1, ordered[i]) for i in range(total_pages)]
        if len(ordered) < total_pages:
            logger.warning(
                "Extracted %s page(s) but PDF has %s; padding empty tail pages.",
                len(ordered),
                total_pages,
            )
            out = [(i + 1, ordered[i]) if i < len(ordered) else (i + 1, "") for i in range(total_pages)]
            return out
        logger.warning(
            "Extracted %s page(s) but PDF has %s; truncating to PDF length.",
            len(ordered),
            total_pages,
        )
        return [(i + 1, ordered[i]) for i in range(total_pages)]

    def _single_call_analyze(
        self, pages: List[Tuple[int, str]], total_pages: int
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        lines: List[str] = [
            "You are an accounts-payable document analyst. Split this PDF into billable invoice packets and discard pages.",
            f"Total pages: {total_pages}. Page markers in the source are authoritative.",
            "Return JSON matching the schema: invoices[] (start_page, end_page, vendor, invoice_number) and discards[] (start_page, end_page, kind).",
            "For discards, kind must be one of: summary, boilerplate, other.",
            SPLITTING_RULES,
            "",
            "PDF text by page:",
        ]
        for pnum, body in pages:
            chunk = body[:PER_PAGE_CHAR_CAP_SINGLE]
            lines.append(f"\n--- PAGE {pnum} ---\n{chunk}")
        prompt = "\n".join(lines)
        parsed = self._chat_completion_json(
            prompt, SplitAnalysisResponse, "split_analysis", max_tokens=8192, temperature=0.1
        )
        return (
            [inv.model_dump() for inv in parsed.invoices],
            [d.model_dump() for d in parsed.discards],
        )

    def _boundary_batches(self, pages: List[Tuple[int, str]]) -> List[Tuple[int, int, str]]:
        """Yield (first_page, last_page, prompt_body) batches covering all pages."""
        batches: List[Tuple[int, int, str]] = []
        i = 0
        n = len(pages)
        while i < n:
            first = pages[i][0]
            parts: List[str] = []
            size = 0
            j = i
            if i > 0:
                prev_num, prev_text = pages[i - 1]
                prev_snip = prev_text[:BOUNDARY_CONTEXT_PREV_CHARS]
                block = f"[context page {prev_num}]\n{prev_snip}\n"
                parts.append(block)
                size += len(block)

            while j < n:
                pnum, body = pages[j]
                snip = body[:BOUNDARY_SNIPPET_CHARS]
                block = f"--- PAGE {pnum} ---\n{snip}\n"
                if size + len(block) > BOUNDARY_BATCH_CHAR_BUDGET and j > i:
                    break
                parts.append(block)
                size += len(block)
                j += 1
            if j == i:
                # force at least one page per batch
                pnum, body = pages[i]
                snip = body[:BOUNDARY_SNIPPET_CHARS]
                parts.append(f"--- PAGE {pnum} ---\n{snip}\n")
                j = i + 1
            last = pages[j - 1][0]
            batches.append((first, last, "\n".join(parts)))
            i = j
        return batches

    def _detect_discard_ranges(self, pages: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """Identify non-invoice discard ranges (summary, boilerplate, etc.)."""
        lines: List[str] = [
            "Identify pages that are NOT billable invoices and should be discarded from AP processing.",
            f"Total PDF pages: {len(pages)}. Return discards[] only (start_page, end_page, kind).",
            "kind: summary (cover/manifest/index), boilerplate (global payment/legal), or other.",
            "Do not list invoice packet pages. If no discard pages exist, return an empty discards array.",
            SPLITTING_RULES,
            "",
            "PDF text by page:",
        ]
        for pnum, body in pages:
            snip = body[:BOUNDARY_SNIPPET_CHARS]
            lines.append(f"\n--- PAGE {pnum} ---\n{snip}")

        prompt = "\n".join(lines)
        # Batch if very large
        if len(prompt) > BOUNDARY_BATCH_CHAR_BUDGET * 3:
            discards: List[Dict[str, Any]] = []
            for batch_first, batch_last, body in self._boundary_batches(pages):
                batch_prompt = (
                    f"Pages {batch_first}-{batch_last} of {len(pages)}. Return discards[] only.\n"
                    f"{SPLITTING_RULES}\n\n{body}"
                )
                parsed = self._chat_completion_json(
                    batch_prompt, DiscardListResponse, "discard_list", max_tokens=1024, temperature=0.0
                )
                discards.extend(d.model_dump() for d in parsed.discards)
            return discards

        parsed = self._chat_completion_json(
            prompt, DiscardListResponse, "discard_list", max_tokens=2048, temperature=0.0
        )
        return [d.model_dump() for d in parsed.discards]

    def _detect_starts_batched(self, pages: List[Tuple[int, str]]) -> List[int]:
        starts: set[int] = set()
        for batch_first, batch_last, body in self._boundary_batches(pages):
            prompt = (
                "You detect where a NEW billable invoice packet begins in a multi-invoice PDF.\n"
                f"This batch shows snippets for global pages {batch_first} through {batch_last} "
                f"(total PDF pages: {len(pages)}).\n"
                "A context line from the page before the batch may appear as [context page N].\n"
                "Return starts_in_batch: sorted unique global page numbers in this inclusive range "
                "where a new single payable bill starts (primary billing header for one transaction).\n"
                "Do NOT list: summary/manifest/index pages, global boilerplate, fee-only or supporting-only "
                "continuation pages, or pages that belong to the previous invoice packet.\n"
                "Do not assume page 1 is an invoice. Only list pages in "
                f"{batch_first}-{batch_last}.\n\n"
                f"{body}"
            )
            parsed = self._chat_completion_json(
                prompt, BoundaryBatchResponse, "boundary_batch", max_tokens=1024, temperature=0.0
            )
            for s in parsed.starts_in_batch:
                if batch_first <= s <= batch_last:
                    starts.add(s)
        return sorted(starts)

    def _metadata_for_segments(
        self, pages: List[Tuple[int, str]], segments: List[Tuple[int, int]]
    ) -> List[Dict[str, Any]]:
        """Assign vendor / invoice_number for each segment using first-page excerpts (batched)."""
        page_map = {p: t for p, t in pages}
        out: List[Dict[str, Any]] = []
        buf_parts: List[str] = []
        buf_size = 0
        buf_segs: List[Tuple[int, int]] = []

        def flush() -> None:
            nonlocal buf_parts, buf_size, buf_segs
            if not buf_segs:
                return
            catalog = "\n".join(buf_parts)
            prompt = (
                "For each invoice segment below, return vendor and invoice_number.\n"
                "The segment may span multiple pages; use the primary billing header page—the page "
                "that introduces this single bill. Ignore fee tables and supporting-only pages for numbering.\n"
                "Rules: respond with JSON matching schema. start_page/end_page must match exactly.\n"
                "Vendor: concise company name. Invoice number: the clearest single-bill identifier printed "
                "(invoice number, load number, or reference); if missing use UNKNOWN.\n\n"
                f"{catalog}"
            )
            parsed = self._chat_completion_json(
                prompt, InvoiceListResponse, "invoice_list", max_tokens=4096, temperature=0.0
            )
            by_key = {(r.start_page, r.end_page): r for r in parsed.invoices}
            for s, e in buf_segs:
                rec = by_key.get((s, e))
                if rec is None:
                    out.append(
                        {
                            "start_page": s,
                            "end_page": e,
                            "vendor": "Unknown",
                            "invoice_number": "UNKNOWN",
                        }
                    )
                else:
                    out.append(rec.model_dump())
            buf_parts = []
            buf_size = 0
            buf_segs = []

        for s, e in segments:
            excerpt = page_map.get(s, "")[:METADATA_FIRST_PAGE_CHARS]
            block = f"Segment pages {s}-{e} (inclusive). First-page excerpt:\n{excerpt}\n---\n"
            if buf_size + len(block) > METADATA_BATCH_CHAR_BUDGET and buf_segs:
                flush()
            buf_parts.append(block)
            buf_size += len(block)
            buf_segs.append((s, e))
        flush()
        out.sort(key=lambda x: x["start_page"])
        return out

    def _analyze_invoices_structured(
        self, text: str, pdf_path: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        raw_pages = pages_from_marked_text(text)
        pages = self._align_pages_with_pdf(raw_pages, total_pages)

        rough_single = sum(len(t[:PER_PAGE_CHAR_CAP_SINGLE]) + 32 for _, t in pages) + 2048
        debug: Dict[str, Any] = {
            "path": pdf_path,
            "total_pages": total_pages,
            "strategy": "single_call" if rough_single <= FULL_DOC_CHAR_BUDGET else "chunked",
        }

        if rough_single <= FULL_DOC_CHAR_BUDGET:
            invoices, discards = self._single_call_analyze(pages, total_pages)
            debug["invoice_count"] = len(invoices)
            debug["discard_count"] = len(discards)
            return invoices, discards, debug

        discards = self._detect_discard_ranges(pages)
        discard_pages = {
            p for d in discards for p in range(int(d["start_page"]), int(d["end_page"]) + 1)
        }
        starts = self._detect_starts_batched(pages)
        starts = [s for s in starts if s not in discard_pages]
        segments = starts_to_segments(starts, total_pages)
        # Trim segment ends so they do not swallow discard pages
        trimmed: List[Tuple[int, int]] = []
        for s, e in segments:
            while e >= s and e in discard_pages:
                e -= 1
            if e >= s:
                trimmed.append((s, e))
        debug["detected_starts"] = starts
        debug["segment_count"] = len(trimmed)
        debug["discard_count"] = len(discards)
        invoices = self._metadata_for_segments(pages, trimmed)
        return invoices, discards, debug

    def _write_manifest(
        self,
        manifest_path: Path,
        *,
        input_pdf: str,
        total_pages: int,
        analysis_debug: Dict[str, Any],
        invoices: List[Dict[str, Any]],
        discards: List[Dict[str, Any]],
        validation_ok: bool,
        validation_errors: List[str],
        discard_dir: Optional[Path] = None,
        raw_model_notes: Optional[str] = None,
    ) -> Path:
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input_pdf": str(Path(input_pdf).resolve()),
            "output_dir": str(manifest_path.parent.resolve()),
            "discard_dir": str(discard_dir.resolve()) if discard_dir else None,
            "model": self.model,
            "total_pages": total_pages,
            "validation_ok": validation_ok,
            "validation_errors": validation_errors,
            "analysis": analysis_debug,
            "invoices": invoices,
            "discards": discards,
            "notes": raw_model_notes,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("Wrote manifest: %s", manifest_path)
        return manifest_path

    def _make_unique_output_path(
        self, output_dir: Path, vendor: str, invoice_number: str, start_page: int, end_page: int
    ) -> Path:
        v = sanitize_filename_component(vendor)
        inv = sanitize_filename_component(invoice_number)
        base = f"{v}_{inv}"
        if not hasattr(self, "_filename_counts"):
            self._filename_counts = {}
        used: Dict[str, int] = self._filename_counts  # type: ignore[attr-defined]
        key = base.lower()
        used[key] = used.get(key, 0) + 1
        n = used[key]
        if n == 1:
            stem = f"output_{base}"
        else:
            stem = f"output_{base}_p{start_page}-{end_page}_{n}"
        return output_dir / f"{stem}.pdf"

    def _write_pages_pdf(
        self,
        reader: PdfReader,
        output_dir: Path,
        filename: str,
        start_page: int,
        end_page: int,
    ) -> Path:
        """Write 1-based inclusive page range to output_dir/filename."""
        start_idx = max(0, start_page - 1)
        end_idx = min(end_page, len(reader.pages))
        out = output_dir / filename
        writer = PdfWriter()
        for page_num in range(start_idx, end_idx):
            writer.add_page(reader.pages[page_num])
        with open(out, "wb") as f:
            writer.write(f)
        return out

    def split_pdf(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        *,
        print_summary: bool = True,
    ) -> RunResult:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        self._filename_counts = {}

        run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path(output_dir) if output_dir is not None else default_day_output_dir()
        output_dir = out
        output_dir.mkdir(parents=True, exist_ok=True)
        discard_dir = output_dir / "discard"
        discard_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = output_dir / (
            f"split_manifest_{sanitize_filename_component(pdf_path.stem)}_{run_ts}.json"
        )
        fallback_name = (
            f"output_NEEDS_REVIEW_{sanitize_filename_component(pdf_path.stem)}_{run_ts}.pdf"
        )

        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)

        def _needs_review(
            reasons: List[str],
            *,
            analysis_debug: Optional[Dict[str, Any]] = None,
            invoices: Optional[List[Dict[str, Any]]] = None,
            discards: Optional[List[Dict[str, Any]]] = None,
            validation_errors: Optional[List[str]] = None,
            warnings: Optional[List[str]] = None,
            failed: bool = False,
        ) -> RunResult:
            review_paths = self._write_fallback_single_pdf(reader, output_dir, fallback_name)
            review_file = Path(review_paths[0]) if review_paths else None
            self._write_manifest(
                manifest_path,
                input_pdf=str(pdf_path),
                total_pages=total_pages,
                analysis_debug=analysis_debug or {},
                invoices=invoices or [],
                discards=discards or [],
                validation_ok=False,
                validation_errors=validation_errors or reasons,
                discard_dir=discard_dir,
            )
            result = RunResult(
                status=RunStatus.FAILED if failed else RunStatus.NEEDS_REVIEW,
                input_pdf=pdf_path.resolve(),
                output_dir=output_dir.resolve(),
                discard_dir=discard_dir.resolve(),
                total_pages=total_pages,
                review_file=review_file,
                manifest_path=manifest_path,
                reasons=reasons,
                warnings=warnings or [],
                invoices=invoices or [],
                discards=discards or [],
            )
            write_run_report(result)
            if print_summary:
                print_run_summary(result)
            return result

        logger.info("Processing: %s", pdf_path.name)
        logger.info("Output directory: %s", output_dir.resolve())
        extracted_text = self._extract_text(str(pdf_path))

        discard_data: List[Dict[str, Any]] = []
        analysis_debug: Dict[str, Any] = {}
        try:
            invoice_data, discard_data, analysis_debug = self._analyze_invoices_structured(
                extracted_text, str(pdf_path)
            )
        except Exception as e:
            logger.error("Invoice analysis failed: %s", e)
            return _needs_review(
                [f"Could not analyze PDF: {e}"],
                analysis_debug={"error": str(e)},
                failed=True,
            )

        invoice_data, discard_data = reconcile_split_with_discards(invoice_data, discard_data)
        aligned_pages = self._align_pages_with_pdf(
            pages_from_marked_text(extracted_text), total_pages
        )
        invoice_data = refine_invoice_packets_from_pages(
            aligned_pages, discard_data, invoice_data
        )
        discard_data = build_final_discards(
            aligned_pages, invoice_data, discard_data, total_pages
        )
        analysis_debug = {**analysis_debug, "refined_from_page_text": True}
        ok, errors = validate_split_partition(invoice_data, discard_data, total_pages)
        run_status, quality_reasons, warnings = assess_run_quality(
            invoice_data, validation_ok=ok, validation_errors=errors
        )

        self._write_manifest(
            manifest_path,
            input_pdf=str(pdf_path),
            total_pages=total_pages,
            analysis_debug={
                **analysis_debug,
                "run_status": run_status.value,
                "quality_reasons": quality_reasons,
                "warnings": warnings,
            },
            invoices=invoice_data,
            discards=discard_data,
            validation_ok=ok and run_status == RunStatus.SUCCESS,
            validation_errors=errors + quality_reasons,
            discard_dir=discard_dir,
        )

        if run_status != RunStatus.SUCCESS:
            logger.error("Run not trusted for auto-split: %s", quality_reasons)
            return _needs_review(
                quality_reasons,
                analysis_debug=analysis_debug,
                invoices=invoice_data,
                discards=discard_data,
                validation_errors=errors,
                warnings=warnings,
            )

        stem = sanitize_filename_component(pdf_path.stem)
        discard_files: List[Path] = []
        for i, discard in enumerate(discard_data):
            try:
                kind = sanitize_filename_component(str(discard.get("kind", "other")))
                s = int(discard["start_page"])
                e = int(discard["end_page"])
                name = f"discard_{kind}_{stem}_p{s}-{e}_{run_ts}"
                if i > 0:
                    name += f"_{i}"
                out_path = self._write_pages_pdf(
                    reader, discard_dir, f"{name}.pdf", s, e
                )
                discard_files.append(out_path)
                logger.info("Discard: %s (pages %s-%s)", out_path.name, s, e)
            except Exception as ex:
                logger.error("Error writing discard segment: %s", ex)

        invoice_files: List[Path] = []
        written_invoices: List[Dict[str, Any]] = []
        for invoice in invoice_data:
            try:
                vendor = str(invoice.get("vendor", "Unknown"))
                invoice_number = str(invoice.get("invoice_number", "UNKNOWN"))
                pages_to_write = [
                    p
                    for p in invoice_page_list(invoice)
                    if 1 <= p <= len(reader.pages)
                ]
                if not pages_to_write:
                    continue

                out_path = self._make_unique_output_path(
                    output_dir,
                    vendor,
                    invoice_number,
                    pages_to_write[0],
                    pages_to_write[-1],
                )

                writer = PdfWriter()
                for page_one_based in pages_to_write:
                    writer.add_page(reader.pages[page_one_based - 1])

                with open(out_path, "wb") as f:
                    writer.write(f)

                logger.info("Created: %s", out_path.name)
                invoice_files.append(out_path)
                written_invoices.append(invoice)
            except Exception as e:
                logger.error("Error processing invoice row: %s", e)

        if not invoice_files:
            return _needs_review(
                ["No invoice PDFs could be written."],
                analysis_debug=analysis_debug,
                invoices=invoice_data,
                discards=discard_data,
                warnings=warnings,
            )

        result = RunResult(
            status=RunStatus.SUCCESS,
            input_pdf=pdf_path.resolve(),
            output_dir=output_dir.resolve(),
            discard_dir=discard_dir.resolve(),
            total_pages=total_pages,
            invoice_files=invoice_files,
            discard_files=discard_files,
            manifest_path=manifest_path,
            warnings=warnings,
            invoices=written_invoices,
            discards=discard_data,
        )
        write_run_report(result)
        if print_summary:
            print_run_summary(result)
        logger.info("Run complete: %s", result.headline())
        return result

    def _write_fallback_single_pdf(
        self, reader: PdfReader, output_dir: Path, name: str
    ) -> List[str]:
        out = output_dir / name
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(out, "wb") as f:
            writer.write(f)
        logger.info("Wrote fallback PDF: %s", out)
        return [str(out)]


def main():
    args = [a for a in sys.argv[1:] if a]
    open_folder = False
    quiet = False
    positional: List[str] = []
    for a in args:
        if a in ("--open", "-o"):
            open_folder = True
        elif a in ("--quiet", "-q"):
            quiet = True
        elif a.startswith("-"):
            print(f"Unknown option: {a}")
            sys.exit(2)
        else:
            positional.append(a)

    if quiet:
        logging.getLogger().setLevel(logging.WARNING)

    if not positional:
        print("Usage: python invoice_splitter.py <pdf_file> [output_dir] [options]")
        print("  Default output_dir: <this_repo>/processed/<today>/")
        print("")
        print("Options:")
        print("  --open, -o     Open the output folder when finished (macOS Finder, etc.)")
        print("  --quiet, -q    Hide detailed progress logs (summary still shown)")
        print("")
        print("Example: python invoice_splitter.py invoices.pdf --open")
        sys.exit(1)

    pdf_path = positional[0]
    output_dir = positional[1] if len(positional) > 1 else None

    try:
        splitter = InvoiceSplitter()
        result = splitter.split_pdf(pdf_path, output_dir)
        if open_folder and result.status == RunStatus.SUCCESS:
            open_path_in_explorer(result.output_dir)
        if result.status == RunStatus.SUCCESS:
            sys.exit(0)
        if result.status == RunStatus.NEEDS_REVIEW:
            sys.exit(1)
        sys.exit(2)
    except FileNotFoundError as e:
        print(f"\nERROR: {e}\n")
        sys.exit(2)
    except Exception as e:
        logger.error("Fatal error: %s", e)
        print(f"\nFAILED — {e}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
