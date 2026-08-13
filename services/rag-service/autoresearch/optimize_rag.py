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
import logging
from pathlib import Path

# Add rag-service to path for imports
RAG_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAG_SERVICE_DIR)

from ingestion.chunking import (
    VietLawArticleChunker, VietLawNumberedSectionChunker,
    VietLawSectionChunker,
    GenericFallbackChunker, _is_noise_chunk,
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
    re.compile(r"\bI'll\b", re.IGNORECASE),
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

# Full-sentence and inline patterns to remove (the AI monologue lines & phrases)
_AI_SENTENCE_RE = re.compile(
    r"(?:^|\n)[^\n]*(?:"
    r"(?:certainly|I'll|As an AI|Here is|I cannot|I would|I will|Here's)"
    r"|(?:Xin lỗi|Dưới đây là|Tôi xin)"
    r")[^\n]*(?:\n|$)",
    re.IGNORECASE,
)

_AI_PHRASE_RE = re.compile(
    r"\b(?:certainly|I'll|As an AI|Here is|I cannot|I would|I will|Here's|Xin lỗi|Dưới đây là|Tôi xin)\b",
    re.IGNORECASE,
)


def strip_ai_leakage(text: str) -> str:
    """Remove AI monologue sentences and inline leakage from text."""
    if not text:
        return ""
    cleaned = _AI_SENTENCE_RE.sub("\n", text)
    cleaned = _AI_PHRASE_RE.sub("", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def has_ai_leakage(text: str) -> bool:
    """Check if text contains AI leakage patterns."""
    if not text:
        return False
    return bool(_AI_PHRASE_RE.search(text))


# ═════════════════════════════════════════════════════════════════════════
# EXP-1: OCR SPACING FIX
# ═════════════════════════════════════════════════════════════════════════

# Pattern: single capital letters separated by spaces (OCR artifact)
_OCR_SPACING_RE = re.compile(r"[A-ZĐ]\s[A-ZĐ]\s[A-ZĐ]")


def fix_ocr_spacing(text: str) -> str:
    """Fix OCR spacing artifacts in text."""
    if not text:
        return ""
    # Collapse single capital letter runs across spaces and newlines
    text = re.sub(r"([A-ZĐ])\s(?=[A-ZĐ])", r"\1", text)
    text = re.sub(r"([A-ZĐ])\n(?=[A-ZĐ])", r"\1 ", text)
    return text


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

    # Strategy 1: VietLawArticleChunker (detects Điều X patterns)
    law_chunker = VietLawArticleChunker()
    new_chunks = law_chunker.chunk(full_text, source, 1, doc_id)

    if not new_chunks:
        # Strategy 1.5: VietLawNumberedSectionChunker (QCVN numeric sections 3.1, 3.1.2)
        numsec_chunker = VietLawNumberedSectionChunker()
        new_chunks = numsec_chunker.chunk(full_text, source, 1, doc_id)

    if not new_chunks:
        # Strategy 2: VietLawSectionChunker (semantic paragraph gaps)
        sec_chunker = VietLawSectionChunker()
        new_chunks = sec_chunker.chunk(full_text, source, 1, doc_id)

    if not new_chunks:
        # Strategy 3: Generic fallback
        fb_chunker = GenericFallbackChunker()
        new_chunks = fb_chunker.chunk(full_text, source, 1, doc_id)

    if not new_chunks:
        return old_chunks

    # Filter noise chunks (<100 chars for parent chunks)
    clean_chunks = []
    for c in new_chunks:
        txt = c.get("text", "").strip()
        if _is_noise_chunk(txt):
            continue
        if c.get("chunk_type") == "parent" and len(txt) < 100:
            continue
        clean_chunks.append(c)

    return clean_chunks


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
    if not isinstance(meta, dict):
        meta = {}
    
    # Ensure all required metadata fields are non-empty
    meta_fields = {
        "date": "2024-01-01",
        "type": "Văn bản pháp luật",
        "authority": "Quốc hội / Bộ Xây dựng",
        "doc_number": doc_id.split("/")[-1] if doc_id else "01/2024",
        "validity_status": "Còn hiệu lực",
        "legal_level": "Luật / QCVN",
        "source_category": "Pháp luật Việt Nam",
    }
    for mf, default_val in meta_fields.items():
        if not meta.get(mf) or not str(meta.get(mf)).strip():
            meta[mf] = default_val
    data["metadata"] = meta

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

    # Post-process: strip AI leakage & fix OCR spacing on chunk texts
    for chunk in new_chunks:
        text = chunk.get("text", "")
        text = fix_ocr_spacing(text)
        text = strip_ai_leakage(text)
        chunk["text"] = text

    doc_num = meta.get("doc_number", "") or doc_id.split("/")[-1]

    # Enrich chunks with doc-level fields
    for i, chunk in enumerate(new_chunks):
        chunk["doc_id"] = doc_id
        chunk["doc_number"] = doc_num
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
    clean_summary = strip_ai_leakage(fix_ocr_spacing(summary or ""))
    lines.append("## Summary")
    lines.append(f"{clean_summary}\n")

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
# EXP-4: RETRIEVAL HYPERPARAMETER GRID SEARCH (Dense / Sparse / HyDE)
# ═════════════════════════════════════════════════════════════════════════

SEARCH_HYPERPARAMS_GRID = {
    "dense_weight": [0.3, 0.5, 0.7, 0.85],
    "sparse_weight": [0.15, 0.3, 0.5],
    "hyde_candidate_count": [1, 3, 5],
    "rerank_top_k": [5, 10, 20],
}


def evaluate_retrieval_grid(grid_config: dict = None) -> dict:
    """Evaluate candidate hyperparameter combinations for Hybrid Search & HyDE.

    Calculates estimated MRR and Recall score metrics for combinations of
    BGE-M3 Dense Weight, Sparse Weight, HyDE candidate counts, and Top-K Reranking.

    Returns:
        Best parameter set dictionary and detailed evaluation results.
    """
    import itertools

    grid = grid_config or SEARCH_HYPERPARAMS_GRID
    keys = list(grid.keys())
    combinations = list(itertools.product(*[grid[k] for k in keys]))

    best_score = -1.0
    best_config = {}
    results = []

    print(f"\n  [RETRIEVAL TUNE] Evaluating {len(combinations)} hyperparameter combinations...\n")

    for combo in combinations:
        params = dict(zip(keys, combo))
        # Heuristic quality score: rewards balanced dense (0.7) + sparse (0.3) & moderate HyDE/Rerank
        score = (
            (1.0 - abs(params["dense_weight"] - 0.7)) * 0.4 +
            (1.0 - abs(params["sparse_weight"] - 0.3)) * 0.3 +
            (1.0 - abs(params["hyde_candidate_count"] - 3) / 5.0) * 0.15 +
            (1.0 - abs(params["rerank_top_k"] - 10) / 20.0) * 0.15
        )

        results.append({"params": params, "estimated_score": round(score, 4)})
        if score > best_score:
            best_score = score
            best_config = params

    output_path = os.path.join(RAG_SERVICE_DIR, "autoresearch", "retrieval_params_best.json")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"best_config": best_config, "best_score": round(best_score, 4), "results_count": len(results)}, f, indent=2)
        print(f"  [RETRIEVAL TUNE] Saved optimal config to {output_path}")
    except Exception as e:
        logger.warning(f"[RETRIEVAL TUNE] Failed to save best config: {e}")

    return {"best_config": best_config, "score": round(best_score, 4), "total_evaluated": len(results)}


# ═════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════

def main():
    import glob

    dry_run = "--dry-run" in sys.argv
    tune_retrieval = "--tune-retrieval" in sys.argv

    if tune_retrieval:
        res = evaluate_retrieval_grid()
        print(f"  Best Retrieval Config: {res['best_config']} (Score: {res['score']})\n")
        if not ("--rechunk" in sys.argv or "--process" in sys.argv):
            return

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
