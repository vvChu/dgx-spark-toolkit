---
name: rag-local-python-runner
description: "Runs pipeline.py + comprehensive_audit.py + evaluate.py directly on host Python and returns full JSON scorecard for the Vietnamese legal RAG pipeline."
---

# RAG Local Python Runner

This skill runs the autoresearch evaluation loop locally (no Docker needed).

## How it works

1. Sets environment variables to point at local export directories
2. Optionally applies pipeline fixes via `pipeline.py`
3. Runs `comprehensive_audit.py` to score exports
4. Parses output via `evaluate.py` into structured JSON
5. Logs results to `results.tsv`

## Usage

Run the script at `.agent/skills/rag-local-python-runner/scripts/run.py`:

```bash
cd /home/vvc/Codebase/dgx-spark-toolkit
python3 .agent/skills/rag-local-python-runner/scripts/run.py [change_description]
```

### Arguments

- `change_description` (optional): Label for this experiment (default: "baseline")

### Environment

The script auto-sets these env vars:
- `EXPORT_JSON_DIR=/home/vvc/Public/exports/json`
- `EXPORT_MD_DIR=/home/vvc/Public/exports/markdown`
- `PDF_SOURCE_DIR=/home/vvc/Public/exports`
- `MILVUS_HOST=100.83.192.30`
- `MILVUS_PORT=19530`

### Output

- Stdout: JSON scorecard with `overall`, dimension scores, and P-issue statuses
- Side effects: Appends to `services/rag-service/results.tsv`, saves audit to `services/rag-service/audit_results/latest.md`

## Typical autoresearch workflow

```
1. Edit pipeline.py with one small change
2. Run this skill to get new scores
3. If improved → KEEP; else → REVERT pipeline.py
4. Repeat
```
