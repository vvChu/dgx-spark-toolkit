#!/usr/bin/env python3
"""Comprehensive RAG Quality Audit — 5 Dimensions × Sub-metrics.

Run inside Docker:
    docker compose exec rag-service python3 comprehensive_audit.py

Or locally (needs pymilvus + env vars):
    MILVUS_HOST=localhost MILVUS_PORT=19530 python3 comprehensive_audit.py
"""

import os
import re
import sys
import json
import glob
import statistics
import hashlib
import io
import threading
import contextlib
from collections import Counter
from pathlib import Path
from typing import Optional

# Ensure rag-service root (/app or services/rag-service) is in sys.path
_RAG_ROOT = str(Path(__file__).resolve().parent.parent)
if _RAG_ROOT not in sys.path:
    sys.path.insert(0, _RAG_ROOT)
if os.path.exists("/app") and "/app" not in sys.path:
    sys.path.insert(0, "/app")

# ── Config ──────────────────────────────────────────────────────────────────
EXPORT_JSON_DIR = os.environ.get("EXPORT_JSON_DIR", "/app/exports/json")
EXPORT_MD_DIR = os.environ.get("EXPORT_MD_DIR", "/app/exports/markdown")
PDF_SOURCE_DIR = os.environ.get("PDF_SOURCE_DIR", "/app/data/legal_docs_source")
MILVUS_SAMPLE_LIMIT = int(os.environ.get("MILVUS_SAMPLE_LIMIT", "2000"))

_audit_lock = threading.Lock()
SEPARATOR = "=" * 70

_VN_DIACRITICS = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]",
    re.IGNORECASE,
)


def is_valid_synthetic_queries(text: str) -> bool:
    """Validate that synthetic queries are genuine Vietnamese questions."""
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < 20:
        return False
    if "is no longer available" in text or "Please switch to Gemini" in text:
        return False
    if "Thinking Process" in text or "Analyze the Request" in text or "Tư duy suy luận" in text:
        return False
    if not _VN_DIACRITICS.search(text):
        return False
    return True


# ── Utility ─────────────────────────────────────────────────────────────────
def pct(n, total):
    return f"{n / max(total, 1) * 100:.1f}%"


def score_linear(bad_ratio, penalty_weight=100):
    """0 issues = 100, 100% issues = 0."""
    return max(0, int(100 - bad_ratio * penalty_weight))


def print_section(title):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


def _has_broken_table(text: str) -> bool:
    """Block-aware broken-table detector.

    Scans line-by-line for contiguous blocks of pipe-delimited rows (≥2 rows).
    A block is flagged as 'broken' only when the FIRST row of the block is NOT
    immediately followed by a Markdown separator row (|---|---|).

    This eliminates false positives from valid multi-row tables where data rows
    are not separators but are perfectly correct.
    """
    _SEP_RE = re.compile(r'^\|[\s\-:|]+\|')
    _PIPE_ROW_RE = re.compile(r'^\s*\|')

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if _PIPE_ROW_RE.match(lines[i]):
            block_start = i
            # Collect the full block of consecutive pipe rows
            while i < len(lines) and _PIPE_ROW_RE.match(lines[i]):
                i += 1
            block_lines = lines[block_start:i]
            if len(block_lines) >= 2:
                # Flag only if second row of the block is NOT a separator
                if not _SEP_RE.match(block_lines[1]):
                    return True
        else:
            i += 1
    return False


# ═════════════════════════════════════════════════════════════════════════════
# DIM A — MARKDOWN QUALITY
# ═════════════════════════════════════════════════════════════════════════════
def audit_markdown(md_files):
    print_section("DIMENSION A: MARKDOWN QUALITY")
    total = len(md_files)
    if total == 0:
        print("  ⚠  No markdown files found")
        return 0

    issues = {
        "no_h1": 0,
        "no_headings": 0,
        "broken_table": 0,
        "ai_leakage": 0,
        "ocr_spacing": 0,
        "boilerplate": 0,
        "encoding_issues": 0,
        "very_short": 0,
    }
    # Require patterns at start of a sentence/line to avoid false positives
    # from Vietnamese legal tables that coincidentally contain English phrases
    ai_patterns = [
        r"(?im)^\s*Certainly[,!.]",
        r"(?im)^\s*As an AI\b",
        r"(?im)^\s*Here is (the|a|an|your|this)\b",
        r"(?im)^\s*Here's (the|a|an|your|this)\b",
        r"(?im)^\s*I cannot\b",
        r"(?im)^\s*I would\b(?! (say|recommend)? rate)",
        r"(?im)^\s*I'll\b",
        r"(?im)^\s*I will\b",
        r"(?i)Xin lỗi, tôi",
        r"(?i)Dưới đây là.*theo yêu cầu",
        r"(?i)Tôi xin lỗi",
    ]
    boilerplate_re = re.compile(
        r"CỘNG\s+HÒA\s+XÃ\s+HỘI|"
        r"Độc lập\s*[-–—]\s*Tự do\s*[-–—]\s*Hạnh phúc|"
        r"Số:\s*\d+/\w+",
        re.IGNORECASE,
    )
    ocr_space_re = re.compile(r"[A-ZĐ]\s[A-ZĐ]\s[A-ZĐ]")  # e.g. B Ộ X Â Y

    for f in md_files:
        try:
            text = Path(f).read_text(errors="replace")
        except Exception:
            issues["encoding_issues"] += 1
            continue

        if len(text) < 200:
            issues["very_short"] += 1

        # Heading structure
        if not re.search(r"^# ", text, re.MULTILINE):
            issues["no_h1"] += 1
        if not re.search(r"^#{1,4} ", text, re.MULTILINE):
            issues["no_headings"] += 1

        # Broken tables: detect pipe-row blocks where the first row has no separator
        # Block-aware: only flag if row[0] of a ≥2-consecutive-pipe-row block
        # has no |---|---| separator on the VERY NEXT pipe row
        if _has_broken_table(text):
            issues["broken_table"] += 1

        # AI monologue leakage — checked against non-table prose sections only
        # Strip table lines before checking to avoid false positives
        prose = "\n".join(
            l for l in text.splitlines() if not l.strip().startswith("|")
        )
        for pat in ai_patterns:
            if re.search(pat, prose):
                issues["ai_leakage"] += 1
                break

        # OCR spacing
        if ocr_space_re.search(text):
            issues["ocr_spacing"] += 1

        # Boilerplate in ## Content section
        content_match = re.search(r"## Content\s*\n(.*)", text, re.DOTALL)
        if content_match and boilerplate_re.search(content_match.group(1)[:500]):
            issues["boilerplate"] += 1

        # Encoding issues (replacement chars)
        if "\ufffd" in text or "\\x" in text[:200]:
            issues["encoding_issues"] += 1

    # Print results
    for k, v in issues.items():
        flag = "🔴" if v > total * 0.1 else ("🟡" if v > 0 else "✅")
        print(f"  {flag} {k:25s}: {v:>4}/{total}  ({pct(v, total)})")

    bad_ratio = sum(issues.values()) / (total * len(issues))
    score = score_linear(bad_ratio, penalty_weight=400)
    print(f"\n  📊 MARKDOWN SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# DIM B — JSON / EXPORT QUALITY
# ═════════════════════════════════════════════════════════════════════════════
def audit_json(json_files):
    print_section("DIMENSION B: JSON EXPORT QUALITY")
    total = len(json_files)
    if total == 0:
        print("  ⚠  No JSON files found")
        return 0

    required_fields = ["doc_id", "original_path", "metadata", "summary", "chunks"]
    meta_fields = ["date", "type", "authority", "doc_number", "validity_status",
                   "legal_level", "source_category"]
    chunk_fields = ["text", "source", "page", "chunk_type", "is_table",
                    "hierarchy_path", "doc_id", "doc_number", "chunk_id"]

    issues = {
        "missing_root_field": 0,
        "missing_meta_field": 0,
        "no_summary": 0,
        "empty_chunks": 0,
        "missing_chunk_field": 0,
        "invalid_doc_id": 0,
        "chunk_no_text": 0,
    }
    total_chunks = 0
    chunk_types = Counter()
    strategies = Counter()

    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            issues["missing_root_field"] += 1
            continue

        # Root fields
        for rf in required_fields:
            if rf not in data or not data[rf]:
                issues["missing_root_field"] += 1
                break

        # Metadata
        meta = data.get("metadata", {})
        for mf in meta_fields:
            if not meta.get(mf, "").strip() if isinstance(meta.get(mf), str) else not meta.get(mf):
                issues["missing_meta_field"] += 1
                break

        # Summary
        summary = data.get("summary", "")
        if not summary or len(summary) < 50:
            issues["no_summary"] += 1

        # Chunks
        chunks = data.get("chunks", [])
        if not chunks:
            issues["empty_chunks"] += 1
        total_chunks += len(chunks)

        for c in chunks:
            ct = c.get("chunk_type", "unknown")
            chunk_types[ct] += 1

            # Check chunk fields
            for cf in chunk_fields:
                if cf not in c:
                    issues["missing_chunk_field"] += 1
                    break

            if not c.get("text", "").strip():
                issues["chunk_no_text"] += 1

            # Strategy from hierarchy_path
            hp = c.get("hierarchy_path", "")
            if "Điều" in hp or "Article" in hp:
                strategies["Article"] += 1
            elif "Section" in hp or "Mục" in hp:
                strategies["Section"] += 1
            elif "Table" in hp:
                strategies["Table"] += 1
            elif ct == "preamble":
                strategies["Preamble"] += 1
            else:
                strategies["Paragraph"] += 1

        # doc_id validation
        doc_id = data.get("doc_id", "")
        if not doc_id or doc_id.count("/") < 1:
            issues["invalid_doc_id"] += 1

    # Print
    for k, v in issues.items():
        flag = "🔴" if v > total * 0.1 else ("🟡" if v > 0 else "✅")
        print(f"  {flag} {k:25s}: {v:>4}/{total}  ({pct(v, total)})")
    print(f"\n  Total chunks across {total} files: {total_chunks:,}")
    print(f"  Chunk type distribution: {dict(chunk_types.most_common(8))}")
    print(f"  Strategy distribution:   {dict(strategies.most_common(8))}")

    bad_ratio = sum(issues.values()) / (total * len(issues))
    score = score_linear(bad_ratio, penalty_weight=400)
    print(f"\n  📊 JSON EXPORT SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# DIM C — CHUNKING QUALITY (from JSON exports)
# ═════════════════════════════════════════════════════════════════════════════
def audit_chunking(json_files):
    print_section("DIMENSION C: CHUNKING QUALITY")
    if not json_files:
        print("  ⚠  No JSON files found")
        return 0

    all_parents = []
    all_children = []
    all_chunks = []

    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            continue
        for c in data.get("chunks", []):
            all_chunks.append(c)
            ct = c.get("chunk_type", "parent")
            if ct == "parent":
                all_parents.append(c)
            elif ct == "child":
                all_children.append(c)

    total_p = len(all_parents)
    total_c = len(all_children)
    total_all = len(all_chunks)

    if total_p == 0:
        print("  ⚠  No parent chunks found")
        return 0

    print(f"  Total chunks: {total_all:,}  (parent: {total_p:,}, child: {total_c:,}, preamble: {total_all - total_p - total_c:,})")

    # C1: Parent/Child ratio
    pc_ratio = total_c / max(total_p, 1)
    flag_pc = "✅" if pc_ratio >= 1.5 else ("🟡" if pc_ratio >= 0.5 else "🔴")
    print(f"  {flag_pc} Child/Parent ratio     : {pc_ratio:.2f}  (target: ≥1.5)")

    # C2: Strategy distribution
    strat = Counter()
    for c in all_parents:
        hp = c.get("hierarchy_path", "")
        if "Điều" in hp or "Article" in hp:
            strat["Article"] += 1
        elif "Table" in hp:
            strat["Table"] += 1
        elif "Section" in hp or "Mục" in hp:
            strat["Section"] += 1
        else:
            strat["Paragraph"] += 1

    art_rate = strat.get("Article", 0) / max(total_p, 1)
    flag_art = "✅" if art_rate >= 0.3 else ("🟡" if art_rate >= 0.15 else "🔴")
    print(f"  {flag_art} Article strategy rate  : {art_rate * 100:.1f}%  (target: ≥30%)")
    print(f"     Strategy breakdown     : {dict(strat.most_common(8))}")

    # C3: Parent chunk length distribution
    p_lens = [len(c.get("text", "")) for c in all_parents]
    noise = sum(1 for l in p_lens if l < 100)
    short = sum(1 for l in p_lens if l < 50)
    oversized = sum(1 for l in p_lens if l > 8000)
    flag_noise = "✅" if noise / total_p < 0.05 else ("🟡" if noise / total_p < 0.1 else "🔴")
    flag_over = "✅" if oversized / total_p < 0.02 else "🟡"
    print(f"  {flag_noise} Parent <100c (noise)   : {noise}/{total_p}  ({pct(noise, total_p)})")
    print(f"     Parent <50c (critical) : {short}/{total_p}  ({pct(short, total_p)})")
    print(f"  {flag_over} Parent >8000c (oversized): {oversized}/{total_p}  ({pct(oversized, total_p)})")
    if p_lens:
        print(f"     Length stats: min={min(p_lens)}, max={max(p_lens)}, "
              f"mean={statistics.mean(p_lens):.0f}, median={statistics.median(p_lens):.0f}")

    # C4: Child chunk quality
    if total_c > 0:
        c_lens = [len(c.get("text", "")) for c in all_children]
        tiny_children = sum(1 for l in c_lens if l < 100)
        flag_cc = "✅" if tiny_children / total_c < 0.1 else "🟡"
        print(f"  {flag_cc} Child <100c             : {tiny_children}/{total_c}  ({pct(tiny_children, total_c)})")
    else:
        print(f"  🔴 No child chunks at all!")

    # C5: Duplicate detection (full text hash)
    fps = Counter(hashlib.md5(c.get("text", "").strip().encode()).hexdigest() for c in all_parents)
    dup_fps = {h: c for h, c in fps.items() if c > 1}
    dup_excess = sum(c - 1 for c in dup_fps.values())
    flag_dup = "✅" if dup_excess < total_p * 0.02 else ("🟡" if dup_excess < total_p * 0.05 else "🔴")
    print(f"  {flag_dup} Duplicate parent chunks : {dup_excess}  ({len(dup_fps)} unique fingerprints repeated)")

    # C6: Synthetic queries coverage
    has_synth = sum(1 for c in all_parents if is_valid_synthetic_queries(c.get("synthetic_queries", "")))
    synth_rate = has_synth / max(total_p, 1)
    flag_synth = "✅" if synth_rate >= 0.4 else ("🟡" if synth_rate >= 0.15 else "🔴")
    print(f"  {flag_synth} Synthetic query coverage: {has_synth}/{total_p}  ({pct(has_synth, total_p)}, target: ≥40%)")

    # Score
    penalties = 0
    if pc_ratio < 1.5:
        penalties += 15
    if art_rate < 0.3:
        penalties += 10
    if noise / total_p > 0.05:
        penalties += 10
    if dup_excess > total_p * 0.02:
        penalties += 15
    if synth_rate < 0.4:
        penalties += 10

    score = max(0, 100 - penalties)
    print(f"\n  📊 CHUNKING SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# DIM D — MILVUS / INGESTION QUALITY
# ═════════════════════════════════════════════════════════════════════════════
def audit_milvus(sample_limit: Optional[int] = None):
    limit = sample_limit or MILVUS_SAMPLE_LIMIT
    print_section("DIMENSION D: MILVUS INGESTION QUALITY")

    try:
        from pymilvus import connections, Collection, MilvusClient
        from core.config import get_settings
    except ImportError:
        print("  ⚠  pymilvus or core.config not available, checking via JSON exports only")
        return -1

    client = None
    try:
        s = get_settings()
        connections.connect(host=s.MILVUS_HOST, port=str(s.MILVUS_PORT))
        col = Collection(s.MILVUS_COLLECTION)
        col.load()
        client = MilvusClient(uri=f"http://{s.MILVUS_HOST}:{s.MILVUS_PORT}")

        total = col.num_entities
        print(f"  Total entities in collection: {total:,}")

        # Sample parents
        res = client.query(
            collection_name=s.MILVUS_COLLECTION,
            filter='chunk_type == "parent"',
            output_fields=[
                "text", "source", "page", "doc_type", "source_category",
                "is_table", "synthetic_queries", "doc_number", "doc_id",
            ],
            limit=limit,
        )
    except Exception as e:
        print(f"  ⚠  Cannot connect to Milvus: {e}")
        return -1
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    n = len(res)
    print(f"  Sampled {n:,} parent chunks from Milvus\n")

    if n == 0:
        return 0

    # D1: Text Length
    lengths = [len(r["text"]) for r in res]
    noise = sum(1 for l in lengths if l < 100)
    short = sum(1 for l in lengths if l < 50)
    oversized = sum(1 for l in lengths if l > 8000)
    flag_noise = "✅" if noise / n < 0.05 else ("🟡" if noise / n < 0.1 else "🔴")
    print(f"  {flag_noise} <100c noise chunks     : {noise}/{n}  ({pct(noise, n)})")
    print(f"     <50c critical noise    : {short}/{n}")
    print(f"     >8000c oversized       : {oversized}/{n}")
    if lengths:
        print(f"     Length stats: min={min(lengths)}, max={max(lengths)}, "
              f"mean={statistics.mean(lengths):.0f}, median={statistics.median(lengths):.0f}")

    # D2: Paragraph fragmentation
    def count_short_lines(text):
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return sum(1 for l in lines if 5 < len(l) < 60)

    fragmented = sum(1 for r in res if count_short_lines(r["text"]) > 5)
    flag_frag = "✅" if fragmented / n < 0.05 else "🟡"
    print(f"  {flag_frag} Fragment-heavy chunks  : {fragmented}/{n}  ({pct(fragmented, n)})")

    # D3: Table detection
    is_table_count = sum(1 for r in res if r.get("is_table"))
    md_table = sum(1 for r in res if not r.get("is_table") and r["text"].count("|") > 3)
    flag_tbl = "✅" if md_table < 5 else "🟡"
    print(f"  {flag_tbl} is_table=True          : {is_table_count}")
    print(f"     Unflagged tables (|)   : {md_table}")

    # D4: Metadata
    missing_dn = sum(1 for r in res if not r.get("doc_number", "").strip())
    khac = sum(1 for r in res if r.get("source_category", "KHAC") == "KHAC")
    has_synth = sum(1 for r in res if is_valid_synthetic_queries(r.get("synthetic_queries", "")))
    flag_dn = "✅" if missing_dn / n < 0.05 else "🟡"
    flag_khac = "✅" if khac / n < 0.2 else "🟡"
    flag_synth = "✅" if has_synth / n > 0.4 else ("🟡" if has_synth / n > 0.15 else "🔴")
    print(f"  {flag_dn} Missing doc_number     : {missing_dn}/{n}  ({pct(missing_dn, n)})")
    print(f"  {flag_khac} source_category=KHAC   : {khac}/{n}  ({pct(khac, n)})")
    print(f"  {flag_synth} Has synthetic_queries  : {has_synth}/{n}  ({pct(has_synth, n)})")
    print(f"     doc_type dist          : {dict(Counter(r.get('doc_type', '?') for r in res).most_common(5))}")
    print(f"     source_category dist   : {dict(Counter(r.get('source_category', '?') for r in res).most_common(8))}")

    # D5: AI Leakage
    monologue = [
        "certainly,", "i'll", "i will", "as an ai", "here is",
        "here's", "i cannot", "i would", "xin lỗi", "dưới đây là",
        "thinking process", "analyze the request", "tư duy suy luận",
    ]
    leaked = sum(1 for r in res if any(p in r["text"].lower() for p in monologue))
    flag_leak = "✅" if leaked == 0 else ("🟡" if leaked < 3 else "🔴")
    print(f"  {flag_leak} AI monologue leakage   : {leaked}/{n}")

    # D6: OCR Spacing artifacts
    def spacing_ratio(text):
        sp = text.count(" ")
        chars = len(text.replace(" ", ""))
        return sp / (chars + sp + 1)

    bad_sp = sum(1 for r in res if spacing_ratio(r["text"]) > 0.35)
    flag_sp = "✅" if bad_sp == 0 else ("🟡" if bad_sp / n < 0.05 else "🔴")
    print(f"  {flag_sp} OCR spacing artifacts  : {bad_sp}/{n}  ({pct(bad_sp, n)})")

    # D7: Duplicate content (full text hash in Milvus)
    fps = Counter(hashlib.md5(r["text"].strip().encode()).hexdigest() for r in res)
    dup_fps = {h: c for h, c in fps.items() if c > 1}
    dup_excess = sum(c - 1 for c in dup_fps.values())
    flag_dup = "✅" if dup_excess < 5 else ("🟡" if dup_excess / n < 0.05 else "🔴")
    print(f"  {flag_dup} Duplicate chunks       : {dup_excess} excess (from {len(dup_fps)} repeated FPs)")

    # D8: Unique docs
    unique_docs = len(set(r.get("doc_id", "") for r in res))
    print(f"     Unique doc_ids sampled : {unique_docs}")

    # Score
    penalties = 0
    if noise / n > 0.05:
        penalties += 10
    if fragmented / n > 0.05:
        penalties += 5
    if leaked > 0:
        penalties += 10
    if bad_sp > 0:
        penalties += 5
    if dup_excess > 5:
        penalties += 10
    if has_synth / n < 0.4:
        penalties += 10
    if missing_dn / n > 0.05:
        penalties += 5
    if khac / n > 0.2:
        penalties += 5

    score = max(0, 100 - penalties)
    print(f"\n  📊 MILVUS INGESTION SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# DIM E — PDF→MARKDOWN FIDELITY
# ═════════════════════════════════════════════════════════════════════════════
def audit_fidelity(json_files, pdf_source_dir):
    print_section("DIMENSION E: PDF→MARKDOWN FIDELITY")

    if not json_files:
        print("  ⚠  No JSON files found")
        return 0

    # Count PDFs
    pdf_count = 0
    for root, _, files in os.walk(pdf_source_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_count += 1

    exported = len(json_files)
    if pdf_count == 0:
        coverage = 0.0
    else:
        coverage = exported / pdf_count
    flag_cov = "✅" if coverage >= 0.9 else ("🟡" if coverage >= 0.5 else "🔴")
    print(f"  {flag_cov} Source PDFs found      : {pdf_count:,}")
    print(f"     Exported documents    : {exported}")
    print(f"     Coverage              : {coverage * 100:.1f}%")

    # Per-doc metrics
    total_pages = 0
    docs_with_chunks = 0
    pages_per_doc = []
    chunks_per_doc = []
    text_lengths = []
    docs_no_content = 0

    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            continue

        chunks = data.get("chunks", [])
        if not chunks:
            docs_no_content += 1
            continue

        docs_with_chunks += 1
        chunk_pages = set(c.get("page", 0) for c in chunks)
        n_pages = max(chunk_pages) if chunk_pages else 0
        pages_per_doc.append(n_pages)
        chunks_per_doc.append(len(chunks))

        total_text = sum(len(c.get("text", "")) for c in chunks)
        text_lengths.append(total_text)

    # Docs with no content
    flag_nc = "✅" if docs_no_content == 0 else "🟡"
    print(f"  {flag_nc} Docs with no chunks    : {docs_no_content}/{exported}")

    # Page coverage basics
    if pages_per_doc:
        print(f"     Pages/doc stats: min={min(pages_per_doc)}, max={max(pages_per_doc)}, "
              f"mean={statistics.mean(pages_per_doc):.1f}")
    if chunks_per_doc:
        print(f"     Chunks/doc stats: min={min(chunks_per_doc)}, max={max(chunks_per_doc)}, "
              f"mean={statistics.mean(chunks_per_doc):.1f}")

    # Text length distribution
    if text_lengths:
        very_short = sum(1 for l in text_lengths if l < 500)
        flag_vs = "✅" if very_short / exported < 0.05 else "🟡"
        print(f"  {flag_vs} Very short docs (<500c): {very_short}/{exported}")
        print(f"     Text/doc stats: min={min(text_lengths)}, max={max(text_lengths)}, "
              f"mean={statistics.mean(text_lengths):.0f}")

    # Table detection rate
    docs_with_tables = 0
    table_chunks = 0
    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            continue
        tables = [c for c in data.get("chunks", []) if c.get("is_table")]
        if tables:
            docs_with_tables += 1
            table_chunks += len(tables)

    table_doc_rate = docs_with_tables / max(exported, 1)
    flag_td = "✅" if table_doc_rate > 0.1 else "🟡"
    print(f"  {flag_td} Docs with tables       : {docs_with_tables}/{exported}  ({pct(docs_with_tables, exported)})")
    print(f"     Total table chunks    : {table_chunks}")

    # Score
    penalties = 0
    if coverage < 0.9:
        penalties += 20
    if docs_no_content > 0:
        penalties += 5
    if text_lengths and sum(1 for l in text_lengths if l < 500) / max(exported, 1) > 0.05:
        penalties += 10

    score = max(0, 100 - penalties)
    print(f"\n  📊 FIDELITY SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
def run_comprehensive_audit(
    json_dir: Optional[str] = None,
    md_dir: Optional[str] = None,
    pdf_dir: Optional[str] = None,
    sample_limit: Optional[int] = None,
) -> str:
    """Run all 5 audit dimensions in-process and return the formatted text report.

    Thread-safe stdout redirection without touching sys.stderr.
    """
    buf = io.StringIO()
    with _audit_lock:
        with contextlib.redirect_stdout(buf):
            target_json = json_dir or EXPORT_JSON_DIR
            target_md = md_dir or EXPORT_MD_DIR
            target_pdf = pdf_dir or PDF_SOURCE_DIR

            print(f"\n{SEPARATOR}")
            print("  COMPREHENSIVE RAG QUALITY AUDIT")
            print(f"  JSON: {target_json}")
            print(f"  MD:   {target_md}")
            print(f"  PDFs: {target_pdf}")
            print(SEPARATOR)

            json_files = sorted(glob.glob(os.path.join(target_json, "*.json")))
            md_files = sorted(glob.glob(os.path.join(target_md, "*.md")))
            print(f"\n  Found {len(json_files)} JSON exports, {len(md_files)} Markdown exports")

            scores = {}
            scores["A_markdown"] = audit_markdown(md_files)
            scores["B_json"] = audit_json(json_files)
            scores["C_chunking"] = audit_chunking(json_files)
            scores["D_milvus"] = audit_milvus(sample_limit=sample_limit)
            scores["E_fidelity"] = audit_fidelity(json_files, target_pdf)

            # Final Report
            print(f"\n\n{SEPARATOR}")
            print("  FINAL QUALITY REPORT")
            print(SEPARATOR)

            valid_scores = {k: v for k, v in scores.items() if v >= 0}
            for dim, s in sorted(valid_scores.items()):
                bar = "█" * (s // 5) + "░" * (20 - s // 5)
                emoji = "✅" if s >= 85 else ("🟡" if s >= 65 else "🔴")
                dim_name = {
                    "A_markdown": "Markdown Quality",
                    "B_json": "JSON Export Quality",
                    "C_chunking": "Chunking Quality",
                    "D_milvus": "Milvus Ingestion",
                    "E_fidelity": "PDF→MD Fidelity",
                }.get(dim, dim)
                print(f"  {emoji} {dim_name:25s} {bar} {s:>3}/100")

            if valid_scores:
                overall = sum(valid_scores.values()) // len(valid_scores)
                print(f"\n  {'═' * 50}")
                overall_emoji = "✅" if overall >= 85 else ("🟡" if overall >= 65 else "🔴")
                print(f"  {overall_emoji} OVERALL QUALITY SCORE: {overall}/100")
                print(f"  {'═' * 50}")

            if scores.get("D_milvus", 0) < 0:
                print("\n  ⚠  Milvus dimension skipped (not available). Run inside Docker for full audit.")

            print()

    return buf.getvalue()


def main():
    sys.stdout.write(run_comprehensive_audit())


if __name__ == "__main__":
    main()
