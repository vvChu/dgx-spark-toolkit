"""PDF extraction mixin — page-level processing with Vision OCR fallback."""
import logging
import re

import fitz

from concurrent.futures import ThreadPoolExecutor
from ingestion.cloud_vision import llm_extract_page as _llm_extract_page
from ingestion import pipeline_config

logger = logging.getLogger(__name__)


class ExtractionMixin:
    """Methods for PDF text extraction (digital + OCR)."""

    def is_scanned_pdf(self, file_path):
        """Quick check if a PDF is mostly scanned or digital."""
        try:
            doc = fitz.open(file_path)
            if len(doc) == 0:
                return False
            text = ""
            for i in range(min(3, len(doc))):
                text += doc[i].get_text()
            doc.close()
            return len(text.strip()) < 100
        except Exception as e:
            logger.error(f"  Error checking PDF type for {file_path}: {e}")
            return True

    def _process_single_page(self, file_path: str, i: int, total_pages: int):
        """Helper for parallel page processing.

        Each worker opens its own fitz.Document instance — fitz.Document is not
        thread-safe even for reads, so sharing a single instance across threads
        can cause corrupted page data or segfaults.
        """
        try:
            img_bytes = None
            with fitz.open(file_path) as doc:
                page = doc[i]
                text_raw = page.get_text().strip()

                # Skip digital signature metadata pages
                if i == 0 and len(text_raw) < 80 and ("Người ký" in text_raw or "Cơ quan" in text_raw or "Email" in text_raw):
                    logger.info(f"  Skipping page 1 (digital signature metadata only)")
                    return None

                if len(text_raw) > 100:
                    # Check for OCR spacing issue: count short Vietnamese tokens (1-2 chars)
                    _VN_CHAR_RE = re.compile(r'^[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]+$')
                    tokens = text_raw.split()
                    if len(tokens) > 5:
                        short_vn = sum(1 for t in tokens if len(t) <= 2 and _VN_CHAR_RE.match(t))
                        spacing_ratio = short_vn / len(tokens)
                        if spacing_ratio > 0.30:
                            logger.info(f"  [P1-3] Page {i+1}: spacing_ratio={spacing_ratio:.2f} > 0.30 → forcing OCR (bad text layer)")
                            pix = page.get_pixmap(dpi=150)
                            img_bytes = pix.tobytes("jpeg")
                            # Fall through to OCR path below
                        else:
                            # Digital text quality is good — use fast path
                            dict_text = page.get_text("dict")
                            layout_segments = []
                            full_text_parts = []

                            for block in dict_text.get("blocks", []):
                                if block.get("type") == 0:
                                    block_text = ""
                                    for line in block.get("lines", []):
                                        for span in line.get("spans", []):
                                            span_text = span.get("text")
                                            if span_text:
                                                block_text += span_text + " "

                                    block_text = block_text.strip()
                                    if block_text:
                                        full_text_parts.append(block_text)
                                        pipe_count = block_text.count('|')
                                        tab_count = block_text.count('\t')
                                        lines_in_block = block_text.split('\n')
                                        short_fields = sum(1 for l in lines_in_block if len(l.strip()) < 15)
                                        has_digit_runs = len(re.findall(r'\d{1,3}(?:[.,]\d{3})*', block_text)) > 3
                                        is_table_block = (
                                            pipe_count >= 3
                                            or tab_count >= 3
                                            or (short_fields > 3 and has_digit_runs)
                                            or bool(re.search(r'\|.*\|.*\n\|[-:\s|]+\|', block_text))
                                        )
                                        label = "table" if is_table_block else "text"
                                        layout_segments.append({
                                            "label": label,
                                            "text": block_text,
                                            "bbox": list(block.get("bbox", [0, 0, 1000, 1000]))
                                        })

                            raw_text = "\n".join(full_text_parts)

                            # Merge pdfplumber-detected tables into fitz text
                            try:
                                from ingestion.table_extraction import extract_and_merge_tables
                                page_h = page.rect.height if hasattr(page, "rect") else 0.0
                                raw_text = extract_and_merge_tables(
                                    pdf_path=file_path, page_num=i,
                                    fitz_text=raw_text, page_height=page_h,
                                )
                            except Exception as _te:
                                logger.debug(f"  [TABLE-FIX] skipped page {i+1}: {_te}")

                            # Rejoin hard-wrapped paragraph lines
                            try:
                                from ingestion.text_normalizer import rejoin_paragraphs
                                raw_text = rejoin_paragraphs(raw_text)
                            except Exception as _pe:
                                logger.debug(f"  [PARA-FIX] skipped page {i+1}: {_pe}")

                            # Describe embedded figure images using vision LLM
                            try:
                                _has_images = bool(page.get_images(full=True))
                                _has_hinh = bool(re.search(r'Hình\s+\d', raw_text))
                                if _has_images and _has_hinh:
                                    from ingestion.figure_extractor import describe_page_figures
                                    raw_text = describe_page_figures(
                                        doc=doc, page_num=i,
                                        page_text=raw_text, pdf_path=file_path,
                                        max_figures_per_page=2,
                                    )
                            except Exception as _fe:
                                logger.debug(f"  [FIGURE-FIX] skipped page {i+1}: {_fe}")

                            return {
                                "text": raw_text,
                                "page": i + 1,
                                "layout": layout_segments,
                                "source": "digital"
                            }

                else:
                    # Page is scanned/image
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("jpeg")

            # doc is now closed; run the vision call outside the fitz context
            if img_bytes is not None:
                res = _llm_extract_page(img_bytes, page_num=i + 1, digital_text=text_raw)
                if res.get("text", ""):
                    return {
                        "text": res["text"],
                        "page": i + 1,
                        "bbox": res.get("bbox", []),
                        "is_table": res.get("is_table", False),
                        "layout": res.get("layout", []),
                        "source": res.get("source", "vision")
                    }
                else:
                    return {"page": i + 1, "error": "No text extracted"}
        except Exception as e:
            logger.error(f"  Error extracting from page {i+1}: {e}")
            return {"page": i + 1, "error": str(e)}

    def extract_pdf(self, file_path):
        """Hybrid extraction: digital text first, Vision OCR fallback page-by-page (Parallel)."""
        chunks = []
        failed_pages = []
        try:
            with fitz.open(file_path) as probe:
                total_pages = len(probe)

            concurrency = min(total_pages, pipeline_config.MAX_OCR_CONCURRENCY)
            with ThreadPoolExecutor(max_workers=concurrency) as page_executor:
                futures = [
                    page_executor.submit(self._process_single_page, file_path, i, total_pages)
                    for i in range(total_pages)
                ]
                for future in futures:
                    res = future.result()
                    if res is None:
                        continue
                    if "error" in res:
                        failed_pages.append(res["page"])
                    else:
                        chunks.append(res)

            chunks.sort(key=lambda x: x["page"])
        except Exception as e:
            logger.error(f"  Critical error: Could not process {file_path}: {e}")
            return [], [0]

        return chunks, failed_pages
