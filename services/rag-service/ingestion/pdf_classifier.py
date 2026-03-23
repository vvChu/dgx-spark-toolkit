"""PDF classification for smart OCR routing.

Classifies PDFs into three tiers to optimize processing:
  - NATIVE:       Digital text layer → PyMuPDF + pdfplumber (skip OCR)
  - SCAN_SIMPLE:  Scanned, simple text → Image preproc + LLM Vision
  - SCAN_COMPLEX: Scanned, complex tables → Image preproc + LLM Vision (table mode)

Usage:
    from ingestion.pdf_classifier import classify_pdf, classify_page, PdfType

    pdf_type = classify_pdf("/path/to/doc.pdf")
    if pdf_type == PdfType.NATIVE:
        ...  # fast digital path

    page_type = classify_page(page, page_index)
    ...
"""

import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class PdfType(str, Enum):
    """PDF processing tier."""
    NATIVE = "NATIVE"              # Digital text — skip OCR
    SCAN_SIMPLE = "SCAN_SIMPLE"    # Scanned, simple layout
    SCAN_COMPLEX = "SCAN_COMPLEX"  # Scanned, complex tables/layout


def classify_pdf(file_path: str, sample_pages: int = 5) -> PdfType:
    """Classify a PDF into one of three processing tiers.

    Samples up to `sample_pages` pages to determine the dominant type.
    Uses character density and image presence as primary signals.

    Args:
        file_path: Absolute path to the PDF file.
        sample_pages: Number of pages to sample (default 5).

    Returns:
        PdfType enum value.
    """
    try:
        import fitz
        doc = fitz.open(file_path)
    except Exception as e:
        logger.warning(f"[CLASSIFY] Cannot open {file_path}: {e} — defaulting to SCAN_COMPLEX")
        return PdfType.SCAN_COMPLEX

    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        return PdfType.SCAN_COMPLEX

    # Sample evenly spaced pages
    step = max(1, total_pages // sample_pages)
    indices = list(range(0, total_pages, step))[:sample_pages]

    total_chars = 0
    total_images = 0
    pages_with_text = 0
    complex_table_signals = 0

    for i in indices:
        page = doc[i]
        text = page.get_text().strip()
        char_count = len(text)
        total_chars += char_count
        image_count = len(page.get_images(full=False))
        total_images += image_count

        if char_count > 100:
            pages_with_text += 1

        # Detect complex table signals
        if _has_complex_table_signals(text):
            complex_table_signals += 1

    doc.close()

    avg_chars = total_chars / len(indices) if indices else 0
    text_ratio = pages_with_text / len(indices) if indices else 0

    # Decision logic
    if avg_chars > 500 and text_ratio > 0.6:
        result = PdfType.NATIVE
    elif total_images > 0 and avg_chars < 100:
        if complex_table_signals >= 1:
            result = PdfType.SCAN_COMPLEX
        else:
            result = PdfType.SCAN_SIMPLE
    elif avg_chars < 200:
        result = PdfType.SCAN_COMPLEX
    else:
        # Mixed content — treat as native if >50% pages have text
        result = PdfType.NATIVE if text_ratio > 0.5 else PdfType.SCAN_SIMPLE

    logger.info(
        f"[CLASSIFY] {file_path.split('/')[-1]}: {result.value} "
        f"(avg_chars={avg_chars:.0f}, text_ratio={text_ratio:.0%}, "
        f"images={total_images}, tables={complex_table_signals})"
    )
    return result


def classify_page(page, page_index: int) -> PdfType:
    """Classify a single page within a PDF.

    Used for per-page routing in mixed PDFs (some pages native, some scanned).

    Args:
        page: fitz.Page object (must be from an open document).
        page_index: 0-based page index for logging.

    Returns:
        PdfType for this specific page.
    """
    text = page.get_text().strip()
    char_count = len(text)
    image_count = len(page.get_images(full=False))

    # Strong text signal — digital page
    if char_count > 300:
        # Check for OCR spacing issues (broken Vietnamese tokens)
        if _has_broken_ocr_spacing(text):
            return PdfType.SCAN_SIMPLE
        return PdfType.NATIVE

    # Very few chars + images → scanned
    if char_count < 100 and image_count > 0:
        if _has_complex_table_signals(text):
            return PdfType.SCAN_COMPLEX
        return PdfType.SCAN_SIMPLE

    # Low char count, no images — could be a blank/signature page
    if char_count < 50:
        return PdfType.SCAN_SIMPLE

    # Moderate text — might be a partially digitized scan
    return PdfType.SCAN_SIMPLE


def _has_complex_table_signals(text: str) -> bool:
    """Detect signals that a page likely contains complex tables.

    Checks for:
    - Technical unit patterns (≤, ≥, m², kN/m³)
    - Dense numeric data
    - Table header keywords
    """
    if not text:
        return False

    # Technical symbols common in QCVN spec tables
    tech_patterns = [
        r'[≤≥±]',
        r'm[²³]',
        r'kN/m',
        r'kg/m',
        r'dB[Am]?',
        r'MHz|GHz|kHz',
    ]
    tech_count = sum(1 for p in tech_patterns if re.search(p, text))

    # Table header keywords
    header_keywords = ['STT', 'Đơn vị', 'ĐVT', 'Quy cách', 'Kích thước', 'Tỷ lệ']
    keyword_count = sum(1 for kw in header_keywords if kw in text)

    return tech_count >= 2 or keyword_count >= 2


def _has_broken_ocr_spacing(text: str) -> bool:
    """Check if digital text has OCR spacing issues (broken Vietnamese tokens).

    Returns True if >30% of tokens are single Vietnamese characters,
    indicating a bad text layer that should be re-OCR'd.
    """
    _VN_CHAR_RE = re.compile(
        r'^[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ'
        r'ÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọ'
        r'ôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]+$'
    )
    tokens = text.split()
    if len(tokens) <= 5:
        return False
    short_vn = sum(1 for t in tokens if len(t) <= 2 and _VN_CHAR_RE.match(t))
    return (short_vn / len(tokens)) > 0.30
