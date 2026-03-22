#!/usr/bin/env python3
"""Autoresearch — Mutable RAG Pipeline.

████████████████████████████████████████████████████████████████████████
██  THIS IS THE FILE THE AI AGENT MODIFIES.                          ██
██  Everything is fair game: extraction, cleaning, chunking, export. ██
████████████████████████████████████████████████████████████████████████

Strategy: Re-process existing JSON exports to improve chunking quality.
This avoids slow PDF re-extraction while iterating on chunk/export logic.

Usage:
    ../venv/bin/python3 optimize_rag.py              # Re-process all exports
    ../venv/bin/python3 optimize_rag.py --dry-run     # Preview changes
"""

import os
import re
import sys
import json
import hashlib
import logging
from pathlib import Path
from collections import Counter

# Add rag-service to path for imports
RAG_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAG_SERVICE_DIR)

from ingestion.chunking import (
    VietLawArticleChunker, VietLawSectionChunker,
    GenericFallbackChunker, _split_into_children, _is_noise_chunk,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
EXPORT_DIR = "/home/vvc/Public/exports"
EXPORT_JSON_DIR = os.path.join(EXPORT_DIR, "json")
EXPORT_MD_DIR = os.path.join(EXPORT_DIR, "markdown")


# ═════════════════════════════════════════════════════════════════════════
# EXP-1: AI LEAKAGE STRIPPING
# ═════════════════════════════════════════════════════════════════════════

_AI_PATTERNS = [
    re.compile(r"\bcertainly\b", re.IGNORECASE),
    re.compile(r"\bI'll\b"),
    re.compile(r"\bAs an AI\b", re.IGNORECASE),
    re.compile(r"\bHere is\b", re.IGNORECASE),
    re.compile(r"\bI cannot\b", re.IGNORECASE),
    re.compile(r"\bI would\b", re.IGNORECASE),
    re.compile(r"\bI will\b", re.IGNORECASE),
    re.compile(r"\bHere's\b", re.IGNORECASE),
    re.compile(r"Xin lỗi", re.IGNORECASE),
    re.compile(r"Dưới đây là", re.IGNORECASE),
    re.compile(r"Tôi xin", re.IGNORECASE),
]

# Full-sentence patterns to remove (the AI monologue lines)
_AI_SENTENCE_RE = re.compile(
    r"(?:^|\n)[^\n]*(?:"
    r"(?:certainly|I'll|As an AI|Here is|I cannot|I would|I will|Here's)"
    r"|(?:Xin lỗi|Dưới đây là|Tôi xin)"
    r")[^\n]*(?:\n|$)",
    re.IGNORECASE,
)


def strip_ai_leakage(text: str) -> str:
    """Remove AI monologue sentences from text."""
    cleaned = _AI_SENTENCE_RE.sub("\n", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def has_ai_leakage(text: str) -> bool:
    """Check if text contains AI leakage patterns."""
    lower = text.lower()
    for p in ["certainly,", "i'll", "i will", "as an ai", "here is",
              "here's", "i cannot", "i would", "xin lỗi", "dưới đây là"]:
        if p in lower:
            return True
    return False


# ═════════════════════════════════════════════════════════════════════════
# EXP-1: OCR SPACING FIX
# ═════════════════════════════════════════════════════════════════════════

# Pattern: single capital letters separated by spaces (OCR artifact)
_OCR_SPACING_RE = re.compile(r"([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ])\s([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ])\s([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ])")


def fix_ocr_spacing(text: str) -> str:
    """Fix OCR double-spacing artifacts in Vietnamese text.
    
    Detects runs of single uppercase letters separated by spaces
    and joins them together. E.g. 'C Ộ N G  H Ò A' -> 'CỘNG HÒA'
    """
    # Only process if the pattern exists
    if not _OCR_SPACING_RE.search(text):
        return text
    
    lines = text.split("\n")
    result = []
    for line in lines:
        # Check if line has OCR spacing (3+ single chars separated by spaces)
        if _OCR_SPACING_RE.search(line):
            # Join runs of single-char-space patterns
            fixed = re.sub(
                r"(?<![a-zA-ZĐàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ])"
                r"([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ])"
                r"(?:\s+(?=[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]))",
                r"\1",
                line,
            )
            result.append(fixed)
        else:
            result.append(line)
    return "\n".join(result)


# ═════════════════════════════════════════════════════════════════════════
# STAGE 1: RE-CHUNK existing JSON exports
# ═════════════════════════════════════════════════════════════════════════

def rechunk_document(old_chunks: list[dict], doc_id: str) -> list[dict]:
    """Re-chunk an existing document by merging parent text and re-splitting.
    
    [EXP-1] Merges all parent chunk text into one document, then re-chunks
    using VietLawArticleChunker (cross-page detection). Forces child
    generation for parents without children to improve child/parent ratio.
    """
    # Extract all parent text in page order
    parents = sorted(
        [c for c in old_chunks if c.get("chunk_type") in ("parent", "preamble")],
        key=lambda x: (x.get("page", 0), 0),
    )
    
    if not parents:
        return old_chunks
    
    # Merge all parent texts (strip [doc_id] prefix for clean re-chunking)
    texts = []
    for p in parents:
        text = p.get("text", "")
        # Strip [doc_id] prefix if present
        text = re.sub(r"^\[.*?\]\s*", "", text)
        # Strip [Context] ::: prefix if present
        text = re.sub(r"^\[.*?\]\s*:::\s*", "", text)
        if text.strip():
            texts.append(text.strip())
    
    full_text = "\n\n".join(texts)
    if len(full_text) < 50:
        return old_chunks
    
    # [EXP-1] Strip AI leakage from merged text before chunking
    full_text = strip_ai_leakage(full_text)
    
    # Get source info from first parent
    source = parents[0].get("source", "")
    
    # Try chunking strategies in order on merged text
    new_chunks = []
    
    # Strategy 1: VietLawArticleChunker (detects Điều patterns)
    law_chunker = VietLawArticleChunker()
    new_chunks = law_chunker.chunk(full_text, source, 1, doc_id)
    
    if not new_chunks:
        # Strategy 2: VietLawSectionChunker
        sec_chunker = VietLawSectionChunker()
        new_chunks = sec_chunker.chunk(full_text, source, 1, doc_id)
    
    if not new_chunks:
        # Strategy 3: Generic fallback
        fb_chunker = GenericFallbackChunker()
        new_chunks = fb_chunker.chunk(full_text, source, 1, doc_id)
    
    if not new_chunks:
        return old_chunks
    
    # Filter noise
    new_chunks = [c for c in new_chunks if not _is_noise_chunk(c.get("text", ""))]
    if not new_chunks:
        return old_chunks
    
    # [EXP-3] Rewrite hierarchy_path for parent chunks containing Điều
    _dieu_re = re.compile(r'([ĐĐD]i[eề]u\s+\d+\.?(?:\s+[^\n]{0,50})?)')
    for c in new_chunks:
        if c.get("chunk_type") != "parent":
            continue
        hp = c.get("hierarchy_path", "")
        if "Điều" in hp or "Article" in hp:
            continue
        text = c.get("text", "")
        # Strip [doc_id] prefix before searching
        stripped = re.sub(r'^\[.*?\]\s*(?:\[.*?\]\s*:::\s*)?', '', text)
        m = _dieu_re.search(stripped[:200])  # Only check first 200 chars
        if m:
            article_label = m.group(1).strip()[:60]
            c["hierarchy_path"] = f"[{doc_id}] -> [{article_label}]"
    
    # Force child generation for parent chunks without children
    parent_ids_with_children = set()
    for c in new_chunks:
        if c.get("chunk_type") == "child":
            parent_ids_with_children.add(c.get("parent_id"))
    
    extra_children = []
    for c in new_chunks:
        if (c.get("chunk_type") == "parent"
            and c.get("parent_id") not in parent_ids_with_children
            and len(c.get("text", "")) > 300):
            children = _split_into_children(
                c["text"], doc_id, source, c.get("page", 1),
                c["parent_id"], c.get("hierarchy_path", ""),
                c.get("bbox", [0, 0, 1000, 1000]),
                min_child_length=200,
            )
            extra_children.extend(children)
    
    new_chunks.extend(extra_children)
    
    return new_chunks


# ═════════════════════════════════════════════════════════════════════════
# STAGE 2: RE-EXPORT with enriched fields
# ═════════════════════════════════════════════════════════════════════════

def enrich_and_export(json_path: str, dry_run: bool = False) -> dict:
    """Re-process a single JSON export: re-chunk + re-export."""
    try:
        data = json.loads(Path(json_path).read_text(errors="replace"))
    except Exception as e:
        return {"status": "error", "error": str(e)}
    
    doc_id = data.get("doc_id", "")
    meta = data.get("metadata", {})
    summary = data.get("summary", "")
    old_chunks = data.get("chunks", [])
    
    if not old_chunks:
        return {"status": "skip", "reason": "no chunks"}
    
    # Count old stats
    old_parents = sum(1 for c in old_chunks if c.get("chunk_type") == "parent")
    old_children = sum(1 for c in old_chunks if c.get("chunk_type") == "child")
    old_articles = sum(1 for c in old_chunks if "Điều" in c.get("hierarchy_path", ""))
    
    # Re-chunk
    new_chunks = rechunk_document(old_chunks, doc_id)
    
    # [EXP-1] Post-process: strip AI leakage from all chunk texts
    for chunk in new_chunks:
        text = chunk.get("text", "")
        if has_ai_leakage(text):
            chunk["text"] = strip_ai_leakage(text)
    
    # Enrich chunks with doc-level fields
    for i, chunk in enumerate(new_chunks):
        chunk["doc_id"] = doc_id
        chunk["doc_number"] = meta.get("doc_number", "")
        chunk["chunk_id"] = f"{doc_id}:chunk_{i}"
        # Preserve synthetic_queries from old chunks if available
        if i < len(old_chunks) and old_chunks[i].get("synthetic_queries"):
            chunk["synthetic_queries"] = old_chunks[i]["synthetic_queries"]
    
    # Count new stats
    new_parents = sum(1 for c in new_chunks if c.get("chunk_type") == "parent")
    new_children = sum(1 for c in new_chunks if c.get("chunk_type") == "child")
    new_articles = sum(1 for c in new_chunks if "Điều" in c.get("hierarchy_path", ""))
    
    result = {
        "status": "ok",
        "doc_id": doc_id,
        "old": {"total": len(old_chunks), "parents": old_parents, "children": old_children, "articles": old_articles},
        "new": {"total": len(new_chunks), "parents": new_parents, "children": new_children, "articles": new_articles},
    }
    
    if dry_run:
        return result
    
    # Write updated JSON
    data["chunks"] = new_chunks
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Re-generate markdown
    safe_filename = doc_id.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
    md_path = os.path.join(EXPORT_MD_DIR, f"{safe_filename}.md")
    rel_path = data.get("original_path", "")
    md_content = generate_markdown(doc_id, rel_path, meta, summary, new_chunks)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    return result


# ═════════════════════════════════════════════════════════════════════════
# MARKDOWN GENERATION
# ═════════════════════════════════════════════════════════════════════════

# Vietnamese boilerplate patterns — expanded for better coverage
_BOILERPLATE_PATTERNS = [
    re.compile(r"CỘNG\s+HÒA\s+XÃ\s+HỘI\s+CHỦ\s+NGHĨA\s+VIỆT\s+NAM", re.IGNORECASE),
    re.compile(r"Độc\s+lập\s*[-–—]\s*Tự\s+do\s*[-–—]\s*Hạnh\s+phúc", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*Nơi\s+nhận\s*:.*?(?=\n\s*(?:[A-ZĐ]|\d)|\Z)", re.DOTALL),
    re.compile(r"(?:^|\n)\s*-?\s*Lưu\s*:\s*VT[,;]?\s*[A-Z]*\.?\s*(?:\n|$)", re.IGNORECASE),
    # [EXP-1] Additional boilerplate patterns
    re.compile(r"Số\s*:\s*\d+/\w+[-/]\w+", re.IGNORECASE),  # Document number prefix
    re.compile(r"(?:Hà Nội|TP\.?\s*HCM|Đà Nẵng),?\s*ngày\s+\d+\s+tháng\s+\d+\s+năm\s+\d+", re.IGNORECASE),  # Date line
    re.compile(r"Kính\s+gửi\s*:.*?(?:\n|$)", re.IGNORECASE),  # Salutation
]

# [EXP-1] OCR boilerplate - badly OCR'd government header
_OCR_BOILERPLATE_PATTERNS = [
    re.compile(r"CONG\s*(?:HOA|NGH)", re.IGNORECASE),
    re.compile(r"D[oọ]c\s+l[aậ]p", re.IGNORECASE),
    re.compile(r"CONGHOA\s+xA\s+HOI", re.IGNORECASE),
]


def strip_boilerplate(text: str) -> str:
    """Strip government boilerplate from content text."""
    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub("\n", text)
    for pat in _OCR_BOILERPLATE_PATTERNS:
        text = pat.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# [EXP-3] Fix broken markdown tables (pipe rows without separator)
_PIPE_ROW_RE = re.compile(r'^(\s*\|[^|]+(?:\|[^|]+)+\|)\s*$', re.MULTILINE)
_SEP_ROW_RE = re.compile(r'^\s*\|[-:\s|]+\|\s*$', re.MULTILINE)


def fix_broken_tables(text: str) -> str:
    """Insert separator rows after header rows in broken markdown tables.
    
    Detects table-like pipe rows that lack separator rows and inserts
    a proper | --- | --- | separator after the first pipe row.
    """
    if not _PIPE_ROW_RE.search(text):
        return text
    if _SEP_ROW_RE.search(text):
        return text  # Already has separator, not broken
    
    lines = text.split('\n')
    result = []
    inserted = False
    for line in lines:
        result.append(line)
        if not inserted and _PIPE_ROW_RE.match(line):
            # Count columns
            cols = line.count('|') - 1
            if cols >= 2:
                sep = '| ' + ' | '.join(['---'] * cols) + ' |'
                result.append(sep)
                inserted = True
    return '\n'.join(result)


def generate_markdown(doc_id: str, rel_path: str, meta: dict,
                      summary: str, chunks: list[dict]) -> str:
    """Generate formatted markdown from document data."""
    lines = [f"# Document: {doc_id}\n"]
    
    # Metadata
    lines.append("## Metadata")
    meta_display = [
        ("date", "Date"), ("type", "Type"), ("authority", "Authority"),
        ("doc_number", "Doc Number"), ("validity_status", "Validity Status"),
        ("legal_level", "Legal Level"), ("source_category", "Source Category"),
    ]
    for key, label in meta_display:
        val = meta.get(key, "")
        if val and val not in ("unknown", "UNKNOWN", ""):
            lines.append(f"- **{label}:** {val}")
    lines.append(f"- **Original Path:** {rel_path}\n")
    
    # Summary
    lines.append("## Summary")
    lines.append(f"{summary}\n")
    
    # Content from parent chunks
    lines.append("## Content")
    parent_chunks = sorted(
        [c for c in chunks if c.get("chunk_type") in ("parent", "preamble")],
        key=lambda x: (x.get("page", 0), 0),
    )
    if not parent_chunks:
        parent_chunks = chunks
    
    # Dedup
    seen = set()
    prev_heading = None
    for chunk in parent_chunks:
        text = chunk.get("text", "")
        fp = hash(text.strip())
        if fp in seen:
            continue
        seen.add(fp)
        
        # Strip [doc_id] prefix from display
        display_text = re.sub(r"^\[.*?\]\s*", "", text)
        # Strip context prefix
        display_text = re.sub(r"^\[.*?\]\s*:::\s*", "", display_text)
        # Strip boilerplate from content
        display_text = strip_boilerplate(display_text)
        # [EXP-1] Fix OCR spacing in markdown
        display_text = fix_ocr_spacing(display_text)
        # [EXP-1] Strip AI leakage from markdown
        display_text = strip_ai_leakage(display_text)
        # [EXP-3] Fix broken markdown tables
        display_text = fix_broken_tables(display_text)
        
        if not display_text.strip():
            continue
        
        # Extract heading from hierarchy_path
        h_path = chunk.get("hierarchy_path", "")
        heading = _extract_heading(h_path, doc_id)
        if heading and heading != prev_heading:
            lines.append(f"\n### {heading}")
            prev_heading = heading
        
        lines.append(display_text)
        lines.append("")
    
    return "\n".join(lines)


def _extract_heading(hierarchy_path: str, doc_id: str) -> str | None:
    """Extract a heading from hierarchy_path."""
    if not hierarchy_path:
        return None
    parts = re.split(r"\s*(?:->|>)\s*", hierarchy_path)
    if not parts:
        return None
    last = parts[-1].strip().strip("[]")
    if not last or last == doc_id or last.lower() == "header":
        return None
    legal_match = re.match(
        r"((?:[ĐÐ]iều\s+\d+\.?\s*[^\n]{0,60})"
        r"|(?:(?:Chương|CHƯƠNG)\s+[IVX\d]+[^.]*)"
        r"|(?:(?:Mục|MỤC)\s+[IVX\d]+[^.]*))",
        last
    )
    if legal_match:
        heading = legal_match.group(1).strip()
        return heading[:80] if len(heading) > 80 else heading
    return None


# ═════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════

def main():
    import glob
    
    dry_run = "--dry-run" in sys.argv
    
    json_files = sorted(glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json")))
    json_files = [f for f in json_files if not f.endswith(".bak")]
    
    if not json_files:
        print("No JSON exports found!")
        sys.exit(1)
    
    print(f"\n  {'[DRY RUN] ' if dry_run else ''}Processing {len(json_files)} exports...\n")
    
    stats = {"ok": 0, "skip": 0, "error": 0}
    total_old_parents = 0
    total_new_parents = 0
    total_old_children = 0
    total_new_children = 0
    total_old_articles = 0
    total_new_articles = 0
    ai_fixed = 0
    
    for i, json_path in enumerate(json_files, 1):
        result = enrich_and_export(json_path, dry_run=dry_run)
        stats[result.get("status", "error")] += 1
        
        if result["status"] == "ok":
            total_old_parents += result["old"]["parents"]
            total_new_parents += result["new"]["parents"]
            total_old_children += result["old"]["children"]
            total_new_children += result["new"]["children"]
            total_old_articles += result["old"]["articles"]
            total_new_articles += result["new"]["articles"]
        
        if i % 20 == 0:
            print(f"  Progress: {i}/{len(json_files)}")
    
    # Summary
    print(f"\n  {'=' * 50}")
    print(f"  {'[DRY RUN] ' if dry_run else ''}Done: {stats['ok']} ok, {stats['skip']} skip, {stats['error']} error")
    print(f"  Parents:  {total_old_parents:,} → {total_new_parents:,}")
    print(f"  Children: {total_old_children:,} → {total_new_children:,}")
    print(f"  Articles: {total_old_articles:,} → {total_new_articles:,}")
    if total_new_parents > 0:
        ratio = total_new_children / total_new_parents
        print(f"  Child/Parent ratio: {ratio:.2f}")
        art_rate = total_new_articles / total_new_parents * 100
        print(f"  Article rate: {art_rate:.1f}%")
    print(f"  {'=' * 50}\n")


if __name__ == "__main__":
    main()
