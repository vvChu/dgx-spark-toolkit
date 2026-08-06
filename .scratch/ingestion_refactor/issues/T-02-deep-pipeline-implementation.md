# T-02: Implement Deep DocumentIngestionPipeline & Remove Mixins/Stages

## Status
Open

## Blocking
Blocked by T-01

## Objective
Implement `DocumentIngestionPipeline` inside `services/rag-service/ingestion/pipeline.py`. Incorporate logic from the 5 mixin files (`mixins/*.py`), 9 stage files (`stages/s01..s09.py`), and `orchestrator.py` as private step handlers inside `DocumentIngestionPipeline`. Delete `mixins/` directory, `stages/` directory, and `orchestrator.py`.

## Public Interface
- `async def ingest_file(file_path: Path, force_reprocess: bool = False) -> IngestionResult`
- `async def run_worker_loop(self) -> None`

## Verification
- File ingestion succeeds end-to-end.
- Deletion test verified: 14 pass-through files removed, logic consolidated cleanly inside `pipeline.py`.
