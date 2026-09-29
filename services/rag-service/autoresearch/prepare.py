#!/usr/bin/env python3
"""Autoresearch — Fixed evaluation & data utilities.

██████████████████████████████████████████████████████████████████████████
██  DO NOT MODIFY THIS FILE.  It is the fixed evaluation harness.     ██
██  The AI Agent only modifies optimize_rag.py.                        ██
██████████████████████████████████████████████████████████████████████████

Usage:
    python3 prepare.py                 # Verify data, print stats
    python3 prepare.py evaluate        # Run full 5-dimension audit
    python3 prepare.py evaluate "desc" # Run audit with custom description
"""

import os
import re
import sys
import json
import glob
import time
import hashlib
import statistics
import subprocess
from datetime import datetime
from pathlib import Path
from collections import Counter

# ── Directories (FIXED — do not change) ─────────────────────────────────
RAG_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTORESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))

# Source PDF directories
PDF_SOURCE_DIRS = [
    str(Path.home() / "Public/QCVN"),
    str(Path.home() / "Public/VB phap quy"),
]

# Export directories (where optimize_rag.py writes output)
EXPORT_DIR = os.environ.get("EXPORT_DIR", str(Path.home() / "Public/exports"))
EXPORT_JSON_DIR = os.path.join(EXPORT_DIR, "json")
EXPORT_MD_DIR = os.path.join(EXPORT_DIR, "markdown")

# Results log
RESULTS_TSV = os.path.join(AUTORESEARCH_DIR, "results.tsv")

SEPARATOR = "=" * 50


# ═════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═════════════════════════════════════════════════════════════════════════

def find_all_pdfs() -> list[str]:
    """Find all source PDFs from the configured directories."""
    pdfs = []
    for src_dir in PDF_SOURCE_DIRS:
        if not os.path.isdir(src_dir):
            print(f"  ⚠ Source directory not found: {src_dir}")
            continue
        for root, _, files in os.walk(src_dir):
            for f in files:
                if f.lower().endswith(".pdf"):
                    pdfs.append(os.path.join(root, f))
    return sorted(pdfs)


def load_sample_pdfs(max_count: int = 10) -> list[str]:
    """Load a sample of PDFs for quick experiments."""
    all_pdfs = find_all_pdfs()
    return all_pdfs[:max_count]


def print_data_stats():
    """Print statistics about available data."""
    all_pdfs = find_all_pdfs()
    print(f"\n  Source Data Statistics:")
    for src_dir in PDF_SOURCE_DIRS:
        count = sum(1 for p in all_pdfs if p.startswith(src_dir))
        print(f"    {src_dir}: {count} PDFs")
    print(f"    Total: {len(all_pdfs)} PDFs\n")

    # Check exports
    json_files = glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json"))
    md_files = glob.glob(os.path.join(EXPORT_MD_DIR, "*.md"))
    print(f"  Export Statistics:")
    print(f"    JSON exports: {len(json_files)}")
    print(f"    Markdown exports: {len(md_files)}")
    print(f"    Export dir: {EXPORT_DIR}\n")


# ═════════════════════════════════════════════════════════════════════════
# SCORING UTILITIES
# ═════════════════════════════════════════════════════════════════════════

def pct(n: int, total: int) -> str:
    return f"{n / max(total, 1) * 100:.1f}%"


def score_linear(bad_ratio: float, penalty_weight: int = 100) -> int:
    """0 issues = 100, 100% issues = 0."""
    return max(0, int(100 - bad_ratio * penalty_weight))


# ═════════════════════════════════════════════════════════════════════════
# DIMENSION A — MARKDOWN QUALITY
# ═════════════════════════════════════════════════════════════════════════

def audit_markdown(md_files: list[str]) -> int:
    total = len(md_files)
    if total == 0:
        print("  ⚠  No markdown files found")
        return 0

    issues = {
        "no_h1": 0, "no_headings": 0, "broken_table": 0,
        "ai_leakage": 0, "ocr_spacing": 0, "boilerplate": 0,
        "encoding_issues": 0, "very_short": 0,
    }
    ai_patterns = [
        r"(?i)\bcertainly\b", r"(?i)\bI'll\b", r"(?i)\bAs an AI\b",
        r"(?i)\bHere is\b", r"(?i)\bI cannot\b", r"(?i)\bI would\b",
        r"(?i)\bI will\b", r"(?i)\bHere's\b",
        r"(?i)Xin lỗi", r"(?i)Dưới đây là", r"(?i)Tôi xin",
    ]
    boilerplate_re = re.compile(
        r"CỘNG\s+HÒA\s+XÃ\s+HỘI|"
        r"Độc lập\s*[-–—]\s*Tự do\s*[-–—]\s*Hạnh phúc|"
        r"Số:\s*\d+/\w+",
        re.IGNORECASE,
    )
    ocr_space_re = re.compile(r"[A-ZĐ]\s[A-ZĐ]\s[A-ZĐ]")
    pipe_row_re = re.compile(r"^\s*\|[^|]+\|[^|]+\|", re.MULTILINE)
    sep_row_re = re.compile(r"^\s*\|[-:\s|]+\|\s*$", re.MULTILINE)

    for f in md_files:
        try:
            text = Path(f).read_text(errors="replace")
        except Exception:
            issues["encoding_issues"] += 1
            continue

        if len(text) < 200:
            issues["very_short"] += 1
        if not re.search(r"^# ", text, re.MULTILINE):
            issues["no_h1"] += 1
        if not re.search(r"^#{1,4} ", text, re.MULTILINE):
            issues["no_headings"] += 1

        has_pipes = bool(pipe_row_re.search(text))
        has_sep = bool(sep_row_re.search(text))
        if has_pipes and not has_sep:
            issues["broken_table"] += 1

        for pat in ai_patterns:
            if re.search(pat, text):
                issues["ai_leakage"] += 1
                break

        if ocr_space_re.search(text):
            issues["ocr_spacing"] += 1

        content_match = re.search(r"## Content\s*\n(.*)", text, re.DOTALL)
        if content_match and boilerplate_re.search(content_match.group(1)[:500]):
            issues["boilerplate"] += 1

        if "\ufffd" in text or "\\x" in text[:200]:
            issues["encoding_issues"] += 1

    for k, v in issues.items():
        flag = "🔴" if v > total * 0.1 else ("🟡" if v > 0 else "✅")
        print(f"  {flag} {k:25s}: {v:>4}/{total}  ({pct(v, total)})")

    bad_ratio = sum(issues.values()) / (total * len(issues))
    score = score_linear(bad_ratio, penalty_weight=400)
    print(f"\n  📊 MARKDOWN SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════
# DIMENSION B — JSON EXPORT QUALITY
# ═════════════════════════════════════════════════════════════════════════

def audit_json(json_files: list[str]) -> int:
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
        "missing_root_field": 0, "missing_meta_field": 0, "no_summary": 0,
        "empty_chunks": 0, "missing_chunk_field": 0, "invalid_doc_id": 0,
        "chunk_no_text": 0,
    }
    total_chunks = 0
    chunk_types = Counter()

    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            issues["missing_root_field"] += 1
            continue

        for rf in required_fields:
            if rf not in data or not data[rf]:
                issues["missing_root_field"] += 1
                break

        meta = data.get("metadata", {})
        for mf in meta_fields:
            if not meta.get(mf, "").strip() if isinstance(meta.get(mf), str) else not meta.get(mf):
                issues["missing_meta_field"] += 1
                break

        summary = data.get("summary", "")
        if not summary or len(summary) < 50:
            issues["no_summary"] += 1

        chunks = data.get("chunks", [])
        if not chunks:
            issues["empty_chunks"] += 1
        total_chunks += len(chunks)

        for c in chunks:
            chunk_types[c.get("chunk_type", "unknown")] += 1
            for cf in chunk_fields:
                if cf not in c:
                    issues["missing_chunk_field"] += 1
                    break
            if not c.get("text", "").strip():
                issues["chunk_no_text"] += 1

        doc_id = data.get("doc_id", "")
        if not doc_id or doc_id.count("/") < 1:
            issues["invalid_doc_id"] += 1

    for k, v in issues.items():
        flag = "🔴" if v > total * 0.1 else ("🟡" if v > 0 else "✅")
        print(f"  {flag} {k:25s}: {v:>4}/{total}  ({pct(v, total)})")
    print(f"\n  Total chunks across {total} files: {total_chunks:,}")

    bad_ratio = sum(issues.values()) / (total * len(issues))
    score = score_linear(bad_ratio, penalty_weight=400)
    print(f"\n  📊 JSON EXPORT SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════
# DIMENSION C — CHUNKING QUALITY
# ═════════════════════════════════════════════════════════════════════════

def audit_chunking(json_files: list[str]) -> int:
    if not json_files:
        print("  ⚠  No JSON files found")
        return 0

    all_parents, all_children, all_chunks = [], [], []

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

    print(f"  Total chunks: {total_all:,}  (parent: {total_p:,}, child: {total_c:,})")

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

    # C3: Parent chunk length distribution
    p_lens = [len(c.get("text", "")) for c in all_parents]
    noise = sum(1 for l in p_lens if l < 100)
    oversized = sum(1 for l in p_lens if l > 8000)
    flag_noise = "✅" if noise / total_p < 0.05 else ("🟡" if noise / total_p < 0.1 else "🔴")
    print(f"  {flag_noise} Parent <100c (noise)   : {noise}/{total_p}  ({pct(noise, total_p)})")
    if p_lens:
        print(f"     Length stats: min={min(p_lens)}, max={max(p_lens)}, "
              f"mean={statistics.mean(p_lens):.0f}, median={statistics.median(p_lens):.0f}")

    # C4: Duplicate detection
    fps = Counter(hashlib.md5(c.get("text", "").strip().encode()).hexdigest() for c in all_parents)
    dup_excess = sum(c - 1 for c in fps.values() if c > 1)
    flag_dup = "✅" if dup_excess < total_p * 0.02 else "🟡"
    print(f"  {flag_dup} Duplicate parent chunks : {dup_excess}")

    # C5: Synthetic queries coverage
    has_synth = sum(1 for c in all_parents if c.get("synthetic_queries", "").strip())
    synth_rate = has_synth / max(total_p, 1)
    flag_synth = "✅" if synth_rate >= 0.4 else ("🟡" if synth_rate >= 0.15 else "🔴")
    print(f"  {flag_synth} Synthetic query coverage: {has_synth}/{total_p}  ({pct(has_synth, total_p)})")

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


# ═════════════════════════════════════════════════════════════════════════
# DIMENSION D — EXPORT CONSISTENCY (offline, no Milvus needed)
# ═════════════════════════════════════════════════════════════════════════

def audit_export_consistency(json_files: list[str]) -> int:
    """Check export quality without needing a running Milvus instance."""
    if not json_files:
        print("  ⚠  No JSON files found")
        return 0

    all_parents = []
    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            continue
        for c in data.get("chunks", []):
            if c.get("chunk_type") == "parent":
                all_parents.append(c)

    n = len(all_parents)
    if n == 0:
        return 0

    print(f"  Sampled {n:,} parent chunks from exports\n")

    # D1: Text length
    lengths = [len(c.get("text", "")) for c in all_parents]
    noise = sum(1 for l in lengths if l < 100)
    flag_noise = "✅" if noise / n < 0.05 else "🟡"
    print(f"  {flag_noise} <100c noise chunks     : {noise}/{n}  ({pct(noise, n)})")

    # D2: AI Leakage
    monologue = ["certainly,", "i'll", "i will", "as an ai", "here is",
                 "here's", "i cannot", "i would", "xin lỗi", "dưới đây là"]
    leaked = sum(1 for c in all_parents if any(p in c.get("text", "").lower() for p in monologue))
    flag_leak = "✅" if leaked == 0 else ("🟡" if leaked < 3 else "🔴")
    print(f"  {flag_leak} AI monologue leakage   : {leaked}/{n}")

    # D3: Missing doc_number
    missing_dn = sum(1 for c in all_parents if not c.get("doc_number", "").strip())
    flag_dn = "✅" if missing_dn / n < 0.05 else "🟡"
    print(f"  {flag_dn} Missing doc_number     : {missing_dn}/{n}  ({pct(missing_dn, n)})")

    # D4: Duplicates
    fps = Counter(hashlib.md5(c.get("text", "").strip().encode()).hexdigest() for c in all_parents)
    dup_excess = sum(c - 1 for c in fps.values() if c > 1)
    flag_dup = "✅" if dup_excess < 5 else "🟡"
    print(f"  {flag_dup} Duplicate chunks       : {dup_excess}")

    # Score
    penalties = 0
    if noise / n > 0.05:
        penalties += 10
    if leaked > 0:
        penalties += 10
    if dup_excess > 5:
        penalties += 10
    if missing_dn / n > 0.05:
        penalties += 5

    score = max(0, 100 - penalties)
    print(f"\n  📊 EXPORT CONSISTENCY SCORE: {score}/100")
    return score


# ═════════════════════════════════════════════════════════════════════════
# DIMENSION E — PDF→EXPORT FIDELITY
# ═════════════════════════════════════════════════════════════════════════

def audit_fidelity(json_files: list[str]) -> int:
    all_pdfs = find_all_pdfs()
    pdf_count = len(all_pdfs)
    exported = len(json_files)

    coverage = exported / max(pdf_count, 1)
    flag_cov = "✅" if coverage >= 0.9 else ("🟡" if coverage >= 0.5 else "🔴")
    print(f"  {flag_cov} Source PDFs found      : {pdf_count:,}")
    print(f"     Exported documents    : {exported}")
    print(f"     Coverage              : {coverage * 100:.1f}%")

    docs_no_content = 0
    text_lengths = []
    docs_with_tables = 0

    for f in json_files:
        try:
            data = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            continue

        chunks = data.get("chunks", [])
        if not chunks:
            docs_no_content += 1
            continue

        total_text = sum(len(c.get("text", "")) for c in chunks)
        text_lengths.append(total_text)

        if any(c.get("is_table") for c in chunks):
            docs_with_tables += 1

    flag_nc = "✅" if docs_no_content == 0 else "🟡"
    print(f"  {flag_nc} Docs with no chunks    : {docs_no_content}/{exported}")

    if text_lengths:
        very_short = sum(1 for l in text_lengths if l < 500)
        flag_vs = "✅" if very_short / exported < 0.05 else "🟡"
        print(f"  {flag_vs} Very short docs (<500c): {very_short}/{exported}")

    table_doc_rate = docs_with_tables / max(exported, 1)
    flag_td = "✅" if table_doc_rate > 0.1 else "🟡"
    print(f"  {flag_td} Docs with tables       : {docs_with_tables}/{exported}  ({pct(docs_with_tables, exported)})")

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


# ═════════════════════════════════════════════════════════════════════════
# FULL EVALUATION
# ═════════════════════════════════════════════════════════════════════════

def evaluate(change_desc: str = "baseline") -> dict:
    """Run the full 5-dimension audit on exports."""
    start = time.time()

    json_files = sorted(glob.glob(os.path.join(EXPORT_JSON_DIR, "*.json")))
    md_files = sorted(glob.glob(os.path.join(EXPORT_MD_DIR, "*.md")))

    # Remove .bak files
    json_files = [f for f in json_files if not f.endswith(".bak")]
    md_files = [f for f in md_files if not f.endswith(".bak")]

    print(f"\n{SEPARATOR}")
    print(f"  AUTORESEARCH QUALITY AUDIT")
    print(f"  JSON: {EXPORT_JSON_DIR} ({len(json_files)} files)")
    print(f"  MD:   {EXPORT_MD_DIR} ({len(md_files)} files)")
    print(SEPARATOR)

    scores = {}

    print(f"\n{'─' * 50}\n  DIMENSION A: MARKDOWN QUALITY\n{'─' * 50}")
    scores["A_markdown"] = audit_markdown(md_files)

    print(f"\n{'─' * 50}\n  DIMENSION B: JSON EXPORT QUALITY\n{'─' * 50}")
    scores["B_json"] = audit_json(json_files)

    print(f"\n{'─' * 50}\n  DIMENSION C: CHUNKING QUALITY\n{'─' * 50}")
    scores["C_chunking"] = audit_chunking(json_files)

    print(f"\n{'─' * 50}\n  DIMENSION D: EXPORT CONSISTENCY\n{'─' * 50}")
    scores["D_consistency"] = audit_export_consistency(json_files)

    print(f"\n{'─' * 50}\n  DIMENSION E: PDF→EXPORT FIDELITY\n{'─' * 50}")
    scores["E_fidelity"] = audit_fidelity(json_files)

    elapsed = time.time() - start

    # Overall
    valid_scores = {k: v for k, v in scores.items() if v >= 0}
    overall = sum(valid_scores.values()) // len(valid_scores) if valid_scores else 0
    scores["overall"] = overall

    print(f"\n\n{SEPARATOR}")
    print(f"  OVERALL: {overall}/100  ({elapsed:.1f}s)")
    for dim in ["A_markdown", "B_json", "C_chunking", "D_consistency", "E_fidelity"]:
        print(f"  {dim}: {scores.get(dim, '?')}/100")
    print(SEPARATOR)

    # Log to TSV
    _append_result(change_desc, scores, elapsed)

    return scores


def _append_result(change_desc: str, scores: dict, time_sec: float):
    """Append result to results.tsv."""
    if not os.path.exists(RESULTS_TSV):
        with open(RESULTS_TSV, "w") as f:
            f.write("commit\toverall_score\tA\tB\tC\tD\tE\tstatus\tdescription\n")

    # Get current git commit
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=AUTORESEARCH_DIR, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        commit = "unknown"

    with open(RESULTS_TSV, "a") as f:
        f.write(
            f"{commit}\t"
            f"{scores.get('overall', 0)}\t"
            f"{scores.get('A_markdown', 0)}\t"
            f"{scores.get('B_json', 0)}\t"
            f"{scores.get('C_chunking', 0)}\t"
            f"{scores.get('D_consistency', 0)}\t"
            f"{scores.get('E_fidelity', 0)}\t"
            f"keep\t"
            f"{change_desc}\n"
        )
    print(f"\n  📝 Logged to {RESULTS_TSV}")


# ═════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "evaluate":
        desc = sys.argv[2] if len(sys.argv) >= 3 else "baseline"
        evaluate(desc)
    else:
        print("\n  📂 Autoresearch — Data Verification")
        print(f"  RAG service: {RAG_SERVICE_DIR}")
        print(f"  Autoresearch: {AUTORESEARCH_DIR}")
        print_data_stats()
        print("  Usage:")
        print("    python3 prepare.py              # This help + data stats")
        print('    python3 prepare.py evaluate      # Run full audit')
        print('    python3 prepare.py evaluate "description"  # Audit with label')


if __name__ == "__main__":
    main()
