"""Smoke test: table extraction on QCVN_113 2023."""
import sys
sys.path.insert(0, '/app')

from ingestion.table_extraction import _extract_page_tables

PDF_PATH = "/app/data/legal_docs_source/VB phap quy/Linh vuc_BXD-GTVT/Quy chuan BGTVT ban hanh/QCVN 113-2023-BGTVT_Ve phuongphapthuvanhbanhmoto-ganmay.pdf"
import os
print(f"PDF exists: {os.path.exists(PDF_PATH)}")
print(f"PDF: {PDF_PATH}\n")

# Test pages 4-17 (0-indexed) — these contain Bảng 1,2,A.2,A.3,...
total_tables = 0
for pg in range(4, 18):
    tables = _extract_page_tables(PDF_PATH, pg)
    if tables:
        print(f"Page {pg+1}: found {len(tables)} table(s) ✅")
        for i, t in enumerate(tables):
            print(f"  Table {i+1}: {t['rows']}x{t['cols']} rows/cols")
            md_lines = t['markdown'].split('\n')[:4]
            for ln in md_lines:
                print(f"    {ln[:90]}")
        total_tables += len(tables)
    else:
        print(f"Page {pg+1}: no tables")

print(f"\n{'='*55}")
print(f"TOTAL: {total_tables} tables detected across 14 tested pages")
print(f"{'='*55}")
