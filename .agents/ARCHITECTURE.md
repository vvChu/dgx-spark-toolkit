# RAG System — Architecture North Star

> This file is the **single source of truth** for the RAG system's target architecture.
> All agents and developers should reference this when making design decisions.

## Current State (v10 — March 2026)

### Identity Model (✅ Implemented)
- **doc_id**: `namespace/doc_number` — globally unique, scoped (e.g. `Linh_vuc_BTP/01/2023/TT-BTP`)
- **doc_number**: raw legal number (e.g. `01/2023/TT-BTP`)
- **chunk_id**: deterministic `doc_id::p{page}::{type}_{idx}`
- All 3 fields present in **every** store (Milvus, Neo4j, PostgreSQL)

### Store Contract
| Store | Primary Key | doc_id | doc_number | chunk_id |
|---|---|---|---|---|
| **Milvus** | auto_id | ✅ INVERTED idx | ✅ INVERTED idx | ✅ |
| **Neo4j** | Document.id | ✅ (= id) | ✅ property | — |
| **PostgreSQL** | file_path | ✅ indexed | via JSONB | — |

### Pipeline: `pipeline.py` (monolith — to be split)
- OCR → LLM metadata → Chunking → Central Identity → Enrichment → Embedding → Indexing → Export

---

## Target Architecture (North Star)

### Principle 1: Pipeline as Stages
Split `pipeline.py` into `ingestion/stages/01_intake.py` through `09_export.py`.
Each stage: `ProcessedDocument → ProcessedDocument`.

### Principle 2: Pydantic Models
All data flows through typed `ProcessedDocument`, `Chunk`, `DocumentIdentity` models.
No more `dict` with optional keys.

### Principle 3: Task Queue (Redis Streams)
Replace filesystem polling with `redis.xadd()` / `xreadgroup()`.
Atomic claim, no race conditions between workers.

### Principle 4: Full Async
`asyncpg` + `httpx.AsyncClient` + async Milvus. No sync blocking in the event loop.

### Principle 5: Model Cache Volume
Docker volume `model_cache:/app/models` + `HF_HOME=/app/models`.
No re-download of 1.3GB Surya OCR on every restart.

### Principle 6: Idempotent Re-ingestion
Content-hash comparison before processing. Never TRUNCATE — upsert by doc_id + hash.

### Principle 7: Observable Pipeline
Structured `PipelineEvent` objects → Prometheus metrics + Grafana dashboards.

### Principle 8: Schema Migration
Alembic-style versioned migrations for Milvus schema. No drop-and-recreate.

---

## Evolution Priority
1. ✅ Identity Architecture (v10)
2. ✅ PostgreSQL Performance (indexes, engine.begin())
3. ✅ Split pipeline.py → stages (9 stages + orchestrator)
4. ✅ Model cache Docker volume
5. ✅ Redis task queue (Redis Streams on DB 1)
6. ✅ Async database (asyncpg + /health/pipeline endpoint)
7. ✅ Prometheus stage metrics (rag_stage_duration_seconds, rag_stage_total)
