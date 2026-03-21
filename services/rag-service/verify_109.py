"""Pre-verify: QCVN_109_2024 table extraction before it queues through rag-watcher."""
import sys; sys.path.insert(0, '/app')
import subprocess, os

from ingestion.table_extraction import _extract_page_tables
from ingestion.text_normalizer import rejoin_paragraphs

# Find QCVN_109_2024 PDF
result = subprocess.run(['find', '/app/data', '-name', '*QCVN*109*2024*.pdf'],
    capture_output=True, text=True, timeout=15)
candidates = [c for c in result.stdout.strip().split('\n') if c.strip()]
if not candidates:
    print("PDF not found"); import sys; sys.exit(1)

pdf_path = candidates[0]
print(f"PDF: {os.path.basename(pdf_path)}")

# Check pages 5-15 for tables (emission standard tables)
total_tables = 0
for pg in range(4, 16):
    tables = _extract_page_tables(pdf_path, pg)
    if tables:
        total_tables += len(tables)
        for t in tables:
            md_lines = t['markdown'].split('\n')
            print(f"\nPage {pg+1}: {t['rows']}x{t['cols']} table")
            for ln in md_lines[:3]:
                print(f"  {ln[:85]}")

print(f"\nTotal tables detected: {total_tables}")

# Test paragraph join on page 3 text
import fitz
with fitz.open(pdf_path) as doc:
    raw = doc[2].get_text()  # page 3

before_lines = [l for l in raw.split('\n') if l.strip()]
joined = rejoin_paragraphs(raw)
after_lines = [l for l in joined.split('\n') if l.strip()]
print(f"\nParagraph join: {len(before_lines)} lines → {len(after_lines)} lines ({len(before_lines)-len(after_lines)} merged)")
print("Sample after join (first 300 chars):")
print(joined[:300])
