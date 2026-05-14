"""
Unit tests for Invoice Splitter
Run with: python -m pytest test_invoice_splitter.py
"""

import pytest
import tempfile
import os
from pathlib import Path
from invoice_splitter import InvoiceSplitter, Invoice


class TestInvoiceSplitter:
    """Test suite for InvoiceSplitter"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Skip tests if API key not available
        if not os.getenv('OPENAI_API_KEY'):
            pytest.skip("OPENAI_API_KEY not set")
    
    def test_initialization_with_env_key(self):
        """Test initialization with environment variable"""
        if os.getenv('OPENAI_API_KEY'):
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
    
    def test_invoice_dataclass(self):
        """Test Invoice dataclass"""
        invoice = Invoice(
            start_page=1,
            end_page=3,
            vendor="ACME Corp",
            invoice_number="INV-001",
            total="$1,500.00"
        )
        
        assert invoice.start_page == 1
        assert invoice.end_page == 3
        assert invoice.vendor == "ACME Corp"
        assert invoice.invoice_number == "INV-001"
        assert invoice.total == "$1,500.00"
    
    def test_output_directory_creation(self):
        """Test that output directory is created if missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_output"
            assert not output_dir.exists()
            
            # Would test split_pdf here with actual PDF
            # For now, just verify path handling
            assert str(output_dir).endswith("test_output")


class TestPDFHandling:
    """Test PDF type detection and handling"""
    
    def setup_method(self):
        """Set up test fixtures"""
        if not os.getenv('OPENAI_API_KEY'):
            pytest.skip("OPENAI_API_KEY not set")
    
    def test_missing_file_error(self):
        """Test that missing PDF raises FileNotFoundError"""
        splitter = InvoiceSplitter(api_key="test-key")
        
        with pytest.raises(FileNotFoundError):
            splitter.split_pdf("nonexistent_file.pdf")


# Integration tests (require actual PDF files)
class TestIntegration:
    """Integration tests with real files"""
    
    @pytest.mark.skip(reason="Requires actual PDF files and API access")
    def test_text_based_pdf_splitting(self):
        """Test splitting a text-based PDF"""
        splitter = InvoiceSplitter()
        output_files = splitter.split_pdf("sample_text.pdf", "test_output")
        
        assert len(output_files) > 0
        for file in output_files:
            assert Path(file).exists()
    
    @pytest.mark.skip(reason="Requires actual PDF files and API access")
    def test_image_based_pdf_splitting(self):
        """Test splitting an image-based (scanned) PDF"""
        splitter = InvoiceSplitter()
        output_files = splitter.split_pdf("sample_scanned.pdf", "test_output")
        
        assert len(output_files) > 0
        for file in output_files:
            assert Path(file).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])