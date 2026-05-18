# Invoice Splitter

Split multi-invoice PDFs into individual files for accounts payable. Works with text-based and scanned PDFs using GPT-4o-mini, validation, discard handling, and a local web UI.

## Features

- **Web UI** — drag-and-drop PDFs, batch processing, open today’s folders in Finder/Explorer
- **Scanned PDFs** — Poppler converts pages to images; Tesseract OCR reads text (both required)
- **Text PDFs** — direct extraction with PyPDF2 when the PDF has selectable text
- **AI splitting** — GPT-4o-mini finds invoice packets vs summary/boilerplate discards
- **Fail-closed** — validation and quality checks; uncertain runs produce a `NEEDS_REVIEW` PDF instead of bad splits
- **Run reports** — `RESULTS_<file>.txt` and `split_manifest_*.json` per run
- **Desktop shortcut** — created automatically during setup (Windows & Mac)

## Requirements

### System (required for scanned PDFs)

| Tool | Role |
|------|------|
| **Poppler** (`pdftoppm`) | Converts each PDF page to an image |
| **Tesseract** | OCR — reads text from those images |

```bash
# macOS
brew install poppler tesseract

# Ubuntu/Debian
sudo apt-get install poppler-utils tesseract-ocr

# Windows
# Poppler: https://github.com/oschwartz10612/poppler-windows/releases/
# Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
# Add both install folders to your PATH.
```

### Python

- Python 3.9+
- `pip install -r requirements.txt`
- OpenAI API key in `.env` (see `.env.example`)

## Install from scratch

**Easiest:** open [`INSTALL-FROM-SCRATCH.txt`](INSTALL-FROM-SCRATCH.txt) — step-by-step copy/paste commands for Windows and Mac.

**Windows (GUI):** double-click `Install from Scratch (Windows).bat` after Python, Tesseract, and Poppler are installed.

**Windows (Command Prompt)** — run from inside the `invoice-splitter` folder:

```bat
git clone https://github.com/jsheppard8989/invoice-splitter.git
cd invoice-splitter
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 setup_program.py
```

**Mac (Terminal):**

```bash
git clone https://github.com/jsheppard8989/invoice-splitter.git
cd invoice-splitter
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 setup_program.py
```

Install **Python 3.12**, **Tesseract**, and **Poppler** first (see [Requirements](#requirements)). On Windows, prefer Python 3.12 over 3.14.

## First-time setup (if you already have the folder)

| Platform | Run once |
|----------|----------|
| **Windows** | `Setup Invoice Splitter.bat` or `Install from Scratch (Windows).bat` |
| **Mac** | `Setup Invoice Splitter.command` |

Setup installs Python packages, creates `.env`, prompts for your API key, checks Poppler/Tesseract, and creates desktop shortcuts **Invoice Splitter** and **Stop Invoice Splitter**.

## Daily use

| Platform | Launch |
|----------|--------|
| **Windows** | Desktop **Invoice Splitter** or `Start Invoice Splitter.vbs` (no terminal window) |
| **Mac** | Desktop **Invoice Splitter** or `Start Invoice Splitter.command` |

Your browser opens to **http://127.0.0.1:5050**. The app runs in the background — you do **not** need to keep a terminal open.

| When finished for the day | Action |
|---------------------------|--------|
| **Windows** | `Stop Invoice Splitter.bat` |
| **Mac** | `Stop Invoice Splitter.command` |

Logs (if needed for support): `logs/app.log` in the program folder.

1. Drag PDFs onto the page (or browse)
2. Click **Split invoices**
3. Use **Open today’s invoices** / **Open discard folder** for output

To recreate only the desktop icon: `Create Desktop Icon.bat` (Windows) or `Create Desktop Icon.command` (Mac).

## Where files go

For each calendar day:

```
invoice-splitter/
├── input/<YYYY-MM-DD>/           ← uploaded originals
└── processed/<YYYY-MM-DD>/
    ├── output_<VENDOR>_<INV>.pdf ← split invoices (send to AP)
    ├── discard/                  ← summaries, boilerplate (do not send to AP)
    ├── split_manifest_*.json     ← machine-readable run log
    └── RESULTS_<stem>.txt        ← human-readable run report
```

If the run is not trusted, you also get `output_NEEDS_REVIEW_<stem>_<timestamp>.pdf` containing the full original for manual handling.

## Command line (optional)

```bash
python invoice_splitter.py invoices.pdf
python invoice_splitter.py invoices.pdf ./custom_output --open
```

Default output directory is `processed/<today>/` (same as the web UI).

### Python API

```python
from invoice_splitter import InvoiceSplitter

splitter = InvoiceSplitter()
result = splitter.split_pdf("invoices.pdf")  # optional output_dir

print(result.headline())
print(result.invoice_files)   # list of Path
print(result.discard_files)
print(result.report_path)
```

`split_pdf` returns a `RunResult` with `status` of `success`, `needs_review`, or `failed`.

## How it works

1. **Extract text** — PyPDF2 for text PDFs; Poppler + Tesseract for scanned
2. **Analyze** — single LLM call for small PDFs; chunked boundary + metadata passes for large ones
3. **Refine** — reconcile discards, merge packets across blank separators, build final discard list
4. **Validate** — every page assigned exactly once (invoice or discard)
5. **Quality gate** — duplicate invoice numbers, missing IDs, etc. → `NEEDS_REVIEW`
6. **Write** — invoice PDFs, discard PDFs, manifest, and `RESULTS_*.txt`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Setup crashes on `find_loader` / `pkgutil` | Python 3.14 + old pytesseract — run `py -3 -m pip install "pytesseract>=0.3.13" --upgrade`, then setup again. Prefer **Python 3.12** on Windows. |
| Setup checklist not green | Run `Setup Invoice Splitter` again; install missing Poppler/Tesseract |
| Tesseract / Poppler not found | Install system tools and ensure they are on PATH |
| API errors | Check `OPENAI_API_KEY` in `.env` |
| Poor splits | Open `RESULTS_*.txt` and `split_manifest_*.json`; use the `NEEDS_REVIEW` PDF |

## Cost

Roughly **$0.01–0.05 per PDF** (GPT-4o-mini tokens). OCR runs locally at no API cost.

## Tests

```bash
python -m pytest test_invoice_splitter.py -q
```

## Security

- API keys live in `.env` (not committed)
- PDFs are processed locally
- `.env` is listed in `.gitignore`

## License

MIT License
