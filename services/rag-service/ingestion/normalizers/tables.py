"""Table detection and normalization utilities.

Provides garbled table detection, table chunk classification,
and raw pipe table normalization for Markdown export.
"""
import re
import logging

logger = logging.getLogger(__name__)

_MARKDOWN_TABLE_RE = re.compile(r'\|.*\|.*\n\|[-:\s|]+\|')


def detect_garbled_table(text: str) -> bool:
    """Heuristic: detect if text is likely a garbled OCR table.

    Indicators:
    * Many very short lines (< 25 chars)
    * Presence of isolated markers like "X", "Χ" (Greek Chi), "x"
    * Keywords like "Vốn NĐT", "NSNN", "NSTP", "NSTW"
    * High ratio of lines with only 1–3 words
    * Unicode garbage characters (ŧ, Ė, ΧŲ, etc.)
    * HTML/LaTeX tags (<math>, <br>, <sup>)
    * Highly repetitive text blocks
    """
    if not text or len(text) < 50:
        return False

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 3:
        return False

    short_lines = sum(1 for l in lines if len(l) < 25)
    short_ratio = short_lines / len(lines) if lines else 0

    table_keywords = ["Vốn NĐT", "NSNN", "NSTP", "NSTW", "NSTƯ"]
    keyword_count = sum(1 for kw in table_keywords if kw in text)

    isolated_marks = sum(1 for l in lines if l in ("X", "Χ", "Х", "x", ".", "-", "_", "*"))
    mark_ratio = isolated_marks / len(lines) if lines else 0

    if short_ratio > 0.5 and (keyword_count >= 2 or mark_ratio > 0.1):
        return True
    if short_ratio > 0.7 and mark_ratio > 0.05:
        return True

    _GARBAGE_CHARS = set('ŧĖΧŲġşŷįďŕŝΈΊϐ')
    garbage_count = sum(1 for c in text if c in _GARBAGE_CHARS)
    if garbage_count > 5:
        return True

    html_tag_count = (
        text.count('<math>') + text.count('</math>')
        + text.count('<br>') + text.count('<br/>')
        + text.count('<sup>') + text.count('</sup>')
    )
    if html_tag_count >= 3:
        return True

    if len(text) > 500:
        sample = text[:200].strip()
        if sample and text.count(sample) >= 3:
            return True

    return False


def is_table_chunk(text: str, page_is_table: bool = False) -> bool:
    """Unified table detection: returns True if text looks like a table."""
    if page_is_table:
        return True
    if _MARKDOWN_TABLE_RE.search(text):
        return True
    return detect_garbled_table(text)


def fix_raw_pipe_tables(text: str) -> str:
    """Fix pipe-delimited tables that lack Markdown separator rows.

    Detects contiguous blocks of pipe-delimited lines and inserts
    separator rows after the first row in each block.
    """
    if not text or '|' not in text:
        return text

    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 3:
            pipe_block = [line]
            j = i + 1
            has_separator = bool(re.match(r'^\s*\|[\s\-:|]+\|\s*$', stripped))

            while j < len(lines):
                next_stripped = lines[j].strip()
                if next_stripped.startswith('|') and next_stripped.endswith('|') and next_stripped.count('|') >= 3:
                    pipe_block.append(lines[j])
                    if re.match(r'^\s*\|[\s\-:|]+\|\s*$', next_stripped):
                        has_separator = True
                    j += 1
                elif not next_stripped:
                    if j + 1 < len(lines) and lines[j + 1].strip().startswith('|'):
                        pipe_block.append(lines[j])
                        j += 1
                    else:
                        break
                else:
                    break

            if len(pipe_block) >= 2 and not has_separator:
                header = pipe_block[0]
                col_count = header.count('|') - 1
                separator = '| ' + ' | '.join(['---'] * col_count) + ' |'
                result.append(pipe_block[0])
                result.append(separator)
                result.extend(pipe_block[1:])
                logger.info(f"  [P1] Fixed raw pipe table: inserted separator ({col_count} cols, {len(pipe_block)} rows)")
            else:
                result.extend(pipe_block)

            i = j
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


def fix_table_gfm_v2(text: str) -> str:
    """[P1] Enhanced GFM table fixer for multi-line and nested tables.

    Improvements:
    - Handles tables where header row doesn't start/end with |
    - Better detection of header vs data rows (looks at content patterns)
    - Handles multi-line cell content by detecting table boundaries
    - Fixes orphaned separator rows (|---|---| without header above)
    """
    if "|" not in text:
        return text

    lines = text.split("\n")
    fixed: list[str] = []
    in_table = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Count pipes in the line
        pipe_count = stripped.count("|")

        # A pipe-row: starts with | and has at least 3 | characters
        is_pipe_row = (
            stripped.startswith("|") and stripped.endswith("|")
            and pipe_count >= 3
        )

        # Also catch rows that have pipes but don't start/end with them
        # e.g., "STT | Tên | Giá trị" (common in OCR output)
        is_loose_pipe_row = (
            not is_pipe_row
            and pipe_count >= 2
            and bool(re.match(r"^\s*\S.*\|.*\S\s*$", stripped))
            and len(stripped) > 10
        )

        if not is_pipe_row and not is_loose_pipe_row:
            in_table = False
            fixed.append(line)
            continue

        # For loose pipe rows, normalize them to proper pipe format
        if is_loose_pipe_row and not is_pipe_row:
            parts = [p.strip() for p in stripped.split("|")]
            if parts and parts[0] == "":
                parts = parts[1:]
            if parts and parts[-1] == "":
                parts = parts[:-1]
            stripped = "| " + " | ".join(parts) + " |"
            line = stripped
            is_pipe_row = True

        # Check if the NEXT line is a separator
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        is_next_sep = bool(re.match(r"^\|[\s:\-|]+\|$", next_line))

        if is_next_sep:
            in_table = True
            fixed.append(line)
            continue

        if in_table:
            # Already inside a table (separator was seen/inserted) — this is a data row
            fixed.append(line)
            continue

        # First pipe row without a following separator — check if it's a header
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        all_trivial = all(len(c) <= 2 for c in cells)
        has_letters = any(re.search(r"[a-zA-Z\u00c0-\u1ef9]", c) for c in cells)
        all_numeric = all(re.match(r"^[\d.,\s%]+$", c) for c in cells if c)

        is_header = (
            cells
            and not all_trivial
            and all(len(c) < 2000 for c in cells)
            and has_letters
            and not all_numeric
        )
        if is_header:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            fixed.append(line)
            fixed.append(sep)
            in_table = True
        else:
            fixed.append(line)

    return "\n".join(fixed)

