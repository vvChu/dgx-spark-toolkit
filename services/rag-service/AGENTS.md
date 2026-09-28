# RAG Service (services/rag-service)

Layered FastAPI backend providing Vietnamese legal document ingestion, hybrid vector/graph retrieval, and domain compliance verification.

## Quick Commands
- **Unit Tests**: `cd services/rag-service && pytest tests/ -q -m 'not integration and not gpu'`
- **Single Test**: `pytest tests/test_warmup.py -v`
- **Lint**: `flake8 services/rag-service/ --config=services/rag-service/.flake8`

## Deep Seams & Topology
- **Ingestion Pipeline**: [`ingestion/pipeline.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py) (`DocumentIngestionPipeline.run_pipeline`) — 9-stage intake, OCR, metadata, identity, chunking, enrichment, embedding, indexing, export.
- **Search Pipeline**: [`retrieval/search_pipeline.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py) (`SearchPipeline.execute`) — Cache, intent classification, hybrid BGE-M3 Milvus search, BGE reranker, and Neo4j timeline enrichment.
- **Storage & Repositories**: [`repositories/document_store.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/document_store.py) — Atomic coordination between Milvus, Neo4j, and PostgreSQL.
- **API Routers**: [`api/routers/`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/api/routers/) — HTTP endpoints (`search.py`, `chat.py`, `preview.py`, `stats.py`, `graph.py`).

## Core Invariants
- **Identity Model**: `doc_id` is uppercase canonical (e.g., `01/2021/TT-BXD`). Chunks are identified via `chunk_id` (`{doc_id}#{strategy}:{hash}`).
- **Redis Partitioning**: DB 0: LiteLLM, DB 1: Ingestion Queue, DB 2: Context Lake, DB 3: Semantic Cache & Tier 0, DB 4: HITL Review.
- **Zero-Regression**: Never change Milvus collection schema (`legal_docs_v11`) without explicit ADR migration.
