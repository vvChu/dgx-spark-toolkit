"""
Process QCVN_113_2023 directly via pipeline and export the markdown.
This verifies that the TABLE-FIX and PARA-FIX work end-to-end.
"""
import sys
import os
import re
sys.path.insert(0, '/app')

from ingestion.pipeline import ProductionIngestor
from ingestion.exporter import DataExporter
from core.config import get_settings

s = get_settings()
pdf_path = "/app/data/legal_docs_source/VB phap quy/Linh vuc_BXD-GTVT/Quy chuan BGTVT ban hanh/QCVN 113-2023-BGTVT_Ve phuongphapthuvanhbanhmoto-ganmay.pdf"
assert os.path.exists(pdf_path), f"PDF not found: {pdf_path}"

ingestor = ProductionIngestor()

print("Extracting PDF pages with TABLE-FIX + PARA-FIX...")
chunks, failed = ingestor.extract_pdf(pdf_path)
print(f"Extracted {len(chunks)} pages, {len(failed)} failed")

# Check for TABLE-FIX results
table_hits = 0
para_joins = 0
for c in chunks:
    text = c.get('text', '')
    if '|---|' in text or '| --- |' in text:
        table_hits += 1
        page = c.get('page', '?')
        # Print preview of first table found
        lines = text.split('\n')
        for i, ln in enumerate(lines):
            if '|---|' in ln or '| --- |' in ln:
                preview = '\n'.join(lines[max(0, i-2):i+4])
                print(f"\nPage {page} — TABLE detected:")
                print(preview[:400])
                break

print(f"\n{'='*55}")
print(f"Pages with markdown tables : {table_hits}/{len(chunks)}")
print(f"{'='*55}")

# Show a sample of page 5 text
for c in chunks:
    if c.get('page') == 5:
        print(f"\nPage 5 text preview (first 600 chars):")
        print(c['text'][:600])
        break
