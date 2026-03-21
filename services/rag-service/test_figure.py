"""Live test: figure description injection on 14177_TCVN page 11 (has 2 images)."""
import sys; sys.path.insert(0, '/app')
import fitz
from ingestion.figure_extractor import describe_page_figures, _extract_page_images, _find_nearest_hinh_label

PDF = '/app/data/legal_docs_source/VB phap quy/TL huongdanBIM/20241231_Tai lieu HD bo TCVN14177-2024_ISO19650_TC&SHTT ve CTXD.pdf'
doc = fitz.open(PDF)

print(f"PDF: {PDF.split('/')[-1]}")
print(f"Pages: {doc.page_count}")

# Test page 11 (0-indexed: 10) — has 2 images
pg = 10
page = doc[pg]
raw_text = page.get_text()

imgs = _extract_page_images(doc, pg)
print(f"\nPage {pg+1}: {len(imgs)} images found")
for img in imgs:
    lbl = _find_nearest_hinh_label(page, img['rect'])
    print(f"  img area={img['area']:.0f}px², label={lbl!r}, bytes={len(img['img_bytes'])}")

import re
hinh_refs = re.findall(r'Hình\s+[\d.A-Za-z]+', raw_text)
print(f"  Hình refs in text: {hinh_refs[:5]}")

print("\nCalling describe_page_figures (vision LLM)...")
enriched = describe_page_figures(doc=doc, page_num=pg, page_text=raw_text, pdf_path=PDF, max_figures_per_page=2)

print("\n--- Original (last 200 chars) ---")
print(raw_text[-200:])
print("\n--- Enriched (last 600 chars) ---")
print(enriched[-600:])

# Check if captions were injected
injected = [l for l in enriched.split('\n') if l.startswith('[Hình') or l.startswith('[Hình trang')]
print(f"\nCaptions injected: {len(injected)}")
for c in injected:
    print(f"  {c[:120]}")
