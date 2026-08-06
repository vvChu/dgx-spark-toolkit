# T-03: Update Callers & Write Seam Unit Tests

## Status
Open

## Blocking
Blocked by T-02

## Objective
Update callers (`main.py`, worker scripts, `e2e_test.py`, `test_single.py`) to consume `DocumentIngestionPipeline`. Add comprehensive unit tests in `services/rag-service/tests/test_ingestion_pipeline.py` exercising `DocumentIngestionPipeline` through its public seam with `InMemoryStateManager`.

## Verification
- `uv run pytest tests/` passes 100%.
- Callers operate cleanly against the 2-method seam.
