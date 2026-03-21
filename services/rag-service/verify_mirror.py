"""Final verify: mirrored text fix in pdfplumber extraction."""
import sys; sys.path.insert(0, '/app')
from ingestion.table_extraction import _extract_page_tables

PDF_PATH = "/app/data/legal_docs_source/VB phap quy/Linh vuc_BXD-GTVT/Quy chuan BGTVT ban hanh/QCVN 113-2023-BGTVT_Ve phuongphapthuvanhbanhmoto-ganmay.pdf"

# Page 10 = Bảng A.2 (11×16), had the most mirrored headers
tables = _extract_page_tables(PDF_PATH, 9)  # page_num 9 = page 10
for t in tables:
    lines = t['markdown'].split('\n')
    print(f"Table {t['rows']}x{t['cols']}:")
    for ln in lines[:4]:
        print(f"  {ln[:100]}")
    print()

# Also page 12 row 0 header (previously: cớưht hcíK ias gnuD ...)
tables12 = _extract_page_tables(PDF_PATH, 11)  # page_num 11 = page 12
for t in tables12:
    lines = t['markdown'].split('\n')
    print(f"Page 12 — Table {t['rows']}x{t['cols']}:")
    # Check for mirrored tokens
    header = lines[0] if lines else ''
    has_mirror = any(tok in header for tok in ['cớưht', 'gnuD', 'tấhn', 'hcíK'])
    print(f"  Mirrored: {has_mirror}")
    for ln in lines[:3]:
        print(f"  {ln[:100]}")
    print()
