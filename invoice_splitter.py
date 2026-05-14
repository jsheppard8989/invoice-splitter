#!/usr/bin/env python3
"""
Invoice Splitter - Split large PDF files into individual invoices
Handles both text-based and image-based (scanned) PDFs with AI-powered detection
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
import re

import requests
from pdf2image import convert_from_path
import pytesseract
from PyPDF2 import PdfReader, PdfWriter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Invoice:
    """Represents a single invoice"""
    start_page: int
    end_page: int
    vendor: str
    invoice_number: str
    total: Optional[str] = None
    pages: Optional[List] = None


class InvoiceSplitter:
    """Main class for splitting invoices from PDFs"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Invoice Splitter
        
        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. "
                "Set OPENAI_API_KEY environment variable or pass api_key parameter."
            )
        
        self.model = "gpt-4o-mini"
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.invoices: List[Invoice] = []
        self.current_pdf_path: Optional[str] = None
        
    def _is_text_based_pdf(self, pdf_path: str) -> bool:
        """
        Determine if PDF is text-based or image-based by checking first page
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            True if text-based, False if image-based (scanned)
        """
        try:
            reader = PdfReader(pdf_path)
            first_page = reader.pages[0]
            text = first_page.extract_text()
            # If we get meaningful text (>50 chars), it's text-based
            return len(text.strip()) > 50
        except Exception as e:
            logger.warning(f"Error checking PDF type: {e}. Assuming image-based.")
            return False
    
    def _extract_text_based(self, pdf_path: str) -> str:
        """
        Extract text from text-based PDF
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text
        """
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                text += f"\n--- PAGE {page_num + 1} ---\n{page_text}"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from text-based PDF: {e}")
            raise
    
    def _extract_image_based(self, pdf_path: str) -> str:
        """
        Extract text from image-based PDF using OCR
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text
        """
        try:
            logger.info("Detected image-based PDF. Running OCR...")
            images = convert_from_path(pdf_path)
            text = ""
            
            for page_num, image in enumerate(images, 1):
                logger.info(f"  OCR processing page {page_num}/{len(images)}...")
                page_text = pytesseract.image_to_string(image)
                text += f"\n--- PAGE {page_num} ---\n{page_text}"
            
            return text
        except Exception as e:
            logger.error(f"Error extracting text with OCR: {e}")
            logger.error(
                "Ensure Tesseract OCR is installed:\n"
                "  Linux: sudo apt-get install tesseract-ocr\n"
                "  Mac: brew install tesseract\n"
                "  Windows: Download installer from https://github.com/UB-Mannheim/tesseract/wiki"
            )
            raise
    
    def _extract_text(self, pdf_path: str) -> str:
        """
        Extract text from PDF (auto-detects type)
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text
        """
        logger.info(f"Analyzing PDF: {pdf_path}")
        
        is_text_based = self._is_text_based_pdf(pdf_path)
        
        if is_text_based:
            logger.info("Detected text-based PDF")
            return self._extract_text_based(pdf_path)
        else:
            return self._extract_image_based(pdf_path)
    
    def _parse_invoices_with_ai(self, text: str, pdf_path: str) -> List[Dict]:
        """
        Use AI to identify invoice boundaries and metadata
        
        Args:
            text: Extracted PDF text
            pdf_path: Path to PDF file for getting page count
            
        Returns:
            List of invoice metadata
        """
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        
        prompt = f"""You are an invoice parsing expert. Analyze this PDF content and identify each invoice.

Total pages in PDF: {total_pages}

PDF Content:
{text[:8000]}  # First 8000 chars to stay within token limits

Your task:
1. Identify where each invoice starts and ends
2. Extract vendor name and invoice number for each
3. Return a JSON array with this structure:

[
  {{
    "invoice_number": "INV-001",
    "vendor": "Company Name",
    "start_page": 1,
    "end_page": 1,
    "confidence": 0.95
  }},
  ...
]

Guidelines:
- Look for invoice numbers (Invoice #, Invoice No., #, etc.)
- Identify vendor/company names at the top of each invoice
- Find page breaks and format changes that indicate new invoices
- Be conservative: if unsure about a boundary, keep pages together
- Ensure NO pages are skipped - all pages must be assigned
- For multi-page invoices, include all continuation pages

Return ONLY valid JSON, no other text."""

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Parse JSON from response
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if not json_match:
                logger.warning("Could not find JSON in AI response")
                return []
            
            invoices = json.loads(json_match.group())
            logger.info(f"AI identified {len(invoices)} invoices")
            
            return invoices
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            raise
    
    def split_pdf(self, pdf_path: str, output_dir: str = "output") -> List[str]:
        """
        Split a PDF into individual invoices
        
        Args:
            pdf_path: Path to input PDF
            output_dir: Directory to save split invoices
            
        Returns:
            List of output file paths
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        self.current_pdf_path = str(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        logger.info(f"Processing: {pdf_path.name}")
        
        # Extract text
        extracted_text = self._extract_text(str(pdf_path))
        
        # Parse invoices with AI
        invoice_data = self._parse_invoices_with_ai(extracted_text, str(pdf_path))
        
        if not invoice_data:
            logger.warning("No invoices detected. Saving entire PDF as single file.")
            output_path = output_dir / f"output_unknown.pdf"
            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            with open(output_path, 'wb') as f:
                writer.write(f)
            return [str(output_path)]
        
        # Split and save invoices
        output_files = []
        reader = PdfReader(str(pdf_path))
        
        for invoice in invoice_data:
            try:
                start_page = invoice.get('start_page', 1) - 1  # Convert to 0-indexed
                end_page = invoice.get('end_page', len(reader.pages))
                vendor = invoice.get('vendor', 'Unknown').replace('/', '_')
                invoice_number = invoice.get('invoice_number', 'UNKNOWN').replace('/', '_')
                
                # Validate page ranges
                start_page = max(0, min(start_page, len(reader.pages) - 1))
                end_page = max(start_page, min(end_page, len(reader.pages)))
                
                # Create output file
                filename = f"output_{vendor}_{invoice_number}.pdf"
                output_path = output_dir / filename
                
                # Extract pages
                writer = PdfWriter()
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])
                
                # Save file
                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                logger.info(f"✓ Created: {filename} (pages {start_page + 1}-{end_page})")
                output_files.append(str(output_path))
                
            except Exception as e:
                logger.error(f"Error processing invoice: {e}")
                continue
        
        logger.info(f"\n✓ Successfully split into {len(output_files)} invoices")
        logger.info(f"✓ Files saved to: {output_dir.absolute()}")
        
        return output_files


def main():
    """Command-line interface"""
    if len(sys.argv) < 2:
        print("Usage: python invoice_splitter.py <pdf_file> [output_dir]")
        print("Example: python invoice_splitter.py invoices.pdf ./output")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    
    try:
        splitter = InvoiceSplitter()
        splitter.split_pdf(pdf_path, output_dir)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()