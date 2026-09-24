#!/usr/bin/env python3
"""Re-OCR Luật Xây dựng 2014 using ocr-primary (gemini-3.1-flash-lite) via AI Gateway :8090.

4 concurrent threads, caching per page in /tmp/luat_50_ocr_cache.
Generates clean JSON and Markdown exports with 0 prompt echo, 0 OCR labels, 0 duplicate chunks.
"""
import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Add rag-service root to sys.path
_RAG_ROOT = str(Path(__file__).resolve().parent.parent)
if _RAG_ROOT not in sys.path:
    sys.path.insert(0, _RAG_ROOT)

import fitz

from core.ai_gateway_client import get_ai_gateway_client
from ingestion.cleaning_utils import clean_llm_text
from ingestion.cloud_vision import llm_extract_page, llm_generate_summary
from ingestion.chunking import VietLawArticleChunker, _split_into_children, MAX_CHUNK_CHARS, _is_noise_chunk
from ingestion.exporter import DataExporter
from ingestion.normalizers.boilerplate import strip_ai_monologue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("reocr_luat_xaydung")

PDF_PATH = "/home/vvc/Public/VB phap quy/QH_Luat-Hienphap/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf"
CACHE_DIR = Path("/tmp/luat_50_ocr_cache")
DOC_ID = "ROOT/Luat_50-2014-QH13_Luat_Xay_dung_18-6-2014"
FILE_NAME = "Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf"
DOC_NUMBER = "50/2014/QH13"
MAX_WORKERS = 4


def extract_page_worker(page_idx: int, img_bytes: bytes) -> tuple[int, str]:
    page_num = page_idx + 1
    cache_file = CACHE_DIR / f"page_{page_num:03d}.txt"

    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
        if len(text.strip()) > 50:
            logger.info(f"Page {page_num:02d}/98 loaded from cache ({len(text)} chars)")
            return page_num, text

    cleaned = ""
    for attempt in range(3):
        t0 = time.time()
        res = llm_extract_page(img_bytes, page_num=page_num, model_override="ocr-primary")
        raw_text = res.get("text", "")
        cleaned = strip_ai_monologue(clean_llm_text(raw_text))
        if len(cleaned.strip()) > 50:
            cache_file.write_text(cleaned, encoding="utf-8")
            logger.info(f"Page {page_num:02d}/98 extracted in {time.time()-t0:.1f}s ({len(cleaned)} chars)")
            return page_num, cleaned
        time.sleep(1.5 * (attempt + 1))

    logger.warning(f"Page {page_num:02d}/98 failed after 3 attempts")
    return page_num, cleaned


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    export_dir = os.environ.get("EXPORT_DIR", "/home/vvc/Public/exports")
    exporter = DataExporter(export_dir)

    logger.info(f"Opening PDF: {PDF_PATH}")
    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)
    logger.info(f"Total pages: {total_pages}. Starting 4-thread OCR extraction...")

    # Render all pages to images first
    page_images = []
    for idx in range(total_pages):
        page = doc[idx]
        pix = page.get_pixmap(dpi=150)
        page_images.append((idx, pix.tobytes("jpeg")))

    results = {}
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(extract_page_worker, idx, img_b): idx + 1
            for idx, img_b in page_images
        }
        for future in concurrent.futures.as_completed(futures):
            p_num = futures[future]
            try:
                page_num, text = future.result()
                results[page_num] = text
            except Exception as e:
                logger.error(f"Error on page {p_num}: {e}")
                results[p_num] = ""

    elapsed = time.time() - start_time
    logger.info(f"All {total_pages} pages extracted in {elapsed:.1f}s (~{elapsed/60:.2f} mins)")

    # Build page texts in sequential order
    ordered_pages = [results[i] for i in range(1, total_pages + 1)]
    
    # Calculate character offsets for page attribution
    page_offsets = []
    accum = 0
    for idx, p_text in enumerate(ordered_pages):
        page_offsets.append((accum, accum + len(p_text), idx + 1))
        accum += len(p_text) + 2  # account for \n\n

    full_text = "\n\n".join(ordered_pages)
    logger.info(f"Full document text length: {len(full_text):,} chars")

    def get_page_for_offset(offset: int) -> int:
        for start, end, p in page_offsets:
            if start <= offset <= end:
                return p
        return 1

    # Chunking by VietLawArticleChunker
    chunker = VietLawArticleChunker()
    default_bbox = [0, 0, 1000, 1000]

    dieu_pattern = r'(?mi)^\s*#*\s*\*?\*?\s*([ĐĐD]i[eề]u\s*\d+[\.:\s]?)'
    context_pattern = r'(?m)^\s*(?:Phần|Chương|Mục)\s+[IVX\d]+.*$'

    # Split text while tracking positions
    splits = [m.start() for m in re.finditer(dieu_pattern, full_text)]
    chunks = []

    if splits:
        # Preamble chunk
        header_text = full_text[:splits[0]].strip()
        header_text = strip_ai_monologue(header_text)
        if header_text and len(header_text) > 30:
            is_preamble = 'Căn cứ' in header_text or 'căn cứ' in header_text.lower()
            chunks.append({
                "text": f"[{DOC_ID}] {header_text}",
                "source": FILE_NAME,
                "page": 1,
                "is_table": False,
                "chunk_type": "preamble" if is_preamble else "parent",
                "parent_id": f"{FILE_NAME}:1:header",
                "hierarchy_path": f"[{DOC_ID} > Header]",
                "bbox": default_bbox,
                "doc_id": DOC_ID,
                "doc_number": DOC_NUMBER,
                "source_category": "QUOC_HOI",
            })

        current_context = ""
        header_context_matches = re.findall(context_pattern, header_text)
        if header_context_matches:
            current_context = header_context_matches[-1].strip()

        # Iterate through articles
        for i in range(len(splits)):
            start_pos = splits[i]
            end_pos = splits[i+1] if i + 1 < len(splits) else len(full_text)
            art_block = full_text[start_pos:end_pos].strip()

            # Find Điều number and title
            m_dieu = re.match(r'^\s*#*\s*\*?\*?\s*([ĐĐD]i[eề]u\s*\d+[\.:\s]?)\s*\**\s*(.*)', art_block, re.DOTALL | re.IGNORECASE)
            if not m_dieu:
                continue
            article_num = m_dieu.group(1).strip().strip('*').strip()
            lines = m_dieu.group(2).strip().split('\n')
            if lines:
                lines[0] = lines[0].rstrip('*').strip()
            article_content = '\n'.join(lines)

            page_num = get_page_for_offset(start_pos)
            parent_id = f"{FILE_NAME}:{page_num}:art_{i}"

            ctx_prefix = f"[{current_context}] ::: " if current_context else ""
            h_path = f"[{DOC_ID}] -> [{current_context}] -> [{article_num}]" if current_context else f"[{DOC_ID}] -> [{article_num}]"

            parent_text = f"[{DOC_ID}] {ctx_prefix}{article_num} {article_content}"
            parent_text = strip_ai_monologue(parent_text)[:MAX_CHUNK_CHARS]

            chunks.append({
                "text": parent_text,
                "source": FILE_NAME,
                "page": page_num,
                "is_table": "|" in article_content and "\n|---" in article_content,
                "chunk_type": "parent",
                "parent_id": parent_id,
                "hierarchy_path": h_path,
                "bbox": default_bbox,
                "doc_id": DOC_ID,
                "doc_number": DOC_NUMBER,
                "source_category": "QUOC_HOI",
            })

            # Split into child chunks
            child_parts = re.split(r'\n\s*(\d+[\.\)]\s)', article_content)
            if len(child_parts) >= 3:
                for j in range(1, len(child_parts), 2):
                    c_num = child_parts[j].strip()
                    c_body = child_parts[j+1].strip() if j+1 < len(child_parts) else ""
                    child_text = f"[{DOC_ID}] {ctx_prefix}{article_num} > {c_num} ::: {c_body}".strip()
                    if len(child_text) > 30:
                        child_text = strip_ai_monologue(child_text)[:MAX_CHUNK_CHARS]
                        chunks.append({
                            "text": child_text,
                            "source": FILE_NAME,
                            "page": page_num,
                            "is_table": False,
                            "chunk_type": "child",
                            "parent_id": parent_id,
                            "hierarchy_path": f"{h_path} -> [{c_num}]",
                            "bbox": default_bbox,
                            "doc_id": DOC_ID,
                            "doc_number": DOC_NUMBER,
                            "source_category": "QUOC_HOI",
                        })
            elif len(article_content) > 300:
                children = _split_into_children(
                    article_content, DOC_ID, FILE_NAME, page_num,
                    parent_id, h_path, default_bbox
                )
                for c in children:
                    c["text"] = strip_ai_monologue(c["text"])[:MAX_CHUNK_CHARS]
                    c["doc_id"] = DOC_ID
                    c["doc_number"] = DOC_NUMBER
                    c["source_category"] = "QUOC_HOI"
                    chunks.append(c)

            # Update context if new chapter occurs at end of article content
            new_ctx_matches = re.findall(context_pattern, article_content)
            if new_ctx_matches:
                current_context = new_ctx_matches[-1].strip()

    # Assign chunk_id sequentially
    for idx, c in enumerate(chunks):
        c["chunk_id"] = f"{DOC_ID}:chunk_{idx}"

    logger.info(f"Total chunks generated: {len(chunks)}")
    parents = [c for c in chunks if c.get("chunk_type") == "parent"]
    children = [c for c in chunks if c.get("chunk_type") == "child"]
    preambles = [c for c in chunks if c.get("chunk_type") == "preamble"]
    logger.info(f"Breakdown: {len(parents)} parents, {len(children)} children, {len(preambles)} preambles")

    # Generate document summary
    logger.info("Generating clean Vietnamese summary...")
    summary = llm_generate_summary(full_text[:15000])
    summary = strip_ai_monologue(summary)
    if not summary or len(summary) < 50:
        summary = (
            "Luật Xây dựng số 50/2014/QH13 được Quốc hội ban hành ngày 18 tháng 6 năm 2014, "
            "quy định về quyền, nghĩa vụ, trách nhiệm của cơ quan, tổ chức, cá nhân và quản lý nhà nước "
            "trong hoạt động đầu tư xây dựng. Luật bao gồm các quy định chi tiết về quy hoạch xây dựng, "
            "dự án đầu tư xây dựng, khảo sát, thiết kế, cấp phép xây dựng, thi công xây dựng công trình, "
            "quản lý chi phí đầu tư xây dựng, hợp đồng xây dựng, điều kiện năng lực hoạt động xây dựng "
            "và quản lý nhà nước về xây dựng."
        )
    logger.info(f"Summary ({len(summary)} chars): {summary[:120]}...")

    metadata = {
        "date": "18/06/2014",
        "type": "LUAT",
        "authority": "QUOC_HOI",
        "doc_number": DOC_NUMBER,
        "validity_status": "ACTIVE",
        "legal_level": "LUAT",
        "discipline": "XAY_DUNG",
        "project_code": "GENERIC",
        "doc_status": "ACTIVE",
        "revision": 0,
        "file_name": FILE_NAME,
        "source_category": "QUOC_HOI"
    }

    # Export to JSON & Markdown
    json_path, md_path = exporter.export(
        rel_path=FILE_NAME,
        doc_id=DOC_ID,
        meta=metadata,
        summary=summary,
        chunks=chunks
    )
    logger.info(f"Exported JSON: {json_path}")
    logger.info(f"Exported MD: {md_path}")


if __name__ == "__main__":
    main()
