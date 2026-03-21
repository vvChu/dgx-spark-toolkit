#!/usr/bin/env python3
"""Autoresearch runner — executes pipeline fixes + audit locally on host Python.

Usage:
    python3 run.py [change_description]

Output: JSON scorecard to stdout.
"""

import os
import sys
import json
import time

# ── Setup environment BEFORE any imports from the rag-service ──
RAG_SERVICE_DIR = "/home/vvc/Codebase/dgx-spark-toolkit/services/rag-service"
RAG_SCRIPTS_DIR = os.path.join(RAG_SERVICE_DIR, "scripts")
sys.path.insert(0, RAG_SERVICE_DIR)
sys.path.insert(0, RAG_SCRIPTS_DIR)
os.chdir(RAG_SERVICE_DIR)

os.environ["EXPORT_JSON_DIR"] = "/home/vvc/Public/exports/json"
os.environ["EXPORT_MD_DIR"] = "/home/vvc/Public/exports/markdown"
os.environ["PDF_SOURCE_DIR"] = "/home/vvc/Public/exports"
os.environ["MILVUS_HOST"] = "100.83.192.30"
os.environ["MILVUS_PORT"] = "19530"

# Disable pydantic secrets validation for local run (no Neo4j/LiteLLM needed)
os.environ.setdefault("NEO4J_PASSWORD", "local_audit_dummy_safe_pw_2026!")
os.environ.setdefault("LITELLM_MASTER_KEY", "local_audit_dummy_key_2026!")


def run_audit_only(change_desc: str = "baseline") -> dict:
    """Run comprehensive_audit.py and parse results via evaluate.py."""
    start = time.time()

    # Import evaluate module (which imports comprehensive_audit)
    try:
        from evaluate import run_audit, parse_audit_output, append_result, save_audit_result
    except ImportError as e:
        return {"error": f"Import failed: {e}", "overall": -1}

    # Run the audit
    try:
        output = run_audit()
    except Exception as e:
        return {"error": f"Audit failed: {e}", "overall": -1}

    elapsed = time.time() - start

    # Parse scores
    scores = parse_audit_output(output)

    # Save raw output
    save_audit_result(output)

    # Log to TSV
    verdict = "BASELINE" if change_desc == "baseline" else "PENDING"
    append_result(change_desc, scores, elapsed, verdict)

    # Add metadata
    scores["elapsed_sec"] = round(elapsed, 1)
    scores["change_desc"] = change_desc
    scores["raw_output_lines"] = len(output.split("\n"))

    return scores


def run_pipeline_then_audit(change_desc: str = "experiment") -> dict:
    """Apply pipeline fixes, then run audit."""
    start = time.time()

    # Step 1: Apply pipeline fixes
    try:
        from pipeline import apply_all_fixes
        fix_result = apply_all_fixes(dry_run=False)
    except Exception as e:
        return {"error": f"Pipeline apply failed: {e}", "overall": -1}

    # Step 2: Run audit
    try:
        from evaluate import run_audit, parse_audit_output, append_result, save_audit_result
        output = run_audit()
    except Exception as e:
        return {"error": f"Audit failed: {e}", "overall": -1}

    elapsed = time.time() - start
    scores = parse_audit_output(output)
    save_audit_result(output)
    append_result(change_desc, scores, elapsed, "PENDING")

    scores["elapsed_sec"] = round(elapsed, 1)
    scores["change_desc"] = change_desc
    scores["pipeline_result"] = fix_result
    scores["raw_output_lines"] = len(output.split("\n"))

    return scores


if __name__ == "__main__":
    change_desc = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    mode = sys.argv[2] if len(sys.argv) > 2 else "audit_only"

    if mode == "pipeline":
        result = run_pipeline_then_audit(change_desc)
    else:
        result = run_audit_only(change_desc)

    print(json.dumps(result, indent=2, ensure_ascii=False))
