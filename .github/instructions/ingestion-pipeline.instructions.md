---
description: "Use when editing ingestion pipeline stages, orchestrator, models, or the ProductionIngestor. Covers stage signature, ProcessedDocument flow, and identity model."
applyTo: "services/rag-service/ingestion/**/*.py"
---
# Ingestion Pipeline Conventions

## Stage contract
Every stage is a function: `run(doc: ProcessedDocument, ctx) -> ProcessedDocument | None`
- Return `ProcessedDocument` to continue the pipeline
- Return `None` to skip this file (e.g., already processed, invalid)
- Raise `StageError` on failure — orchestrator handles logging and metrics

## Stage order
`s01_intake` → `s02_ocr` → `s03_metadata` → `s04_identity` → `s05_chunking` → `s06_enrichment` → `s07_embedding` → `s08_indexing` → `s09_export`

## Data models (`ingestion/models.py`)
- `DocumentIdentity` — `doc_id`, `doc_number`, `namespace`, `content_hash`
- `DocumentMetadata` — LLM-extracted fields (doc_type, authority, effective_date, etc.)
- `ProcessedDocument` — container carrying identity, metadata, chunks, embeddings through all stages
- All are `@dataclass` (not Pydantic) — keep it lightweight for sync workers

## Identity model
- `doc_id` = `namespace/doc_number` (globally unique)
- `chunk_id` = `doc_id::p{page}::type_idx` (deterministic)
- All 3 fields must be present in Milvus, Neo4j, and PostgreSQL

## Key rules
- Stages are **sync** — workers run in `rag-watcher` process, not async FastAPI
- LLM calls use OpenAI SDK via `ingestion/rag_router.py` → AI Gateway
- Structured LLM output: `response_format={"type": "json_schema", ...}` with Pydantic schema
- **Two `pipeline.py` files**: `ingestion/pipeline.py` = `ProductionIngestor`; root-level `pipeline.py` = export post-processor
- Prometheus metrics: `rag_stage_duration_seconds`, `rag_stage_total` — orchestrator tracks automatically
