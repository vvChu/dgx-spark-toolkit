# Domain Context & Glossary

Ubiquitous language and domain model definitions for the `dgx-spark-toolkit` Vietnamese Legal Document RAG System.

## Ingestion Domain

### `DocumentIngestionPipeline`
The single, deep entry-point module responsible for orchestrating the complete document processing pipeline: file intake, OCR text extraction, legal metadata parsing, identity normalization, structured chunking, BGE-M3 embedding, vector/graph indexing, and document export.

### `IngestionState`
The status lifecycle of a document within the processing queue and state database:
- `PENDING`: Enqueued in Redis/Database, awaiting worker claim.
- `CLAIMED`: Claimed by a worker process.
- `PROCESSING`: Active extraction/embedding/indexing in progress.
- `COMPLETED`: Successfully ingested into Milvus and Neo4j.
- `FAILED`: Ingestion halted due to unrecoverable error.

### `IngestionResult`
The structured output returned after running `DocumentIngestionPipeline.ingest_file()`, containing document metadata, page counts, chunk metrics, index status, and execution duration.

### `StateManager`
The database adapter responsible for persisting and querying `IngestionState` across processing workers. Supports both production PostgreSQL storage and an in-memory test adapter for offline unit testing.

## AI Gateway & LLM Domain

### `AIGatewayClient`
The single, deep client module providing unified access to all AI Gateway models (LLM text completions, JSON structured extractions, and Vision OCR). Encapsulates model fallback chains, rate-limit retries, circuit breakers, and markdown-fence JSON parsing behind a clean seam.

### `MockAIGatewayClient`
An in-memory test adapter for `AIGatewayClient` allowing fast, deterministic unit testing of LLM-dependent services without requiring external network calls.

## Retrieval & Search Domain

### `SearchPipeline`
The deep execution module for legal search, encapsulating query intent classification, semantic caching, query rewriting, HyDE generation, Milvus hybrid vector search, BGE reranking, Neo4j document validity status checks, and Graph RAG timeline enrichment behind a single seam.

### `SearchContext`
The type-safe state container passed across `SearchPipeline` stages, encapsulating raw query parameters, generated embeddings, candidate hits, reranked results, and execution traces.

## Frontend Stream Domain

### `StreamClient`
The deep client module managing Server-Sent Events (SSE) streaming connections (`POST /chat/stream`), providing automatic reconnection, buffer decoding, discriminated union event parsing, and transparent fallback to REST API.



