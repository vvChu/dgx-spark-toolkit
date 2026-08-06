# Technical Spec: Deep Ingestion Pipeline Refactoring

## 1. Overview & Goal

Refactor the over-fragmented ingestion architecture in `services/rag-service/ingestion/` into a single, deep `DocumentIngestionPipeline` module behind a clean 2-method public interface.

Consolidate:
- `ProductionIngestor` (`pipeline.py`)
- 5 mixin files (`mixins/extraction.py`, `mixins/metadata.py`, `mixins/indexing.py`, `mixins/graph.py`, `mixins/runner.py`)
- 9 shallow stage files (`stages/s01_intake.py` .. `stages/s09_export.py`)
- `PostgresStateManager` & `AsyncStateManager` (`state_manager.py` & `async_state_manager.py`)

## 2. Target Architecture

### Module Seam (`services/rag-service/ingestion/pipeline.py`)

```python
class DocumentIngestionPipeline:
    def __init__(self, state_manager: StateManager | None = None, settings: Settings | None = None):
        self.state_manager = state_manager or StateManager()
        ...

    async def ingest_file(self, file_path: Path, force_reprocess: bool = False) -> IngestionResult:
        """Main entry point: process a single file through all steps."""

    async def run_worker_loop(self) -> None:
        """Worker entry point: consume from Redis stream queue."""
```

### Internal Step Handlers (Private Methods)

1. `_intake_and_ocr(file_path: Path) -> RawDocument`
2. `_extract_metadata_and_identity(doc: RawDocument) -> EnrichedDocument`
3. `_chunk_and_embed(doc: EnrichedDocument) -> ChunkedDocument`
4. `_index_milvus_and_graph(doc: ChunkedDocument) -> IndexResult`
5. `_export_processed_data(doc: ChunkedDocument) -> Path`

### State Manager Adapter (`services/rag-service/ingestion/state_manager.py`)

Single `StateManager` class supporting async database ops, plus an `InMemoryStateManager` for offline unit testing.

## 3. Execution Plan & Tickets

1. **Ticket 1 (`T-01`)**: Consolidate `state_manager.py` & `async_state_manager.py` into a single async `StateManager` with `InMemoryStateManager` adapter.
2. **Ticket 2 (`T-02`)**: Implement `DocumentIngestionPipeline` in `pipeline.py` incorporating all 9 stage steps as private methods, removing `mixins/` and `stages/`.
3. **Ticket 3 (`T-03`)**: Update caller references (`main.py`, `e2e_test.py`, test scripts) and write comprehensive unit tests using `InMemoryStateManager`.
