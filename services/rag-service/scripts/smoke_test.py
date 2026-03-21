"""Smoke test: table extraction on QCVN_113."""
import sys
sys.path.insert(0, '/app')

from ingestion.table_extraction import _extract_page_tables
import subprocess, os

# Find the QCVN_113 2023 PDF
result = subprocess.run(
    ['find', '/data', '-name', '*QCVN*113*2023*.pdf', '-not', '-name', '*113*2024*'],
    capture_output=True, text=True, timeout=20
)
candidates = [c for c in result.stdout.strip().split('\n') if c.strip()]
if not candidates:
    # Try broader search
    result = subprocess.run(['find', '/data', '-name', '*113*23*.pdf'], capture_output=True, text=True, timeout=20)
    candidates = [c for c in result.stdout.strip().split('\n') if c.strip()]

if not candidates:
    print("ERROR: PDF not found")
    sys.exit(1)

pdf_path = candidates[0]
print(f"PDF: {pdf_path}\n")

# Test pages 4-14 (0-indexed) — these contain Bảng 1,2,A.2,A.3,...
total_tables = 0
for pg in range(4, 18):
    tables = _extract_page_tables(pdf_path, pg)
    if tables:
        print(f"Page {pg+1}: found {len(tables)} table(s)")
        for i, t in enumerate(tables):
            print(f"  Table {i+1}: {t['rows']}x{t['cols']}")
            md_lines = t['markdown'].split('\n')[:3]
            for ln in md_lines:
                print(f"    {ln[:85]}")
        total_tables += len(tables)
    else:
        print(f"Page {pg+1}: no tables")

print(f"\nTOTAL: {total_tables} tables detected across 14 tested pages")
