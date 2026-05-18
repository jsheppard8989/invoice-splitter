Release: OnBase DB Duplicate Detection + Duplicates Folder
Date: 2026-05-18
Commit: ca61071

Summary
-------
This release adds OnBase database checking to the Invoice Splitter to detect potential duplicate invoices and automatically isolate them for review.

Key changes
-----------
- Added `db_check.py` — safe, permission-tolerant DB access using `pyodbc` and optional fuzzy vendor matching via `rapidfuzz`.
- Updated `requirements.txt` — added `pyodbc` and `rapidfuzz` (run `pip install -r requirements.txt`).
- Integrated DB checks into `invoice_splitter.py` — invoices are annotated with:
  - `exists_in_db` (boolean)
  - `db_vendor` (string) — vendor name returned from OnBase
  - `vendor_score` (int 0-100) — fuzzy similarity score
  - `moved_to_duplicates` (boolean) — true when moved to `duplicates/`
- Added automatic duplicate handling:
  - `processed/<date>/duplicates/` created when an invoice is found in OnBase
  - Threshold: invoices `exists_in_db == true` AND `vendor_score >= 75` are moved to `duplicates/`
- Manifest timing fixed: `split_manifest_*.json` is now written after DB checks and duplicate classification so it includes the new metadata.
- Report and CLI updates: `RESULTS_*.txt` and console summary now show potential duplicates and vendor match scores.
- Added tests: `test_db_check.py` (unit tests mocking DB) and `test_db_today.py` (ad-hoc runner for today's manifest).
- README updated with DB configuration and duplicates behavior.

Configuration
-------------
Set the following environment variables in `.env` (examples already added to the repository `.env`):

```
DB_HOST=SQLP-ONBASE01
DB_DATABASE=OnBase
# Optional: custom lookup SQL (one parameter placeholder ?)
# DB_EXISTING_INVOICE_SQL=SELECT ltrim(rtrim(k1014.keyvaluechar)) as [Vendor Name] FROM hsi.itemdata i ... WHERE REPLACE(..., '-', '') = ? AND ...
```

Notes & operational details
---------------------------
- Invoice numbers are cleaned (non-alphanumeric characters removed) before lookup.
- The SQL used by default searches OnBase for the cleaned invoice number within the last 14 months and returns the vendor name for fuzzy matching.
- Windows (trusted) authentication is used; if the running user lacks permissions the program will log a warning and continue (no failure).
- Duplicate handling is non-destructive: invoices moved to `duplicates/` should be reviewed and only then processed/sent to AP.

How to test locally
-------------------
1. Install new dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Restart the Invoice Splitter service or re-run the CLI so the updated code and `.env` are loaded.
3. Run the existing `processed/<today>/split_manifest_*.json` test using `test_db_today.py`:

```bash
python test_db_today.py
```

4. Run unit tests (uses `unittest`):

```bash
python -m unittest test_db_check.py -v
```

Release artifacts
-----------------
- `db_check.py` (new)
- `invoice_splitter.py` (modified)
- `requirements.txt` (modified)
- `README.md` (modified to include DB/duplicates docs)
- `test_db_check.py` (new)
- `test_db_today.py` (new)
- `RELEASE_NOTES.md` (this file)

If you want a different vendor-match threshold, or to log additional fields in the manifest, tell me which changes to make and I will patch them.
