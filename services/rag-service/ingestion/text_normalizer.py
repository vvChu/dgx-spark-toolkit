"""Text Normalizer for Markdown Export — Facade Module.

This module re-exports all public functions from the `ingestion.normalizers`
package and provides the composite `normalize_chunk_text()` pipeline.

All existing imports like `from ingestion.text_normalizer import X`
continue to work unchanged.

Sub-modules (under ingestion/normalizers/):
    ocr_fixes.py   — OCR spacing, typos, stuck words, syllable boundaries (~250 LOC)
    boilerplate.py — Header/footer noise removal (~180 LOC)
    structure.py   — Paragraph rejoining, section splitting, legal formatting (~250 LOC)
    tables.py      — Table detection and normalization (~140 LOC)
"""

# Re-export all public names from sub-modules
from ingestion.normalizers.ocr_fixes import (  # noqa: F401
    normalize_ocr_spacing,
    fix_common_ocr_typos,
    fix_stuck_vietnamese_words,
    fix_generic_stuck_words,
    fix_vietnamese_syllable_boundaries,
)

from ingestion.normalizers.boilerplate import (  # noqa: F401
    strip_document_boilerplate,
    strip_noi_nhan_block,
    strip_signer_block,
    strip_digital_signature,
    strip_date_page_noise,
    strip_template_dots,
)

from ingestion.normalizers.structure import (  # noqa: F401
    rejoin_broken_headings,
    rejoin_paragraphs,
    rejoin_cross_page_paragraphs,
    normalize_section_headings,
    format_legal_structure,
)

from ingestion.normalizers.tables import (  # noqa: F401
    detect_garbled_table,
    is_table_chunk,
    fix_raw_pipe_tables,
)


# ---------------------------------------------------------------------------
# Composite: Full normalization pipeline
# ---------------------------------------------------------------------------

def normalize_chunk_text(text: str, strip_doc_id_prefix: str = "") -> str:
    """Apply the full normalization chain to a chunk's text.

    Args:
        text: Raw chunk text.
        strip_doc_id_prefix: If provided, strip this prefix pattern from the text
                             (e.g. "[UBND_DaNang-QNam/1287/QĐ-TTg] ").

    Returns:
        Cleaned, formatted markdown text.
    """
    if not text:
        return ""

    # Step 0: Strip doc_id prefix
    if strip_doc_id_prefix:
        prefix = f"[{strip_doc_id_prefix}] "
        if text.startswith(prefix):
            text = text[len(prefix):]

    # Step 0a: Normalize OCR spacing (must be FIRST, before any regex)
    text = normalize_ocr_spacing(text)

    # Step 0b: Fix OCR typos early (before any structure detection)
    text = fix_common_ocr_typos(text)

    # Step 0b2: Fix stuck Vietnamese words (hồsơ → hồ sơ)
    text = fix_stuck_vietnamese_words(text)

    # Step 0b3: Fix generic stuck words via regex (diacritic+uppercase boundary)
    text = fix_generic_stuck_words(text)

    # Step 0b3b: Fix Vietnamese syllable boundaries (lowercase→lowercase)
    text = fix_vietnamese_syllable_boundaries(text)

    # Step 0b4: Strip date/page metadata noise
    text = strip_date_page_noise(text)

    # Step 0b5: Strip template dotted-line patterns from form annexes
    text = strip_template_dots(text)

    # Step 0c: Strip government document boilerplate headers
    text = strip_document_boilerplate(text)

    # Step 0d: Strip Nơi nhận distribution blocks
    text = strip_noi_nhan_block(text)

    # Step 0e: Strip signer block at end of text (KT./TM. + name)
    text = strip_signer_block(text)

    # Step 0f: Strip digital signature metadata (Ký bởi:...Email:...)
    text = strip_digital_signature(text)

    # Step 1: Detect garbled table — return with warning if garbled
    if detect_garbled_table(text):
        return f"> ⚠️ *Bảng biểu gốc — dữ liệu OCR cần kiểm tra thủ công*\n\n{text}"

    # Step 2: Rejoin hard-wrapped paragraphs
    text = rejoin_paragraphs(text)

    # Step 2b: [P1-FIX] Fix raw pipe tables missing separator rows
    text = fix_raw_pipe_tables(text)

    # Step 3: Rejoin broken ALL-CAPS headings
    text = rejoin_broken_headings(text)

    # Step 3b: Split inline section numbers onto separate lines
    text = normalize_section_headings(text)

    # Step 4: Format legal structure markers as headings
    text = format_legal_structure(text)

    return text
