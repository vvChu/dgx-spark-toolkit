#!/usr/bin/env python3
"""Autoresearch Pipeline — Post-processing fixes for RAG exports.

This is the ONLY file edited during autoresearch experiments.
It post-processes existing JSON + Markdown exports in-place to fix
quality issues detected by comprehensive_audit.py.

Usage inside Docker:
    python3 pipeline.py --apply      # Apply all fixes to exports
    python3 pipeline.py --revert     # Revert to backup copies
    python3 pipeline.py --dry-run    # Show what would change without writing

Backup strategy: First --apply creates .bak files; --revert restores them.
"""

import os
import re
import sys
import json
import glob
import shutil
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
EXPORT_JSON_DIR = os.environ.get("EXPORT_JSON_DIR", "/app/exports/json")
EXPORT_MD_DIR = os.environ.get("EXPORT_MD_DIR", "/app/exports/markdown")

# ═════════════════════════════════════════════════════════════════════════════
# P2 — AI MONOLOGUE LEAKAGE STRIPPING
# ═════════════════════════════════════════════════════════════════════════════

# Vietnamese AI monologue phrases (high-precision patterns)
_AI_PATTERNS_VN = [
    # Introductory/conversational phrases
    r"(?i)(?:^|\n)\s*Dưới đây là[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Xin lỗi[^.]*[.!]?\s*\n",
    r"(?i)(?:^|\n)\s*Tôi xin[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Theo yêu cầu[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Nội dung chính[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Bảng dưới đây[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Tôi đã[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Tôi sẽ[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Tóm tắt[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Như bạn[^.]*[.:]?\s*\n",
    r"(?i)(?:^|\n)\s*Chào bạn[^.]*[.!]?\s*\n",
    r"(?i)(?:^|\n)\s*Dạ,[^.]*[.!]?\s*\n",
    r"(?i)(?:^|\n)\s*Vâng,[^.]*[.!]?\s*\n",
    # Instruction echo patterns
    r"(?i)(?:^|\n)\s*Trích xuất TOÀN BỘ[^\n]*\n",
    r"(?i)(?:^|\n)\s*TUYỆT ĐỐI KHÔNG[^\n]*\n",
    r"(?i)(?:^|\n)\s*KHÔNG mô tả font[^\n]*\n",
    r"(?i)(?:^|\n)\s*giữ nguyên thứ tự[^\n]*\n",
    r"(?i)(?:^|\n)\s*KHÔNG thêm bất kỳ[^\n]*\n",
    r"(?i)(?:^|\n)\s*Chỉ trả về nội dung[^\n]*\n",
    # Summary leakage
    r"(?i)(?:^|\n)\s*Nội dung đã chỉnh sửa:?\s*\n",
    r"(?i)(?:^|\n)\s*Tóm tắt văn bản:?\s*\n",
    r"(?i)(?:^|\n)\s*Here is the corrected text:?\s*\n",
]

# English AI monologue phrases
_AI_PATTERNS_EN = [
    r"(?i)(?:^|\n)\s*Certainly[,!]?\s+(?:here|I|let)[^\n]*\n",
    r"(?i)(?:^|\n)\s*I'll\s[^\n]*\n",
    r"(?i)(?:^|\n)\s*As an AI[^\n]*\n",
    r"(?i)(?:^|\n)\s*Here is[^\n]*:\s*\n",
    r"(?i)(?:^|\n)\s*Here's[^\n]*:\s*\n",
    r"(?i)(?:^|\n)\s*I cannot[^\n]*\n",
    r"(?i)(?:^|\n)\s*I would[^\n]*\n",
    r"(?i)(?:^|\n)\s*I will[^\n]*\n",
    r"(?i)(?:^|\n)\s*I need to[^\n]*\n",
    r"(?i)(?:^|\n)\s*Let me[^\n]*\n",
    # LLM reasoning traces
    r"(?i)(?:^|\n)\s*Thinking Process:?[^\n]*\n",
    r"(?i)(?:^|\n)\s*Analysis:?\s*\n",
    r"(?i)(?:^|\n)\s*\*\*Plan:\*\*[^\n]*\n",
    r"(?i)(?:^|\n)\s*\*\*Structure:[^\n]*\*\*[^\n]*\n",
    r"(?i)(?:^|\n)\s*\*\*OCR Text:\*\*[^\n]*\n",
]

_AI_COMPILED = [re.compile(p) for p in _AI_PATTERNS_VN + _AI_PATTERNS_EN]


def strip_ai_monologue(text: str) -> str:
    """[P2] Strip AI monologue phrases from text content."""
    if not text:
        return text
    original_len = len(text)
    for pat in _AI_COMPILED:
        text = pat.sub("\n", text)
    # Safety: never strip more than 30% of content
    if len(text) < original_len * 0.7:
        return text  # Already cleaned enough
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ═════════════════════════════════════════════════════════════════════════════
# P1 — TABLE GFM FIX (ENHANCED)
# ═════════════════════════════════════════════════════════════════════════════

def fix_table_gfm_v2(text: str) -> str:
    """[P1] Enhanced GFM table fixer for multi-line and nested tables.
    
    Improvements over v1:
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
            and re.match(r"^\s*\S.*\|.*\S\s*$", stripped)
            and len(stripped) > 10
        )

        if not is_pipe_row and not is_loose_pipe_row:
            in_table = False
            fixed.append(line)
            continue

        # For loose pipe rows, normalize them to proper pipe format
        if is_loose_pipe_row and not is_pipe_row:
            # Add leading and trailing pipes
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
        is_header = (
            cells
            and all(len(c) < 80 for c in cells)
            and any(re.search(r"[a-zA-Z\u00c0-\u1ef9]", c) for c in cells)
            and not all(re.match(r"^[\d.,\s%]+$", c) for c in cells if c)
        )
        if is_header:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            fixed.append(line)
            fixed.append(sep)
            in_table = True
        else:
            fixed.append(line)

    return "\n".join(fixed)


# ═════════════════════════════════════════════════════════════════════════════
# P5 — EXTENDED BOILERPLATE STRIPPING
# ═════════════════════════════════════════════════════════════════════════════

_BOILERPLATE_CONTENT_PATTERNS = [
    # Government header phrases that may leak into ## Content section
    re.compile(
        r"(?:^|\n)\s*CỘNG\s+HÒA\s+XÃ\s+HỘI\s+CHỦ\s+NGHĨA\s+VIỆT\s+NAM\s*(?:\n|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\n)\s*Độc\s+lập\s*[-–—]\s*Tự\s+do\s*[-–—]\s*Hạnh\s+phúc\s*(?:\n|$)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:^|\n)\s*Số\s*:\s*[\d/]+\s*[A-ZĐ]{2,}[-/][A-ZĐ]+\s*(?:\n|$)"),
    # Nơi nhận distribution list
    re.compile(r"(?:^|\n)\s*Nơi\s+nhận\s*:.*?(?=\n\s*(?:[A-ZĐ]|\d)|\Z)", re.DOTALL),
    # Digital signature metadata
    re.compile(
        r"(?:^|\n)\s*(?:Ký bởi|Người ký)\s*:.*?"
        r"(?:\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\s*[+\-]\d{2}:\d{2})",
        re.DOTALL,
    ),
    # Portal noise
    re.compile(r"(?:^|\n).*CỔNG\s+THÔNG\s+TIN\s+ĐIỆN\s+TỬ.*(?:\n|$)", re.IGNORECASE),
    re.compile(r"(?:^|\n).*chinhphu\.vn.*(?:\n|$)", re.IGNORECASE),
    # VGP header
    re.compile(r"(?:^|\n)\s*VGP\s*(?:\n|$)", re.IGNORECASE),
    # Lưu: VT archive lines
    re.compile(r"(?:^|\n)\s*-?\s*Lưu\s*:\s*VT[,;]?\s*[A-Z]*\.?\s*(?:\n|$)", re.IGNORECASE),
]


def strip_boilerplate_extended(text: str) -> str:
    """[P5] Strip extended boilerplate patterns from content."""
    if not text:
        return text
    for pat in _BOILERPLATE_CONTENT_PATTERNS:
        text = pat.sub("\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ═════════════════════════════════════════════════════════════════════════════
# P4 — DOC_NUMBER EXTRACTION FROM FILENAME/PATH
# ═════════════════════════════════════════════════════════════════════════════

# QCVN pattern: QCVN_01_2021_BXD → QCVN 01:2021/BXD
_QCVN_FILENAME_RE = re.compile(
    r"QCVN[_\s-]?(\d+)[_\s-](\d{4})[_\s-]([A-Z]+)"
)

# Standard doc pattern: TT01-2023-BTP → 01/2023/TT-BTP
_DOC_NUM_FILENAME_RE = re.compile(
    r"([A-Z]{2,4})(\d+)[-_/](\d{4})[-_/]([A-Z]+)"
)
# Simpler: QD08-TTg → 08/QĐ-TTg
_DOC_NUM_SIMPLE_RE = re.compile(
    r"([A-Z]{2,4})(\d+)[-_/]([A-Za-z]+)"
)


def extract_doc_number_from_path(filepath: str) -> str:
    """[P4] Extract doc_number from filename/path when missing from content.
    
    Handles QCVN patterns and standard Vietnamese legal document IDs.
    """
    basename = os.path.basename(filepath).replace(".json", "").replace(".md", "")

    # QCVN special handling
    m = _QCVN_FILENAME_RE.search(basename)
    if m:
        return f"QCVN {m.group(1)}:{m.group(2)}/{m.group(3)}"

    # Standard full pattern: TT01-2023-BTP → 01/2023/TT-BTP
    m = _DOC_NUM_FILENAME_RE.search(basename)
    if m:
        return f"{m.group(2)}/{m.group(3)}/{m.group(1)}-{m.group(4)}"

    # Simple pattern: QD08-TTg → 08/QĐ-TTg
    m = _DOC_NUM_SIMPLE_RE.search(basename)
    if m:
        return f"{m.group(2)}/{m.group(1)}-{m.group(3)}"

    return ""


# ═════════════════════════════════════════════════════════════════════════════
# MAIN PROCESSING LOGIC
# ═════════════════════════════════════════════════════════════════════════════

def process_markdown_file(filepath: str, dry_run: bool = False) -> dict:
    """Apply all fixes to a single markdown file."""
    text = Path(filepath).read_text(errors="replace")
    original = text

    # P2: Strip AI monologue
    text = strip_ai_monologue(text)

    # P1: Fix table GFM
    text = fix_table_gfm_v2(text)

    # Apply OCR spacing normalization + P5 boilerplate to the Content section only
    # (preserves Metadata and Summary sections untouched)
    content_match = re.search(r"(## Content\s*\n)(.*)", text, re.DOTALL)
    if content_match:
        pre = text[: content_match.start(2)]
        content = content_match.group(2)

        # OCR spacing normalization (from text_normalizer pipeline)
        try:
            from ingestion.text_normalizer import (
                fix_stuck_vietnamese_words,
                fix_generic_stuck_words,
                fix_vietnamese_syllable_boundaries,
                fix_common_ocr_typos,
                fix_raw_pipe_tables,
                strip_noi_nhan_block,
                normalize_ocr_spacing,
            )
            content = normalize_ocr_spacing(content)
            content = fix_common_ocr_typos(content)
            content = fix_stuck_vietnamese_words(content)
            content = fix_generic_stuck_words(content)
            content = fix_vietnamese_syllable_boundaries(content)
            content = strip_noi_nhan_block(content)
            content = fix_raw_pipe_tables(content)
        except ImportError:
            logger.warning("text_normalizer not available, skipping OCR normalization")

        # P5: Strip boilerplate from Content section
        content = strip_boilerplate_extended(content)
        text = pre + content

    changed = text != original

    if changed and not dry_run:
        Path(filepath).write_text(text, encoding="utf-8")

    return {"changed": changed, "path": filepath}


def process_json_file(filepath: str, dry_run: bool = False) -> dict:
    """Apply fixes to a single JSON export file."""
    try:
        data = json.loads(Path(filepath).read_text(errors="replace"))
    except Exception:
        return {"changed": False, "path": filepath, "error": "parse_failed"}

    changed = False

    # P4: Fix missing doc_number
    meta = data.get("metadata", {})
    current_dn = meta.get("doc_number", "").strip()
    if not current_dn:
        extracted = extract_doc_number_from_path(filepath)
        if extracted:
            meta["doc_number"] = extracted
            # Also update all chunks
            for c in data.get("chunks", []):
                c["doc_number"] = extracted
            changed = True

    # P2: Strip AI monologue from chunk text
    for c in data.get("chunks", []):
        old_text = c.get("text", "")
        new_text = strip_ai_monologue(old_text)
        if new_text != old_text:
            c["text"] = new_text
            changed = True

    # P5: Strip boilerplate from chunk text
    for c in data.get("chunks", []):
        old_text = c.get("text", "")
        new_text = strip_boilerplate_extended(old_text)
        if new_text != old_text:
            c["text"] = new_text
            changed = True

    if changed and not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {"changed": changed, "path": filepath}


def backup_exports():
    """Create .bak copies of all exports (idempotent — skips if backup exists)."""
    count = 0
    for d in [EXPORT_JSON_DIR, EXPORT_MD_DIR]:
        for f in glob.glob(os.path.join(d, "*")):
            if f.endswith(".bak"):
                continue
            bak = f + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(f, bak)
                count += 1
    logger.info(f"Backed up {count} files (skipped existing backups)")


def revert_exports():
    """Restore all exports from .bak files."""
    count = 0
    for d in [EXPORT_JSON_DIR, EXPORT_MD_DIR]:
        for bak in glob.glob(os.path.join(d, "*.bak")):
            original = bak.rsplit(".bak", 1)[0]
            shutil.copy2(bak, original)
            count += 1
    logger.info(f"Reverted {count} files from backups")


def apply_all_fixes(dry_run: bool = False):
    """Apply all P1-P5 fixes to all exports."""
    if not dry_run:
        backup_exports()

    md_files = sorted(glob.glob(os.path.join(EXPORT_MD_DIR, "*.md")))
    json_files = sorted(glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json")))

    md_changed = 0
    json_changed = 0

    for f in md_files:
        if f.endswith(".bak"):
            continue
        r = process_markdown_file(f, dry_run=dry_run)
        if r["changed"]:
            md_changed += 1

    for f in json_files:
        if f.endswith(".bak"):
            continue
        r = process_json_file(f, dry_run=dry_run)
        if r["changed"]:
            json_changed += 1

    action = "Would fix" if dry_run else "Fixed"
    logger.info(f"{action} {md_changed}/{len(md_files)} markdown files")
    logger.info(f"{action} {json_changed}/{len(json_files)} JSON files")

    return {"md_changed": md_changed, "json_changed": json_changed,
            "md_total": len(md_files), "json_total": len(json_files)}


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="RAG Export Post-Processor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="Apply fixes to exports")
    group.add_argument("--revert", action="store_true", help="Revert to backup copies")
    group.add_argument("--dry-run", action="store_true", help="Show what would change")

    args = parser.parse_args()

    if args.revert:
        revert_exports()
    elif args.apply:
        apply_all_fixes(dry_run=False)
    elif args.dry_run:
        apply_all_fixes(dry_run=True)


if __name__ == "__main__":
    main()
