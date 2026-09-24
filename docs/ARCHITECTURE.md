# Architecture & Services

Overview of the system architecture, services topology, data pipelines, and infrastructure orchestration for the Vietnamese Legal Document RAG System.

## High-Level Topology

```
Frontend (:5173) ──> RAG Service (:8005) ──┬──> Milvus (Vector Search :19530)
                                           ├──> Neo4j (Knowledge Graph :7474, :7687)
                                           ├──> PostgreSQL (State & Metadata :5432)
                                           ├──> Redis (Cache & Ingestion Queue :6379)
                                           └──> AI Gateway (:8090 / :4000) ──> vLLM / Cloud LLMs
```

## Core Services

### 1. RAG Service (`services/rag-service/`)
Layered FastAPI application running on Python 3.12:
- `api/routers/`: HTTP & SSE endpoints (`search`, `chat`, `chat_stream`, `admin`, `analysis`, `evaluation`, `graph`, `preview`, `stats`, `traces`).
- `services/`: Business logic for retrieval orchestration, document processing, and compliance checking.
- `retrieval/`: Multi-stage search engine (HyDE, query rewriting, agentic retrieval, graph-timeline enrichment, async BGE reranker).
- `core/config.py`: Pydantic Settings with `SecretStr` authentication enforcement.
- `core/database.py`: Lifespan management and dependency injection for all database clients.

### 2. Ingestion Pipeline (`services/rag-service/ingestion/`)
A 9-stage pipeline consolidated in `pipeline.py` (orchestrated by `DocumentIngestionPipeline`):
1. `s01_intake`: File validation, hash deduplication, and initial registration.
2. `s02_ocr`: PDF text and bounding-box extraction via Surya OCR or PyMuPDF.
3. `s03_metadata`: Legal metadata extraction (issuing authority, date, type, signer).
4. `s04_identity`: Canonical document and chunk identity normalization (`doc_id`, `chunk_id`).
5. `s05_chunking`: Structure-aware legal chunking (Articles, Clauses, Points).
6. `s06_enrichment`: Cross-reference linking and legal hierarchy resolution.
7. `s07_embedding`: Dense & sparse vector embeddings via BGE-M3.
8. `s08_indexing`: Synchronized indexing into Milvus collections and Neo4j graph nodes.
9. `s09_export`: Final document export artifact and status finalization.

- **Workers**: Run as `rag-watcher` consuming tasks from Redis stream `ingest:queue`.
- **Pipeline Implementation**: `services/rag-service/ingestion/pipeline.py` contains `DocumentIngestionPipeline` (aliased as `ProductionIngestor` for backward compatibility).

### 3. AI Gateway (`services/ai-gateway/`)
LiteLLM proxy instance configured via `litellm_config.yaml`:
- External port `:8090` mapped to container internal port `:4000`.
- Latency-based routing, Redis semantic caching (0.85 threshold), and automated fallback chains.
- Routes across local vLLM models (Qwen 35B / 9B AWQ) and remote proxies (Claude, Gemini, GPT-OSS).

### 4. Frontend (`services/frontend/`)
Single-page application built with React 19, Vite 7, and Tailwind CSS 4:
- API integration: `src/lib/api.ts` (REST) and `src/lib/streamClient.ts` (SSE).
- Graph visualization: `react-force-graph-2d`.
- Markdown rendering: `react-markdown` + `remark-gfm`.

## Databases & Persistence

| Database | Primary Purpose | Identifier / Namespace |
|---|---|---|
| **Milvus** | Hybrid vector search (dense + sparse BGE-M3) | Collection: `legal_docs_v11` |
| **Neo4j** | Knowledge graph relationships (`REPLACES`, `AMENDS`, `REFERENCES`, `GUIDES`) | Document nodes |
| **PostgreSQL** | Ingestion state tracking & LiteLLM state | Table: `ingestion_state` |
| **Redis** | DB 0: LiteLLM cache, DB 1: Ingestion queue, DB 2: Context Lake, DB 3: SemanticCache L2, DB 4: HITL review queue | Stream: `ingest:queue` (DB 1) |

## Infrastructure & Docker

### Docker Compose Profiles (`docker-compose.yml`)
- `(default)`: Core stack (`rag-service`, `ai-gateway`, `milvus`, `neo4j`, `postgres`, `redis`, `prometheus`, `grafana`).
- `ingest`: `rag-watcher` worker replica for document processing queue.
- `vllm-light`: `vllm-4b` on-demand model container.
- `loadtest`: `locust` load testing container at `:8089`.

### vLLM Model Containers
- `vllm-36b`: Qwen3.5-35B-FP8 (always-on, 78GB memory limit, 96k context).
- `vllm-4b`: Qwen3.5-9B AWQ (on-demand via `vllm-light` profile, 12GB memory, 8k context).

### Alternative Deployment Targets
- **Helm**: Kubernetes charts located in `helm/dgx-spark-toolkit/` with HPA and Nginx ingress (`rag.dgxspark.local`).
- **Monitoring**: Prometheus + Grafana dashboards located in `monitoring/`.
