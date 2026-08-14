# Code & Engineering Conventions

Key engineering standards, identity models, and programming patterns enforced across the codebase.

## 1. Canonical Identity Model

All database stores, caches, and index pipelines must adhere to the unified document and chunk identification scheme:

- **Document ID (`doc_id`)**: Formatted as `{namespace}/{doc_number}` (e.g., `luat_dat_dai/31_2024_QH15`).
- **Chunk ID (`chunk_id`)**: Formatted as `{doc_id}::p{page}::{type_idx}` (e.g., `luat_dat_dai/31_2024_QH15::p12::art_5_cl_2`).

Never generate arbitrary surrogate IDs for documents or chunks in Milvus or Neo4j.

## 2. Python Standards (RAG Backend)

- **Language Version**: Python 3.10+ syntax required.
- **Type Annotations**: Mandatory type hints for all function parameters and return types (use `list[str]`, `dict[str, Any]`, `str | None`).
- **Data Models**: Use Pydantic v2 exclusively. Sensitive fields must use `SecretStr` and never be directly logged via raw string interpolation.
- **Async Execution**: The FastAPI API layer and retrieval interfaces are async-first. Long-running or CPU-bound synchronous calls (such as local model inference or reranking) must be offloaded via `asyncio.to_thread()`.
- **Formatting**: Max line length is 150 characters.

## 3. LLM & AI Gateway Integration

- **Client Invocation**: Use the official OpenAI Python SDK with `base_url` pointed to the local AI Gateway instance (`http://localhost:8090/v1` or `http://ai-gateway:4000/v1`).
- **Structured Outputs**: For metadata extraction and JSON outputs, enforce Pydantic schemas using `response_format={"type": "json_schema", ...}`.
- **Centralized Routing**: Refer to `services/rag-service/ingestion/rag_router.py` for standard gateway client configuration and retry policies.

## 4. Code Organization & Deep Modules

- Place public utilities behind cohesive, deep module seams (e.g. `DocumentIngestionPipeline`, `TextNormalizer`, `AIGatewayClient`).
- Tests belong in `services/rag-service/tests/`, never as ad-hoc scripts in module roots.
- Operational, data-fix, or audit scripts belong in `services/rag-service/scripts/`.
- Benchmarks belong in `services/rag-service/benchmarks/` with a clean `locustfile.py`.
