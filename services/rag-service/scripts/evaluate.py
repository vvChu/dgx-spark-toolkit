#!/usr/bin/env python3
"""Autoresearch Evaluator — Runs audit and parses scores.

Usage inside Docker:
    python3 evaluate.py

Or from host:
    cd path/to/dgx-spark-toolkit
    docker compose exec rag-service python3 evaluate.py

Output: JSON with overall_score, per-dimension scores, P1-P6 status.
Also appends to results.tsv.
"""

import os
import re
import sys
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path


RESULTS_TSV = os.path.join(os.path.dirname(__file__), "results.tsv")
AUDIT_DIR = os.path.join(os.path.dirname(__file__), "audit_results")


def run_audit() -> str:
    """Run comprehensive_audit.py and capture output."""
    script = os.path.join(os.path.dirname(__file__), "comprehensive_audit.py")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.stdout + result.stderr


def parse_audit_output(output: str) -> dict:
    """Parse audit stdout into structured scores."""
    scores = {}

    # Parse dimension scores
    dim_patterns = {
        "A_markdown": r"MARKDOWN SCORE:\s*(\d+)/100",
        "B_json": r"JSON EXPORT SCORE:\s*(\d+)/100",
        "C_chunking": r"CHUNKING SCORE:\s*(\d+)/100",
        "D_milvus": r"MILVUS INGESTION SCORE:\s*(\d+)/100",
        "E_fidelity": r"FIDELITY SCORE:\s*(\d+)/100",
    }

    for key, pattern in dim_patterns.items():
        m = re.search(pattern, output)
        if m:
            scores[key] = int(m.group(1))

    # Parse overall score
    m = re.search(r"OVERALL QUALITY SCORE:\s*(\d+)/100", output)
    scores["overall"] = int(m.group(1)) if m else -1

    # Parse P1-P6 indicators
    p_issues = {}

    # P1: Broken tables
    m = re.search(r"broken_table\s*:\s*(\d+)/(\d+)\s*\(([^)]+)\)", output)
    if m:
        p_issues["P1_broken_table"] = {"count": int(m.group(1)), "total": int(m.group(2)), "pct": m.group(3)}

    # P2: AI leakage
    m = re.search(r"ai_leakage\s*:\s*(\d+)/(\d+)\s*\(([^)]+)\)", output)
    if m:
        p_issues["P2_ai_leakage_md"] = {"count": int(m.group(1)), "total": int(m.group(2)), "pct": m.group(3)}
    m = re.search(r"AI monologue leakage\s*:\s*(\d+)/(\d+)", output)
    if m:
        p_issues["P2_ai_leakage_milvus"] = {"count": int(m.group(1)), "total": int(m.group(2))}

    # P3: Article strategy rate
    m = re.search(r"Article strategy rate\s*:\s*([\d.]+)%", output)
    if m:
        p_issues["P3_article_rate"] = {"pct": float(m.group(1))}

    # P4: Missing doc_number
    m = re.search(r"Missing doc_number\s*:\s*(\d+)/(\d+)\s*\(([^)]+)\)", output)
    if m:
        p_issues["P4_missing_docnum"] = {"count": int(m.group(1)), "total": int(m.group(2)), "pct": m.group(3)}

    # P5: Boilerplate
    m = re.search(r"boilerplate\s*:\s*(\d+)/(\d+)\s*\(([^)]+)\)", output)
    if m:
        p_issues["P5_boilerplate"] = {"count": int(m.group(1)), "total": int(m.group(2)), "pct": m.group(3)}

    # P6: Child/Parent ratio
    m = re.search(r"Child/Parent ratio\s*:\s*([\d.]+)", output)
    if m:
        p_issues["P6_child_parent"] = {"ratio": float(m.group(1))}

    scores["p_issues"] = p_issues
    return scores


def append_result(change_desc: str, scores: dict, time_sec: float, verdict: str, fixed_issues: str = ""):
    """Append result to results.tsv."""
    os.makedirs(os.path.dirname(RESULTS_TSV), exist_ok=True)

    # Create header if file doesn't exist
    if not os.path.exists(RESULTS_TSV):
        with open(RESULTS_TSV, "w") as f:
            f.write("timestamp\tchange_description\toverall_score\tA\tB\tC\tD\tE\ttime_sec\tverdict\tfixed_issues\n")

    with open(RESULTS_TSV, "a") as f:
        f.write(
            f"{datetime.now().isoformat()}\t"
            f"{change_desc}\t"
            f"{scores.get('overall', -1)}\t"
            f"{scores.get('A_markdown', -1)}\t"
            f"{scores.get('B_json', -1)}\t"
            f"{scores.get('C_chunking', -1)}\t"
            f"{scores.get('D_milvus', -1)}\t"
            f"{scores.get('E_fidelity', -1)}\t"
            f"{time_sec:.1f}\t"
            f"{verdict}\t"
            f"{fixed_issues}\n"
        )


def save_audit_result(output: str, label: str = "latest"):
    """Save raw audit output to audit_results/."""
    os.makedirs(AUDIT_DIR, exist_ok=True)
    path = os.path.join(AUDIT_DIR, f"{label}.md")
    with open(path, "w") as f:
        f.write(f"# Audit Result — {label}\n\n")
        f.write(f"```\n{output}\n```\n")


def evaluate(change_desc: str = "baseline") -> dict:
    """Full evaluation cycle: run audit, parse, log, save."""
    start = time.time()

    output = run_audit()
    elapsed = time.time() - start

    scores = parse_audit_output(output)

    # Save raw output
    save_audit_result(output)

    # Print summary
    print(f"\n{'='*50}")
    print(f"  OVERALL: {scores.get('overall', '?')}/100  ({elapsed:.1f}s)")
    for dim in ["A_markdown", "B_json", "C_chunking", "D_milvus", "E_fidelity"]:
        print(f"  {dim}: {scores.get(dim, '?')}/100")
    print(f"{'='*50}")

    if scores.get("p_issues"):
        print("\n  P-Issue Status:")
        for k, v in scores["p_issues"].items():
            print(f"    {k}: {v}")

    # Log to TSV
    append_result(change_desc, scores, elapsed, "BASELINE" if change_desc == "baseline" else "PENDING")

    return scores


if __name__ == "__main__":
    desc = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    evaluate(desc)
