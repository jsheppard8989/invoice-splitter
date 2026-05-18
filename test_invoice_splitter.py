"""
Unit tests for Invoice Splitter
Run with: python -m pytest test_invoice_splitter.py
"""

import pytest
import tempfile
import os
from pathlib import Path
from invoice_splitter import (
    InvoiceRecord,
    InvoiceSplitter,
    pages_from_marked_text,
    starts_to_segments,
    validate_split_partition,
    reconcile_split_with_discards,
    refine_invoice_packets_from_pages,
    assess_run_quality,
    RunStatus,
    format_run_report,
    RunResult,
    sanitize_filename_component,
)


class TestInvoiceSplitter:
    """Test suite for InvoiceSplitter"""

    def test_initialization_with_env_key(self):
        """Test initialization with environment variable"""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        splitter = InvoiceSplitter()
        assert splitter.api_key is not None
        assert splitter.model == "gpt-4o-mini"

    def test_initialization_with_explicit_key(self):
        """Test initialization with explicit API key"""
        splitter = InvoiceSplitter(api_key="test-key-123")
        assert splitter.api_key == "test-key-123"
    
    def test_initialization_missing_api_key(self):
        """Test that missing API key raises error"""
        # Temporarily remove env var
        original = os.environ.pop('OPENAI_API_KEY', None)
        try:
            with pytest.raises(ValueError, match="OpenAI API key"):
                InvoiceSplitter(api_key=None)
        finally:
            if original:
                os.environ['OPENAI_API_KEY'] = original
    
    def test_invoice_record_model(self):
        """InvoiceRecord is the structured invoice shape from the LLM."""
        rec = InvoiceRecord(
            start_page=1,
            end_page=3,
            vendor="ACME Corp",
            invoice_number="INV-001",
        )
        dumped = rec.model_dump()
        assert dumped["start_page"] == 1
        assert dumped["end_page"] == 3
        assert dumped["vendor"] == "ACME Corp"
        assert dumped["invoice_number"] == "INV-001"

    def test_default_output_paths(self):
        """Default folders use processed/<date>/ and discard subfolder."""
        from invoice_splitter import (
            default_day_discard_dir,
            default_day_input_dir,
            default_day_output_dir,
        )

        out = default_day_output_dir()
        assert out.parent.name == "processed"
        assert len(out.name) == 10  # YYYY-MM-DD
        assert default_day_discard_dir() == out / "discard"
        assert default_day_input_dir().parent.name == "input"


class TestPureHelpers:
    """Tests that do not require network or API keys."""

    def test_pages_from_marked_text(self):
        text = "\n--- PAGE 1 ---\nAlpha\n--- PAGE 2 ---\nBeta"
        pages = pages_from_marked_text(text)
        assert pages == [(1, "Alpha"), (2, "Beta")]

    def test_pages_from_marked_text_no_markers(self):
        pages = pages_from_marked_text("hello world")
        assert pages == [(1, "hello world")]

    def test_starts_to_segments(self):
        assert starts_to_segments([1, 3], 5) == [(1, 2), (3, 5)]
        assert starts_to_segments([2], 4) == [(2, 4)]
        assert starts_to_segments([], 5) == []

    def test_validate_split_partition_invoices_only_ok(self):
        ok, err = validate_split_partition(
            [
                {"start_page": 1, "end_page": 2, "vendor": "A", "invoice_number": "1"},
                {"start_page": 3, "end_page": 3, "vendor": "B", "invoice_number": "2"},
            ],
            [],
            3,
        )
        assert ok and not err

    def test_validate_split_partition_invoices_only_gap(self):
        ok, err = validate_split_partition(
            [
                {"start_page": 1, "end_page": 1, "vendor": "A", "invoice_number": "1"},
                {"start_page": 3, "end_page": 3, "vendor": "B", "invoice_number": "2"},
            ],
            [],
            3,
        )
        assert not ok and err

    def test_reconcile_split_with_discards(self):
        invoices = [
            {"start_page": 1, "end_page": 6, "vendor": "A", "invoice_number": "X"},
            {"start_page": 7, "end_page": 10, "vendor": "A", "invoice_number": "Y"},
        ]
        discards = [{"start_page": 1, "end_page": 1, "kind": "summary"}]
        fixed, _ = reconcile_split_with_discards(invoices, discards)
        assert fixed[0]["start_page"] == 2 and fixed[0]["end_page"] == 6

    def test_validate_split_partition_with_discards(self):
        ok, err = validate_split_partition(
            [
                {"start_page": 2, "end_page": 4, "vendor": "A", "invoice_number": "1"},
                {"start_page": 5, "end_page": 5, "vendor": "B", "invoice_number": "2"},
            ],
            [{"start_page": 1, "end_page": 1, "kind": "summary"}],
            5,
        )
        assert ok and not err

    def test_validate_split_partition_non_contiguous_pages(self):
        ok, err = validate_split_partition(
            [
                {
                    "start_page": 3,
                    "end_page": 5,
                    "vendor": "A",
                    "invoice_number": "125",
                    "page_list": [3, 5],
                }
            ],
            [
                {"start_page": 1, "end_page": 1, "kind": "summary"},
                {"start_page": 2, "end_page": 2, "kind": "other"},
                {"start_page": 4, "end_page": 4, "kind": "other"},
            ],
            5,
        )
        assert ok and not err

    def test_refine_merges_across_blank_separator(self):
        pages = [
            (1, "INVOICE Invoice No: 100 Page: 1"),
            (2, ""),
            (3, "INVOICE Invoice No: 100 Page: 2"),
            (4, "INVOICE Invoice No: 200 Page: 1"),
        ]
        model = [
            {"start_page": 1, "end_page": 1, "vendor": "V", "invoice_number": "100"},
            {"start_page": 3, "end_page": 3, "vendor": "V", "invoice_number": "100"},
            {"start_page": 4, "end_page": 4, "vendor": "V", "invoice_number": "200"},
        ]
        discards = [{"start_page": 2, "end_page": 2, "kind": "other"}]
        refined = refine_invoice_packets_from_pages(pages, discards, model)
        assert len(refined) == 2
        assert refined[0]["invoice_number"] == "100"
        assert refined[0]["page_list"] == [1, 3]
        assert refined[1]["invoice_number"] == "200"

    def test_sanitize_filename_component(self):
        assert ".." not in sanitize_filename_component("A/B Corp")
        assert sanitize_filename_component("   ") == "UNKNOWN"

    def test_assess_run_quality_success(self):
        invoices = [
            {"start_page": 1, "end_page": 1, "vendor": "A", "invoice_number": "100"},
            {"start_page": 2, "end_page": 2, "vendor": "A", "invoice_number": "200"},
        ]
        status, reasons, warnings = assess_run_quality(
            invoices, validation_ok=True, validation_errors=[]
        )
        assert status == RunStatus.SUCCESS and not reasons

    def test_assess_run_quality_duplicate(self):
        invoices = [
            {"start_page": 1, "end_page": 1, "vendor": "A", "invoice_number": "100"},
            {"start_page": 3, "end_page": 3, "vendor": "A", "invoice_number": "100"},
        ]
        status, reasons, _ = assess_run_quality(
            invoices, validation_ok=True, validation_errors=[]
        )
        assert status == RunStatus.NEEDS_REVIEW
        assert any("Duplicate" in r for r in reasons)

    def test_format_run_report_success(self):
        result = RunResult(
            status=RunStatus.SUCCESS,
            input_pdf=Path("test.pdf"),
            output_dir=Path("/tmp/out"),
            discard_dir=Path("/tmp/out/discard"),
            total_pages=3,
            invoice_files=[Path("/tmp/out/output_A_1.pdf")],
            invoices=[
                {
                    "start_page": 1,
                    "end_page": 2,
                    "vendor": "A",
                    "invoice_number": "1",
                }
            ],
        )
        text = format_run_report(result)
        assert "SUCCESS" in text
        assert "output_A_1.pdf" in text


class TestPDFHandling:
    """Test PDF type detection and handling"""

    def test_missing_file_error(self):
        """Test that missing PDF raises FileNotFoundError"""
        splitter = InvoiceSplitter(api_key="test-key")
        
        with pytest.raises(FileNotFoundError):
            splitter.split_pdf("nonexistent_file.pdf")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])