---
description: "Run an autoresearch optimization cycle: edit optimize_rag.py, run evaluation, compare against baseline"
agent: "agent"
argument-hint: "Describe the RAG improvement to test (e.g., 'increase chunk overlap to 200 tokens')"
---
Run a Karpathy-style autoresearch optimization cycle on the RAG pipeline.

## Context
- Workspace: `services/rag-service/autoresearch/`
- Editable: `optimize_rag.py` only
- Read-only: `prepare.py` (evaluation), `program.md` (instructions)
- Baseline: `results.tsv`
- Branch naming: `autoresearch/<tag>`

## Steps
1. Read `program.md` for current experiment instructions
2. Read `results.tsv` for baseline scores
3. Apply the requested change to `optimize_rag.py`
4. Run the experiment:
   ```
   cd services/rag-service/autoresearch && python optimize_rag.py
   ```
5. Run evaluation:
   ```
   cd services/rag-service/autoresearch && python prepare.py
   ```
6. Compare new scores against baseline in `results.tsv`
7. Summarize: what changed, score delta, whether to keep or revert
