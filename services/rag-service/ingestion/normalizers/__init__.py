"""Vietnamese legal document text normalizers.

Sub-modules:
  ocr_fixes   — OCR spacing, typos, stuck words, syllable boundaries
  boilerplate — Header/footer noise removal
  structure   — Paragraph rejoining, section splitting, legal formatting
  tables      — Table detection and normalization
"""

# Re-export all public functions for backward compatibility
from ingestion.normalizers.ocr_fixes import (
    normalize_ocr_spacing,
    fix_common_ocr_typos,
    fix_stuck_vietnamese_words,
    fix_generic_stuck_words,
    fix_vietnamese_syllable_boundaries,
)

from ingestion.normalizers.boilerplate import (
    strip_document_boilerplate,
    strip_noi_nhan_block,
    strip_signer_block,
    strip_digital_signature,
    strip_date_page_noise,
    strip_template_dots,
)

from ingestion.normalizers.structure import (
    rejoin_broken_headings,
    rejoin_paragraphs,
    normalize_section_headings,
    format_legal_structure,
)

from ingestion.normalizers.tables import (
    detect_garbled_table,
    is_table_chunk,
    fix_raw_pipe_tables,
)

__all__ = [
    # OCR fixes
    'normalize_ocr_spacing',
    'fix_common_ocr_typos',
    'fix_stuck_vietnamese_words',
    'fix_generic_stuck_words',
    'fix_vietnamese_syllable_boundaries',
    # Boilerplate
    'strip_document_boilerplate',
    'strip_noi_nhan_block',
    'strip_signer_block',
    'strip_digital_signature',
    'strip_date_page_noise',
    'strip_template_dots',
    # Structure
    'rejoin_broken_headings',
    'rejoin_paragraphs',
    'normalize_section_headings',
    'format_legal_structure',
    # Tables
    'detect_garbled_table',
    'is_table_chunk',
    'fix_raw_pipe_tables',
]
