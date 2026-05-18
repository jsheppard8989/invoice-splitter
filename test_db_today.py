#!/usr/bin/env python3
"""Quick test: check today's processed invoices against OnBase."""

import json
from pathlib import Path
from db_check import check_invoices

manifest_path = Path(__file__).parent / "processed" / "2026-05-18" / "split_manifest_Invoices-1_20260518T191659Z.json"

with open(manifest_path) as f:
    manifest = json.load(f)

invoices = manifest["invoices"]
pairs = [(inv["vendor"], inv["invoice_number"]) for inv in invoices]

print(f"Testing {len(pairs)} invoices from today's split...")
print("=" * 80)

results = check_invoices(pairs)

for inv, res in zip(invoices, results):
    exists = res.get("exists", False)
    db_vendor = res.get("db_vendor")
    score = res.get("vendor_score")
    
    status = "✓ FOUND" if exists else "✗ NOT FOUND"
    print(f"\n{status}: {inv['invoice_number']}")
    print(f"  JSON vendor:    {inv['vendor']}")
    if db_vendor:
        print(f"  DB vendor:      {db_vendor}")
        print(f"  Match score:    {score}%")
    else:
        print(f"  DB vendor:      (not found in OnBase)")

print("\n" + "=" * 80)
found_count = sum(1 for r in results if r.get("exists"))
print(f"Summary: {found_count}/{len(results)} invoices already in OnBase")
