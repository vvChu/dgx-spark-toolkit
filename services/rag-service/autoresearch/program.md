# autoresearch — RAG Pipeline Optimization

This is an experiment to have an AI Agent autonomously optimize a RAG (Retrieval-Augmented Generation) pipeline for Vietnamese legal documents. Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar21`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The autoresearch directory is small. Read these files for full context:
   - `program.md` — this file (agent instructions). Do not modify.
   - `prepare.py` — fixed evaluation metrics, data loading, and scoring. **Do not modify.**
   - `optimize_rag.py` — the file you modify. Contains the full RAG pipeline: extraction, cleaning, chunking, export.
4. **Understand the RAG service**: Skim these files for context on the production pipeline:
   - `../ingestion/chunking.py` — current chunking strategies (VietLawArticleChunker, etc.)
   - `../ingestion/exporter.py` — current export logic (JSON + Markdown)
   - `../ingestion/vision.py` — OCR via Cloud Vision / vLLM
   - `../scripts/comprehensive_audit.py` — the 5-dimension scoring system
5. **Verify data exists**: Check that source PDFs exist:
   - `/home/vvc/Public/QCVN/` — QCVN standards
   - `/home/vvc/Public/VB phap quy/` — Legal documents
6. **Initialize results.tsv**: If `results.tsv` is empty or missing, create it with just the header row. The baseline will be recorded after the first run.
7. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs the optimize_rag.py pipeline on the sample PDFs, then evaluates the output using the 5-dimension audit. You launch it simply as:

```bash
cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/autoresearch
python3 optimize_rag.py > run.log 2>&1
```

Then evaluate:

```bash
python3 prepare.py evaluate > eval.log 2>&1
```

**What you CAN do:**
- Modify `optimize_rag.py` — this is the only file you edit. Everything is fair game: extraction method, cleaning logic, chunking strategy, chunk sizes, child/parent ratios, table detection, boilerplate removal, metadata enrichment, export format.
- Import and reuse modules from `../ingestion/` (chunking, vision, exporter, etc.) or create entirely new logic.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the evaluation metrics.
- Modify `program.md`. It is read-only.
- Modify files in `../ingestion/`, `../scripts/`, or any production code.
- Install new packages or add dependencies beyond what's in `requirements.txt`.
- Modify the evaluation harness. The scoring in `prepare.py` is the ground truth metric.

**The goal is simple: get the highest `overall_score`.**

The `overall_score` is the average of 5 dimensions (each 0-100):
- **A: Markdown Quality** — H1 headings, GFM tables, no AI leakage, no boilerplate
- **B: JSON Export Quality** — All required fields, valid doc_id, chunk fields complete
- **C: Chunking Quality** — Child/Parent ratio ≥1.5, Article strategy ≥30%, no noise chunks (<100 chars), no duplicates
- **D: Milvus Ingestion** — Text length, no fragmentation, table detection, metadata, no AI leakage
- **E: PDF→MD Fidelity** — Coverage, chunk count, text length, table detection

**Export Rule**: Every document processed must be exported as:
- `/home/vvc/Public/exports/json/<doc_id>.json`
- `/home/vvc/Public/exports/markdown/<doc_id>.md`

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. A 0.001 improvement from deleting code? Definitely keep.

**The first run**: Your very first run should always be to establish the baseline. Run the pipeline as-is without changes.

## Output format

After evaluation, `prepare.py evaluate` prints:

```
==================================================
  OVERALL: 74/100  (45.2s)
  A_markdown: 57/100
  B_json: 97/100
  C_chunking: 65/100
  D_milvus: 75/100
  E_fidelity: 80/100
==================================================
```

You can extract the key metric:

```bash
grep "OVERALL:" eval.log
```

## Logging results

When an experiment is done, it is automatically logged to `results.tsv` (tab-separated).

The TSV has a header row and 9 columns:

```
commit	overall_score	A	B	C	D	E	status	description
```

1. git commit hash (short, 7 chars)
2. overall_score (0-100)
3. A_markdown score, B_json, C_chunking, D_milvus, E_fidelity
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

Example:

```
commit	overall_score	A	B	C	D	E	status	description
a1b2c3d	74	57	97	65	75	80	keep	baseline
b2c3d4e	78	65	97	70	75	82	keep	improved boilerplate stripping
c3d4e5f	72	60	90	65	75	70	discard	aggressive table detection (broke B_json)
d4e5f6g	0	0	0	0	0	0	crash	OOM on large PDF batch
```

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar21`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Look at past results in `results.tsv` — what worked, what didn't
3. Tune `optimize_rag.py` with an experimental idea by directly hacking the code
4. git commit
5. Run the pipeline: `python3 optimize_rag.py > run.log 2>&1`
6. Evaluate: `python3 prepare.py evaluate > eval.log 2>&1`
7. Read out the results: `grep "OVERALL:\|A_markdown:\|B_json:\|C_chunking:" eval.log`
8. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace and attempt a fix.
9. Record the results in the TSV (NOTE: do not commit `results.tsv`, leave it untracked by git)
10. If `overall_score` improved (higher), you "advance" the branch, keeping the git commit
11. If `overall_score` is equal or worse, you `git reset --hard` back to where you started

The idea is that you are a completely autonomous researcher trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate.

**Things to try** (non-exhaustive, just ideas to get you started):
- Improve the Article chunker regex to catch more Điều variants
- Change `min_child_length` in sentence splitting (200, 300, 400, 500)
- Add or improve table detection heuristics
- Improve boilerplate/noise stripping patterns
- Change parent chunk size caps (currently 14500)
- Better doc_number extraction from filenames
- Improve the preamble detection logic
- Better handling of scanned vs digital PDFs
- Improve synthetic query generation coverage
- Try different strategies for documents without Điều patterns

**Timeout**: Each pipeline run should take at most 10 minutes. If a run exceeds 10 minutes, kill it and treat it as a failure.

**Crashes**: If a run crashes, use your judgment: If it's something easy to fix (typo, missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it.

**NEVER STOP**: Once the experiment loop has begun, do NOT pause to ask the human if you should continue. The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. If you run out of ideas, think harder — re-read the audit output for new angles, try combining previous near-misses, try more radical changes. The loop runs until the human interrupts you, period.
