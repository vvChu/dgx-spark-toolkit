"""Post-OCR Structural Validator.

Detects and fixes common OCR hallucination patterns BEFORE chunking:
  1. Strips hallucinated markdown tables on non-table pages
  2. Detects anomalous pages (too short = possible OCR failure)
  3. Strips orphan number-only lines (page numbers leaked through)

Runs as part of the s05_chunking pipeline, after cross-page joining
and article sequence validation, before per-page chunking.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Hallucinated table detection ────────────────────────────────────────────

# Pattern: markdown table with header + separator + rows
_TABLE_BLOCK_RE = re.compile(
    r'(\n?\|[^\n]+\|\n\|[\s:|-]+\|\n(?:\|[^\n]+\|\n?)+)',
    re.MULTILINE
)

# Tables that look like hallucination: very short content cells (single char/number)
_HALLUC_TABLE_RE = re.compile(
    r'\|[^\n]{1,8}\|[^\n]{1,8}\|'  # cells with <=8 chars each
)

# Known hallucinated table patterns from QH13 corpus
_KNOWN_HALLUC_PATTERNS = [
    re.compile(r'\|\s*STT\s*\|\s*Nội dung\s*\|', re.IGNORECASE),
    re.compile(r'\|\s*\d\s*\|\s*[a-z]\s*\|'),           # | 1 | a |
    re.compile(r'\|\s*TT\s*\|\s*Nội dung\s*\|', re.IGNORECASE),
]


def strip_hallucinated_tables(text: str, is_table_page: bool = False) -> str:
    """Remove markdown tables that are likely OCR hallucinations.

    Strategy:
    - If the page is classified as a table page (SCAN_COMPLEX), keep all tables
    - Otherwise, check each table block for hallucination signals:
      1. Known hallucination patterns (STT | Nội dung | ...)
      2. Very short cell contents (single chars/numbers)
      3. Few rows (<= 3) with trivial content

    Args:
        text: OCR output text
        is_table_page: True if page was classified as SCAN_COMPLEX

    Returns:
        Text with hallucinated tables removed
    """
    if is_table_page:
        return text  # Trust tables on table-classified pages

    tables = list(_TABLE_BLOCK_RE.finditer(text))
    if not tables:
        return text

    removals = []
    for m in tables:
        table_text = m.group(0)

        # Check 1: Known hallucination patterns
        is_known_halluc = any(p.search(table_text) for p in _KNOWN_HALLUC_PATTERNS)
        if is_known_halluc:
            removals.append((m.start(), m.end()))
            logger.info(f"  [PostOCR] Stripped hallucinated table (known pattern): "
                        f"{table_text[:80]!r}")
            continue

        # Check 2: All cells are trivially short (<=3 chars of content)
        rows = [r for r in table_text.strip().split('\n') if '|' in r and not re.match(r'^\|[\s:-]+\|$', r)]
        if rows:
            cells = []
            for row in rows:
                parts = [c.strip() for c in row.split('|') if c.strip()]
                cells.extend(parts)
            if cells:
                avg_len = sum(len(c) for c in cells) / len(cells)
                if avg_len <= 3 and len(rows) <= 4:
                    removals.append((m.start(), m.end()))
                    logger.info(f"  [PostOCR] Stripped hallucinated table (trivial cells, "
                                f"avg={avg_len:.1f} chars): {table_text[:60]!r}")
                    continue

    # Apply removals in reverse order to preserve positions
    if removals:
        result = text
        for start, end in reversed(removals):
            result = result[:start] + result[end:]
        return result

    return text


# ── Anomalous page detection ───────────────────────────────────────────────

def detect_anomalous_pages(
    page_texts: list[str],
    min_ratio: float = 0.25,
    min_abs_chars: int = 50,
) -> list[int]:
    """Detect pages with suspiciously little content (possible OCR failure).

    A page is anomalous if:
    - Its char count < min_ratio * median page length
    - AND its char count < min_abs_chars

    Args:
        page_texts: List of OCR text for each page (0-indexed)
        min_ratio: Minimum ratio vs median page length
        min_abs_chars: Minimum absolute char count

    Returns:
        List of 0-indexed page numbers that are anomalous
    """
    if len(page_texts) < 3:
        return []

    lengths = [len(t.strip()) for t in page_texts]
    sorted_lengths = sorted(lengths)
    median_len = sorted_lengths[len(sorted_lengths) // 2]

    if median_len < 100:
        return []  # Document is too short to judge

    threshold = max(min_abs_chars, median_len * min_ratio)

    anomalous = []
    for i, length in enumerate(lengths):
        if length < threshold and length < median_len * min_ratio:
            anomalous.append(i)
            logger.warning(
                f"  [PostOCR] Page {i+1} anomalous: {length} chars "
                f"(threshold={threshold:.0f}, median={median_len})"
            )

    return anomalous


# ── Orphan page number stripping ────────────────────────────────────────────

_ORPHAN_PAGE_NUM_RE = re.compile(r'^\s*\d{1,4}\s*$', re.MULTILINE)


def strip_orphan_page_numbers(text: str) -> str:
    """Strip standalone numbers that are orphaned page numbers.

    Only strips numbers that are on their own line and could be page numbers.
    Preserves numbers that are part of lists or content.
    """
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Is this a standalone number (1-4 digits)?
        if re.match(r'^\d{1,4}$', stripped):
            # Check context: if surrounded by empty lines or at start/end, it's a page number
            prev_empty = (i == 0 or not lines[i-1].strip())
            next_empty = (i == len(lines)-1 or not lines[i+1].strip())
            if prev_empty or next_empty:
                logger.debug(f"  [PostOCR] Stripped orphan page number: {stripped}")
                continue
        result.append(line)
    return '\n'.join(result)


# ── Main public function ────────────────────────────────────────────────────

def validate_and_clean_ocr(
    text: str,
    page_num: int = 0,
    is_table_page: bool = False,
) -> str:
    """Run all post-OCR validations on a single page's OCR output.

    Call this AFTER OCR extraction, BEFORE chunking.

    Args:
        text: Raw OCR text for one page
        page_num: Page number (for logging)
        is_table_page: Whether this page was classified as having tables

    Returns:
        Cleaned text with hallucinations removed
    """
    if not text or not text.strip():
        return text

    original_len = len(text)

    # 1. Strip hallucinated tables
    text = strip_hallucinated_tables(text, is_table_page)

    # 2. Strip orphan page numbers
    text = strip_orphan_page_numbers(text)

    cleaned_len = len(text)
    if cleaned_len < original_len:
        delta = original_len - cleaned_len
        logger.info(f"  [PostOCR] Page {page_num+1}: cleaned {delta} chars "
                    f"({original_len} → {cleaned_len})")

    return text
