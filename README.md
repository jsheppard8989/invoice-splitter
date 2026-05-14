# Invoice Splitter

A robust, low-cost AI-powered tool to automatically split large PDF files containing multiple invoices into individual invoice files. Handles both text-based and scanned (image-based) PDFs with intelligent invoice boundary detection.

## Features

✨ **Key Capabilities**
- **Dual PDF Support**: Works with both text-based and scanned (image-based) PDFs
- **Automatic Detection**: Detects PDF type and uses appropriate extraction method
- **OCR for Scanned PDFs**: Uses Tesseract OCR for image-based documents
- **AI-Powered Parsing**: GPT-4o-mini identifies invoice boundaries with common sense
- **Zero Data Loss**: Every page assigned to an invoice, nothing skipped
- **Multi-Vendor**: Handles different invoice formats and vendors automatically
- **Low Cost**: Uses GPT-4o-mini (~$0.01-0.05 per PDF)
- **Easy to Use**: Single command, automatic output naming
- **Production Ready**: Error handling, logging, and validation included

## Requirements

### System Dependencies

**Tesseract OCR** (required for scanned PDFs):
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
```

**Poppler** (required for PDF to image conversion):
```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler

# Windows
# Download from: https://github.com/oschwartz10612/poppler-windows/releases/
```

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/jsheppard8989/invoice-splitter.git
   cd invoice-splitter
   ```

2. **Install system dependencies** (see Requirements above)

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up OpenAI API key**
   ```bash
   export OPENAI_API_KEY=sk-your-key-here
   ```
   
   Or create a `.env` file:
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```

## Quick Start

### Basic Usage

```bash
python invoice_splitter.py large_invoices.pdf
```

This will:
1. Analyze the PDF (auto-detect if text or image-based)
2. Extract text (with OCR if needed)
3. Use AI to identify invoice boundaries
4. Split into individual PDFs
5. Save to `./output/` directory with names like `output_VENDOR_INVOICENUMBER.pdf`

### Advanced Usage

```bash
# Specify output directory
python invoice_splitter.py invoices.pdf ./my_output_folder

# Use in Python code
from invoice_splitter import InvoiceSplitter

splitter = InvoiceSplitter(api_key="sk-your-key")
output_files = splitter.split_pdf("invoices.pdf", "output")
print(f"Created {len(output_files)} invoices")
```

## How It Works

### 1. PDF Type Detection
- Attempts to extract text from the first page
- If successful (>50 characters), treats as text-based PDF
- Otherwise, uses OCR for image-based (scanned) PDFs

### 2. Text Extraction
- **Text PDFs**: Direct text extraction using PyPDF2
- **Image PDFs**: Tesseract OCR processes each page and extracts text

### 3. Invoice Parsing with AI
- Sends extracted text to GPT-4o-mini
- AI identifies:
  - Invoice boundaries (start/end pages)
  - Vendor/company names
  - Invoice numbers
  - Page ranges for multi-page invoices
- Ensures every page is assigned to an invoice

### 4. PDF Splitting
- Creates separate PDF files for each invoice
- Names files: `output_<VENDOR>_<INVOICENUMBER>.pdf`
- Saves to output directory

## Output

The tool creates individual PDF files named like:
```
output_ACME_Corp_INV-2024-001.pdf
output_Vendor_XYZ_INV-85432.pdf
output_Global_Services_2024-05-14-001.pdf
```

Each file contains only the pages for that specific invoice.

## Troubleshooting

### "Tesseract not found" Error
Install Tesseract OCR for your OS (see Requirements section)

### "Poppler not found" Error
Install poppler utilities for your OS (see Requirements section)

### API Errors
- Verify your OpenAI API key is valid
- Check you have sufficient API credits
- Ensure you're using a valid OpenAI organization

### Poor OCR Quality
- PDFs with very low resolution may have poor OCR results
- Consider increasing DPI if you control PDF generation
- For business PDFs, typically 150-200 DPI is sufficient

### AI Misidentifies Invoice Boundaries
- Large multi-vendor PDFs may occasionally need manual review
- Check output files to verify splits are correct
- Adjust prompts in `_parse_invoices_with_ai()` if needed

## Cost Estimate

- **Text-based PDF** (100 pages): ~$0.01-0.02
- **Scanned PDF** (100 pages): ~$0.02-0.05
  - OCR processing happens locally (free)
  - Only AI parsing costs (tokens)

## Architecture

```
invoice_splitter.py
├── InvoiceSplitter (main class)
│   ├── _is_text_based_pdf()        # Detect PDF type
│   ├── _extract_text_based()       # Extract from text PDFs
│   ├── _extract_image_based()      # OCR scanned PDFs
│   ├── _extract_text()             # Auto-detect and extract
│   ├── _parse_invoices_with_ai()   # AI parsing
│   └── split_pdf()                 # Main workflow
└── CLI interface
```

## License

MIT License - Free for commercial and personal use

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review logs for error messages
3. Test with a small PDF first to verify setup

## Performance Notes

- **First run**: May be slower as dependencies install
- **OCR processing**: Scanned PDFs take longer (proportional to page count)
- **API rate limits**: OpenAI API has rate limits; batching jobs is recommended
- **Memory**: Large PDFs (500+ pages) may use significant memory

## Security

- API keys are never logged
- PDFs are processed locally
- No data is retained after processing
- Specify `.env` file for secure key management

---

**Made with ❤️ for invoice management**