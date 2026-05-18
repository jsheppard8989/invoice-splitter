"""Database-check helpers for Invoice Splitter.

Provides a safe, permission-tolerant way to check whether invoice numbers
already exist in a SQL Server database using Windows authentication.

Configuration (via environment variables):
- DB_CONNECTION_STRING: ODBC connection string (optional). If not set, a default
  trusted connection string using the host in DB_HOST will be attempted.
- DB_HOST: SQL Server host (used when DB_CONNECTION_STRING is not provided).
- DB_EXISTING_INVOICE_SQL: Parameterized SQL to lookup an invoice number.
  Use a single parameter placeholder (?). Example:
    SELECT vendor_name FROM dbo.invoices WHERE invoice_number = ?
  If not provided, the module will try a few common queries.

The module never raises on permission/connect failures; it returns empty results
and logs a warning so the rest of the program can continue.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import pyodbc
except Exception:  # pragma: no cover - optional dependency
    pyodbc = None

try:
    from rapidfuzz import process, fuzz
except Exception:  # pragma: no cover - optional dependency
    process = None
    fuzz = None

logger = logging.getLogger(__name__)


def _clean_invoice_number(value: str) -> str:
    if value is None:
        return ""
    # Remove common separators and whitespace
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _get_connection() -> Optional[pyodbc.Connection]:
    if pyodbc is None:
        logger.warning("pyodbc not installed; DB checks disabled")
        return None

    conn_str = os.environ.get("DB_CONNECTION_STRING")
    if conn_str:
        try:
            return pyodbc.connect(conn_str, autocommit=True)
        except Exception as e:
            logger.warning("Could not connect using DB_CONNECTION_STRING: %s", e)
            return None

    host = os.environ.get("DB_HOST")
    if not host:
        logger.info("No DB_HOST or DB_CONNECTION_STRING provided; skipping DB checks")
        return None

    # Build a trusted connection string for SQL Server using Windows auth
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={host};Trusted_Connection=yes;Encrypt=no"
    try:
        return pyodbc.connect(conn_str, autocommit=True)
    except Exception as e:
        logger.warning("Could not connect to SQL Server at %s: %s", host, e)
        return None


def _candidate_queries() -> List[str]:
    env_q = os.environ.get("DB_EXISTING_INVOICE_SQL")
    if env_q:
        return [env_q]
    # Common fallback queries; expect one parameter (?) for invoice_number
    return [
        "SELECT vendor_name FROM invoices WHERE invoice_number = ?",
        "SELECT vendor FROM invoices WHERE invoice_number = ?",
        "SELECT vendor_name FROM dbo.invoices WHERE invoice_number = ?",
        "SELECT vendor FROM dbo.invoices WHERE invoice_number = ?",
    ]


def check_invoices(
    pairs: Iterable[Tuple[str, str]],
) -> List[Dict[str, Optional[str]]]:
    """Check a batch of (vendor, invoice_number) pairs against the DB.

    Returns a list of dicts with keys: invoice_number, vendor, exists (bool), db_vendor (str|None)
    If DB access is unavailable or permission-denied, `exists` will be False and
    `db_vendor` None for all rows (the function will not raise).
    """
    conn = _get_connection()
    results: List[Dict[str, Optional[str]]] = []
    pairs_list = list(pairs)
    if not pairs_list:
        return results

    cleaned_map = {inv: _clean_invoice_number(inv) for _, inv in pairs_list}

    if conn is None:
        for vendor, inv in pairs_list:
            results.append({"invoice_number": inv, "vendor": vendor, "exists": False, "db_vendor": None})
        return results

    queries = _candidate_queries()
    cursor = None
    try:
        cursor = conn.cursor()
    except Exception as e:
        logger.warning("Could not obtain DB cursor: %s", e)
        for vendor, inv in pairs_list:
            results.append({"invoice_number": inv, "vendor": vendor, "exists": False, "db_vendor": None})
        return results

    for vendor, inv in pairs_list:
        cleaned = cleaned_map.get(inv, _clean_invoice_number(inv))
        found = False
        db_vendor = None
        for q in queries:
            try:
                # Try exact invoice number first
                cursor.execute(q, inv)
                row = cursor.fetchone()
                if row:
                    db_vendor = str(row[0]) if row[0] is not None else None
                    found = True
                    break
                # Try cleaned invoice number where schema stores only alphanumerics
                cursor.execute(q, cleaned)
                row = cursor.fetchone()
                if row:
                    db_vendor = str(row[0]) if row[0] is not None else None
                    found = True
                    break
            except Exception as e:  # pragma: no cover - DB errors depend on environment
                err_text = str(e).lower()
                if "permission" in err_text or "access" in err_text or "denied" in err_text:
                    logger.warning("DB permission issue while checking invoice '%s': %s", inv, e)
                    found = False
                    db_vendor = None
                    break
                # Other errors: try next query
                logger.debug("Query failed (%s); trying next. Error: %s", q, e)
                continue

        results.append({"invoice_number": inv, "vendor": vendor, "exists": bool(found), "db_vendor": db_vendor})

    try:
        cursor.close()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass

    # Optionally perform fuzzy vendor match if rapidfuzz available and any found vendors exist
    if process and any(r.get("db_vendor") for r in results):
        db_vendors = [r["db_vendor"] for r in results if r.get("db_vendor")]
        # Remove duplicates
        db_vendors_unique = list(dict.fromkeys(db_vendors))
        for r in results:
            if r.get("db_vendor"):
                # Score the provided vendor against db_vendor
                try:
                    score = fuzz.token_sort_ratio(str(r.get("vendor", "")), r["db_vendor"])
                    r["vendor_score"] = int(score)
                except Exception:
                    r["vendor_score"] = None
            else:
                r["vendor_score"] = None

    return results


__all__ = ["check_invoices", "_clean_invoice_number"]
