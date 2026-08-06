"""doc_boundary.py — Technical Standard Content Boundary Extractor.

For QCVN / TCVN / TCCS / tiêu chuẩn ngành documents that are bundled inside an
issuing Thông tư or Quyết định, this module strips the issuing-document pages
and returns only the raw technical-standard content for chunking / embedding.

For standalone legal documents (Nghị định, Thông tư, Quyết định, etc.)
strip_issuing_document() is a **no-op** — it returns raw_pages unchanged.

Usage:
    from ingestion.doc_boundary import strip_issuing_document
    doc.raw_pages = strip_issuing_document(doc.raw_pages, doc_type=doc.meta.get("type"))
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports

logger = logging.getLogger(__name__)

# ── Document types that may contain an issuing document wrapper ───────────────
TECHNICAL_STANDARD_TYPES: set[str] = {"QCVN", "TCVN", "TCCS", "TIEU_CHUAN_NGANH", "KY_THUAT"}

# ── Patterns to detect technical-standard header anywhere in page text ────────
_STANDARD_HEADER_PATTERNS: list[re.Pattern] = [
    re.compile(r'QCVN\s+\d+[:\-]\d{4}(?:\/[A-ZĐ]+)?', re.IGNORECASE),
    re.compile(r'TCVN\s+\d+[:\-]\d{4}', re.IGNORECASE),
    re.compile(r'TCCS\s+\d+\/\d{4}(?:\/[A-ZĐ]+)?', re.IGNORECASE),
    re.compile(r'(?:14|22|QCĐP|QCPL)TCN\s+\d+', re.IGNORECASE),
]

# ── Patterns that mark the TRUE START of technical content ────────────────────
# Ordered by reliability (most unambiguous first).
_CONTENT_START_PATTERNS: list[re.Pattern] = [
    re.compile(r'(?m)^Lời nói đầu\s*$', re.IGNORECASE),
    re.compile(r'(?m)^1\.\s+QUY ĐỊNH CHUNG\s*$', re.IGNORECASE),
    re.compile(r'(?m)^CHƯƠNG\s+I[\.\s]', re.IGNORECASE),
    re.compile(r'(?m)^Phần\s+(?:I|1)[\.\s]', re.IGNORECASE),
    re.compile(r'(?m)^I\.\s+QUY ĐỊNH', re.IGNORECASE),
]

# ── Patterns that identify an *issuing* document page (Thông tư / QĐ) ─────────
_ISSUING_DOC_PATTERNS: list[re.Pattern] = [
    re.compile(r'(?m)^Điều\s+1\.\s+Ban hành', re.IGNORECASE),
    re.compile(r'(?m)^Điều\s+1\.\s+Phê duyệt', re.IGNORECASE),
    re.compile(r'THÔNG TƯ\s*\n.*\s*Ban hành', re.IGNORECASE | re.DOTALL),
    re.compile(r'Thông tư\s+số\s+\d+\/\d{4}\/TT-', re.IGNORECASE),
    re.compile(r'Quyết định\s+số\s+\d+\/\d{4}\/Q[ĐD]-', re.IGNORECASE),
    # Digital signature metadata page (chữ ký điện tử)
    re.compile(r'Người ký\s*:.*(?:Email|Cơ quan|Thời gian ký)', re.IGNORECASE | re.DOTALL),
    re.compile(r'Thời gian ký\s*:\s*\d{2}\.\d{2}\.\d{4}', re.IGNORECASE),
    re.compile(r'(?:chinhphu\.vn|thongtinchinhphu@)', re.IGNORECASE),
    # Distribution list page (danh sách phân phối)
    re.compile(r'(?m)^-\s*Thủ tướng Chính phủ', re.IGNORECASE),
    re.compile(r'(?m)^-\s*Các Bộ,\s*cơ quan ngang Bộ', re.IGNORECASE),
    re.compile(r'(?m)^-\s*(?:HĐND|UBND)\s+các tỉnh', re.IGNORECASE),
    re.compile(r'BỘ TRƯỞNG\s*\n\s*[A-ZĐÀÁẢÃẠĂẮẰẲẴẶ][a-zàáảãạăắằẳẵặâấầẩẫậ]', re.DOTALL),
]

# ── Max pages to scan for the technical standard header ───────────────────────
_SCAN_WINDOW = 8


def detect_technical_standard(raw_pages: list) -> str | None:
    """Scan first _SCAN_WINDOW pages for a technical-standard identifier.

    Returns the matched standard_id string (e.g. 'QCVN 119:2019/BTTTT')
    or None if not found.
    """
    scan_text = "\n".join(
        (p.text if hasattr(p, "text") else p.get("text", ""))
        for p in raw_pages[:_SCAN_WINDOW]
    )
    for pat in _STANDARD_HEADER_PATTERNS:
        m = pat.search(scan_text)
        if m:
            return m.group(0).strip()
    return None


def _page_text(page) -> str:
    """Unified accessor for page text regardless of dict/RawPage form."""
    return page.text if hasattr(page, "text") else page.get("text", "")


def _has_issuing_doc_marker(text: str) -> bool:
    return any(p.search(text) for p in _ISSUING_DOC_PATTERNS)


def _has_content_start_marker(text: str) -> bool:
    return any(p.search(text) for p in _CONTENT_START_PATTERNS)


# ── TOC page detection ────────────────────────────────────────────────────────
# A TOC page has many lines that look like "X.Y ... section title ... 12"
_TOC_LINE_RE = re.compile(
    r'^\d+\.\d+\.?\s+.{5,60}\s+\d{1,3}\s*$|'
    r'^Phụ lục\s+[A-Z]\s+.{5,60}\s+\d{1,3}\s*$',
    re.MULTILINE
)


def _is_toc_page(text: str) -> bool:
    """Return True if the page is likely a Table of Contents."""
    matches = _TOC_LINE_RE.findall(text)
    lines = [l for l in text.split('\n') if l.strip()]
    if not lines:
        return False
    return len(matches) >= 3 and len(matches) / len(lines) > 0.3


def find_technical_content_start(raw_pages: list, standard_id: str) -> int:
    """Find the page index where real technical content begins.

    Strategy:
    1. Identify the last issuing-document page (pages with Thông tư/QĐ markers).
    2. From that point, scan forward for explicit content-start markers
       (Lời nói đầu, 1. QUY ĐỊNH CHUNG, CHƯƠNG I, etc.) — these are preferred.
    3. If no content-start marker found, fall back to the first page carrying the
       standalone standard header *after* the issuing-document pages.
    4. Return 0 if nothing detected (keep all pages).
    """
    # Phase 1: find last issuing-doc page index
    issuing_until = -1
    for i, page in enumerate(raw_pages[:_SCAN_WINDOW]):
        text = _page_text(page)
        if _has_issuing_doc_marker(text):
            issuing_until = i
            logger.debug(f"  [doc_boundary] Issuing doc marker on page index {i}")

    # Phase 2: scan pages AFTER issuing doc for explicit content-start markers
    search_from = issuing_until + 1  # pages beyond the last issuing-doc page
    for i, page in enumerate(raw_pages[search_from:], start=search_from):
        text = _page_text(page)
        # Skip TOC pages (P2 fix)
        if _is_toc_page(text):
            logger.debug(f"  [doc_boundary] Skipping TOC page at index {i}")
            continue
        if _has_content_start_marker(text):
            logger.info(f"  [doc_boundary] Technical content starts at page index {i} (content-start marker)")
            return i

    # Phase 3: fallback — first page with standard header after issuing doc
    fallback_from = max(0, issuing_until)
    for i, page in enumerate(raw_pages[fallback_from:], start=fallback_from):
        text = _page_text(page)
        for pat in _STANDARD_HEADER_PATTERNS:
            if pat.search(text) and not _has_issuing_doc_marker(text):
                logger.info(f"  [doc_boundary] Technical content starts at page index {i} (standard header fallback)")
                return i

    logger.warning(f"  [doc_boundary] Could not find content start for '{standard_id}', keeping all pages")
    return 0



def strip_issuing_document(raw_pages: list, doc_type: str | None = None) -> list:
    """Strip the issuing Thông tư / Quyết định pages from a technical standard PDF.

    For non-technical-standard doc_types this is a no-op.

    Args:
        raw_pages: list of RawPage objects or dicts with 'text'/'page' keys.
        doc_type:  classified document type (e.g. 'QCVN', 'TCVN', 'KY_THUAT').

    Returns:
        Filtered raw_pages starting from the technical content boundary.
    """
    if not raw_pages:
        return raw_pages

    # Quick exit: not a technical standard type → no-op
    is_tech_standard = (doc_type in TECHNICAL_STANDARD_TYPES) if doc_type else False

    # Even without explicit doc_type, auto-detect from content
    standard_id = detect_technical_standard(raw_pages)
    if not standard_id and not is_tech_standard:
        return raw_pages  # definitely not a technical standard

    if not standard_id:
        # doc_type says technical but no clear header found — scan for issuing markers only
        has_issuing = any(
            _has_issuing_doc_marker(_page_text(p))
            for p in raw_pages[:4]
        )
        if not has_issuing:
            return raw_pages

    logger.info(f"  [doc_boundary] Technical standard detected: '{standard_id}' (doc_type={doc_type})")

    start_idx = find_technical_content_start(raw_pages, standard_id or "")

    if start_idx == 0:
        return raw_pages  # nothing to strip

    stripped = raw_pages[start_idx:]
    logger.info(
        f"  [doc_boundary] Stripped {start_idx} issuing-doc page(s). "
        f"Remaining: {len(stripped)}/{len(raw_pages)} pages."
    )
    return stripped
