"""
table_extraction.py — pdfplumber-based table detection for RAG pipeline.

Extracts structured tables from PDF pages that fitz extracts as fragmented
cell-by-cell text, and replaces them with proper markdown |col|col| format.

Usage:
    from ingestion.table_extraction import extract_and_merge_tables

    final_text = extract_and_merge_tables(
        pdf_path=file_path,
        page_num=i,          # 0-indexed (same as fitz page index)
        fitz_text="...",     # raw text from fitz blocks
        page_height=page.rect.height,
    )
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Table settings tuned for Vietnamese legal / QCVN technical PDFs.
# "lines" strategy works well for ruled tables (grid lines visible).
# Fallback to "text" strategy handles unruled tables.
# ─────────────────────────────────────────────────────────────
_TABLE_SETTINGS_RULED = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 4,
    "join_tolerance": 4,
    "edge_min_length": 10,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
}

_TABLE_SETTINGS_TEXT = {
    "vertical_strategy": "text",
    "horizontal_strategy": "lines",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "edge_min_length": 10,
}


# ─────────────────────────────────────────────────────────────
# Common Vietnamese words / token prefixes found in table headers.
# Used to detect reversed text from rotated PDF text layers.
# ─────────────────────────────────────────────────────────────
_VN_HEADER_WORDS = frozenset([
    "Kích", "thước", "Dung", "sai", "nhất", "nhỏ", "lớn", "Nhỏ", "Lớn",
    "Mã", "chiều", "rộng", "danh", "nghĩa", "đường", "kính", "vành",
    "Chu", "vi", "ứng", "với", "Độ", "Hình", "Ghi", "chú", "Loại",
    "Ký", "hiệu", "cớưht", "tấhn", "ias", "gnuD",  # known mirrored tokens
])

_MIRRORED_TOKENS = frozenset(["cớưht", "tấhn", "ias", "ộĐ", "nớL", "ỏhN", "gnuD", "hcíK"])


def _fix_mirrored_text(text: str) -> str:
    """Detect and fix reversed Vietnamese text from rotated PDF text layers.

    In some technical PDFs, the text layer for rotated column headers is stored
    with reversed character order. This function detects that pattern and reverses
    the text back to normal reading order.

    Detection heuristic: if any token in the text is a known mirrored Vietnamese
    token, reverse the entire cell string.
    """
    if not text:
        return text
    tokens = text.split()
    # Fast check: if any token is a known mirrored fragment, reverse everything
    if any(t in _MIRRORED_TOKENS for t in tokens):
        return text[::-1].strip()
    return text


def _clean_cell(cell) -> str:
    """Normalize a single table cell: strip whitespace, collapse internal newlines,
    and fix mirrored text from rotated PDF text layers."""
    if cell is None:
        return ""
    text = str(cell).strip().replace("\n", " ").replace("  ", " ")
    return _fix_mirrored_text(text)


def _cells_to_markdown(cells: list[list]) -> str:
    """Convert a pdfplumber cell grid into a markdown table string.

    Args:
        cells: 2D list from pdfplumber table.extract(), rows × cols.

    Returns:
        Markdown table string. Empty string if cells are invalid.
    """
    if not cells or len(cells) < 2:
        return ""

    # Clean and pad all rows to same width
    cleaned = [[_clean_cell(c) for c in row] for row in cells]
    max_cols = max(len(r) for r in cleaned)
    if max_cols < 2:
        return ""
    padded = [r + [""] * (max_cols - len(r)) for r in cleaned]

    # Filter out entirely empty rows
    non_empty = [r for r in padded if any(c.strip() for c in r)]
    if len(non_empty) < 2:
        return ""

    lines: list[str] = []
    # Header row
    header = non_empty[0]
    lines.append("| " + " | ".join(header) + " |")
    # Separator
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # Data rows
    for row in non_empty[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _validate_markdown_table(md: str) -> bool:
    """Validate a markdown table — reject garbled/empty tables.

    Returns True if the table looks valid, False if it should be discarded.
    Checks:
    1. >50% of data cells empty or ≤2 chars → reject
    2. >60% of cell tokens are 1-3 char fragments → reject (word-level garbling)
    """
    lines = [l for l in md.strip().split("\n") if l.strip()]
    if len(lines) < 3:  # header + separator + at least 1 data row
        return False

    # Skip header (line 0) and separator (line 1)
    data_lines = lines[2:]
    total_cells = 0
    empty_or_tiny = 0
    all_tokens = []

    for line in data_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        for cell in cells:
            total_cells += 1
            if len(cell) <= 2:
                empty_or_tiny += 1
            # Collect tokens for fragment analysis
            all_tokens.extend(cell.split())

    if total_cells == 0:
        return False

    # Check 1: too many empty cells
    if empty_or_tiny / total_cells > 0.50:
        logger.info(f"  [TABLE] Rejected garbled table: {empty_or_tiny}/{total_cells} cells empty/tiny")
        return False

    # Check 2: too many word fragments (1-3 char tokens)
    if all_tokens:
        fragment_count = sum(1 for t in all_tokens if len(t) <= 3)
        if len(all_tokens) > 5 and fragment_count / len(all_tokens) > 0.60:
            logger.info(f"  [TABLE] Rejected garbled table: {fragment_count}/{len(all_tokens)} fragment tokens")
            return False

    return True


def _extract_page_tables(pdf_path: str, page_num: int) -> list[dict]:
    """Open the PDF with pdfplumber and extract all tables from page_num.

    Args:
        pdf_path: Absolute path to the PDF file.
        page_num: 0-indexed page number (same as fitz indexing).

    Returns:
        List of dicts with keys: bbox (x0,top,x1,bottom), markdown, rows, cols.
    """
    try:
        import pdfplumber  # local import — avoid slow startup if unused
    except ImportError:
        logger.warning("[TABLE] pdfplumber not installed — skipping table extraction")
        return []

    result = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num >= len(pdf.pages):
                return []
            page = pdf.pages[page_num]

            # Try ruled-line strategy first (catches explicit grid tables)
            tables = page.find_tables(table_settings=_TABLE_SETTINGS_RULED)

            # Fallback to text-alignment strategy if nothing found
            if not tables:
                tables = page.find_tables(table_settings=_TABLE_SETTINGS_TEXT)

            for tbl in tables:
                cells = tbl.extract()
                if not cells or len(cells) < 2:
                    continue
                max_cols = max(len(r) for r in cells) if cells else 0
                if max_cols < 2:
                    continue

                md = _cells_to_markdown(cells)
                if not md:
                    continue

                result.append({
                    "bbox": tbl.bbox,   # (x0, top, x1, bottom) in PDF pts coords
                    "markdown": md,
                    "rows": len(cells),
                    "cols": max_cols,
                })

        if result:
            logger.info(f"  [TABLE] Page {page_num + 1}: found {len(result)} table(s)")

    except Exception as e:
        logger.warning(f"  [TABLE] pdfplumber error on page {page_num + 1}: {e}")

    return result


# ─────────────────────────────────────────────────────────────
# Pattern to detect standalone "Bảng X" or "Bảng A.Y" labels
# that should be preserved as table headers in the output.
# ─────────────────────────────────────────────────────────────
_TABLE_LABEL_RE = re.compile(
    r"Bảng\s+[A-Z]?\d+[\.\d]*\s*[-–—]?\s*.{0,80}",
    re.IGNORECASE
)


def _find_table_label_before(text: str, position: int, search_window: int = 300) -> Optional[str]:
    """Search backwards from `position` in `text` for a Bảng label.

    Returns the label string if found within the search window, else None.
    """
    start = max(0, position - search_window)
    segment = text[start:position]
    matches = list(_TABLE_LABEL_RE.finditer(segment))
    if matches:
        return matches[-1].group(0).strip()
    return None


def extract_and_merge_tables(
    pdf_path: str,
    page_num: int,
    fitz_text: str,
    page_height: float = 0.0,
) -> str:
    """Extract tables from a page and merge them into the fitz text.

    Strategy:
    1. Extract all tables from the page using pdfplumber.
    2. Detect corresponding "Bảng X - Title" labels in fitz_text.
    3. Replace the fragmented numeric/cell content in fitz_text with a
       proper markdown table. The replacement happens by detecting: 
       - isolated number-only lines (classic cell fragmentation pattern)
       - blocks of very short lines clustered together
    4. Return the merged text.

    Args:
        pdf_path:    Path to original PDF.
        page_num:    0-indexed page number.
        fitz_text:   Raw text string assembled from fitz blocks.
        page_height: PDF page height in points (for coordinate math).

    Returns:
        Cleaned text with markdown tables inserted where appropriate.
    """
    tables = _extract_page_tables(pdf_path, page_num)

    if not tables:
        return fitz_text

    # We'll replace blocks of fragmented table text in fitz_text.
    # The approach: split fitz_text into lines and annotate "table spans"
    # where fragmented cells appear, then substitute with markdown tables.
    result_text = _replace_fragmented_tables(fitz_text, tables, page_num)
    return result_text


# ─────────────────────────────────────────────────────────────
# Heuristics to detect fragmented table regions in fitz text
# ─────────────────────────────────────────────────────────────

# A line that contains only numbers / decimals / dimension codes
_NUMERIC_ONLY_LINE = re.compile(
    r"^[\s\d+\-±.,×xX/()°mmkgkNkPa%³²mÅ]*$"
)
# A line that is very short (likely a table dimension value or code)
_SHORT_STANDALONE_LINE = re.compile(r"^\S{0,15}\s*$")

# Lines beginning with dimension codes like "1.10", "MT 1.85" (table row IDs)
_TABLE_ROW_IDENTIFIER = re.compile(
    r"^(?:MT|WM|LF|[A-Z]{0,3})?\s*\d{1,2}[\.,]\d{2}\s"
)


def _is_fragmented_table_line(line: str) -> bool:
    """Return True if a line looks like a fragmented table cell value."""
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 60:
        return False
    # Pure numeric/unit lines
    if _NUMERIC_ONLY_LINE.match(stripped):
        return True
    # Table row identifiers (dimension codes)
    if _TABLE_ROW_IDENTIFIER.match(stripped):
        return True
    # Very short lines that are single values or codes (not sentences)
    words = stripped.split()
    if len(words) <= 2 and re.search(r"\d", stripped):
        return True
    return False


def _replace_fragmented_tables(fitz_text: str, tables: list[dict], page_num: int) -> str:
    """Replace fragmented table regions in fitz_text with markdown tables.

    For each pdfplumber table detected:
    1. Find the "Bảng X" label line in fitz_text
    2. Find the fragmented cell range after the label
    3. Replace with the markdown table

    Graceful fallback: if we can't locate the fragmentation, append each 
    table after its label with a comment.
    """
    if not tables:
        return fitz_text

    lines = fitz_text.split("\n")
    n = len(lines)
    used_tables: set[int] = set()

    # Scan through lines and detect "Bảng X" labels, then check if
    # the lines immediately after are fragmented table data
    result_lines: list[str] = []
    i = 0

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Check if this line is a "Bảng X..." label
        is_bảng_label = bool(_TABLE_LABEL_RE.match(stripped)) if stripped else False

        if is_bảng_label and tables:
            # Look ahead to see if the following lines are fragmented
            j = i + 1
            fragmented_start = j
            frag_count = 0

            while j < n and j < i + 60:  # look max 60 lines ahead
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                if _is_fragmented_table_line(next_line):
                    frag_count += 1
                    j += 1
                elif frag_count > 0 and len(next_line) > 80:
                    # Long line — likely back to regular text
                    break
                elif frag_count > 0:
                    j += 1  # absorb short lines even if not perfectly numeric
                else:
                    break

            if frag_count >= 3:
                # Found fragmented table region — replace with markdown
                # Pick the best matching pdfplumber table (use first unused)
                chosen_table = None
                for ti, tbl in enumerate(tables):
                    if ti not in used_tables:
                        chosen_table = tbl
                        used_tables.add(ti)
                        break

                if chosen_table:
                    result_lines.append(line)  # keep the label
                    result_lines.append("")
                    result_lines.append(chosen_table["markdown"])
                    result_lines.append("")
                    logger.info(
                        f"  [TABLE] Page {page_num + 1}: replaced {frag_count} fragmented lines "
                        f"after '{stripped[:40]}' with {chosen_table['rows']}×{chosen_table['cols']} table"
                    )
                    i = j  # skip all fragmented lines
                    continue

        result_lines.append(line)
        i += 1

    # Append any tables that weren't matched (at end of page content)
    for ti, tbl in enumerate(tables):
        if ti not in used_tables:
            md = tbl["markdown"]

            # Fix 2: Validate table quality — skip garbled tables
            if not _validate_markdown_table(md):
                logger.info(f"  [TABLE] Page {page_num + 1}: skipped garbled unmatched table {ti + 1}")
                continue

            # Fix 1: Try to remove the raw fragmented text that corresponds
            # to this table to avoid duplication
            result_lines = _remove_trailing_fragmented_block(result_lines)

            result_lines.append("")
            result_lines.append(f"*[Bảng kỹ thuật — trang {page_num + 1}]*")
            result_lines.append("")
            result_lines.append(md)
            result_lines.append("")
            logger.info(f"  [TABLE] Page {page_num + 1}: appended unmatched table {ti + 1}")

    return "\n".join(result_lines)


def _remove_trailing_fragmented_block(lines: list[str]) -> list[str]:
    """Remove trailing block of fragmented short lines that likely represent
    raw table cell text which will be replaced by a proper markdown table.

    Scans backwards from the end of `lines` and removes consecutive clusters
    of short lines (≤60 chars, ≤3 words) that span ≥5 non-empty lines.
    """
    if not lines:
        return lines

    # Scan backwards to find the fragmented block
    i = len(lines) - 1

    # Skip trailing blank lines
    while i >= 0 and not lines[i].strip():
        i -= 1

    if i < 0:
        return lines

    # Count consecutive short/fragmented lines from the bottom
    frag_end = i + 1  # exclusive end
    frag_count = 0

    while i >= 0:
        stripped = lines[i].strip()
        if not stripped:
            # Allow blank lines within the block
            i -= 1
            continue
        words = stripped.split()
        if len(stripped) <= 60 and len(words) <= 4:
            frag_count += 1
            i -= 1
        else:
            break

    frag_start = i + 1  # inclusive start

    # Only remove if we found a substantial fragmented block (≥5 short lines)
    if frag_count >= 5:
        logger.info(
            f"  [TABLE] Removed {frag_count} trailing fragmented lines "
            f"(lines {frag_start}-{frag_end-1})"
        )
        return lines[:frag_start]

    return lines
