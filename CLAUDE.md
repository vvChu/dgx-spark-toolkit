# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vietnamese legal document RAG system running on NVIDIA DGX Spark (GB10 Blackwell, 128GB unified memory). Unified AI Gateway routes to local vLLM models and remote cloud proxies (Claude, Gemini, GPT-OSS). Stack: FastAPI backend, React 19 frontend, Milvus vector DB, Neo4j knowledge graph, LiteLLM proxy with 22 unique models (38 route configs including multi-key load balancing).

## Common Commands

### Start/Stop Services
```bash
./scripts/start-all.sh    # Start vLLM + Docker Compose stack
./scripts/stop-all.sh     # Stop all services
```

### Backend Tests (from repo root)
```bash
cd services/rag-service && pytest tests/            # All unit tests
cd services/rag-service && pytest tests/test_config.py  # Single test file
cd services/rag-service && pytest tests/test_config.py::test_name -v  # Single test
```
- `pytest.ini` auto-excludes `integration` and `gpu` markers
- CI uses `requirements-ci.txt` (excludes GPU packages like torch, surya-ocr)
- Tests stub the BGE-M3 embedding module and swap out the lifespan (see `tests/conftest.py`)
- Required env vars for tests: `NEO4J_PASSWORD`, `LITELLM_MASTER_KEY` (conftest sets safe defaults)

### Frontend (from `services/frontend/`)
```bash
npm ci          # Install dependencies
npm run lint    # ESLint
npm run build   # Production build (4GB memory limit)
npm run dev     # Dev server
```

### Python Linting
```bash
flake8 services/rag-service/ --max-line-length=150 --exclude=venv,__pycache__,surya_src
```

### Smoke/Audit (requires running services)
```bash
python3 services/rag-service/scripts/smoke_test.py
python3 services/rag-service/scripts/comprehensive_audit.py
```

## Architecture

```
Frontend(:5173) → RAG Service(:8005) → Milvus + Neo4j + AI Gateway(:8090) → LLM
```

### RAG Service (`services/rag-service/`)
Layered FastAPI app (Python 3.12):
- `api/routers/` → `services/` → `repositories/` → Milvus/Neo4j
- Routers: search, chat, admin, analysis, stats, graph, preview, evaluation
- `core/config.py` — Pydantic Settings with `SecretStr`, model validator rejects weak passwords
- `core/database.py` — Lifespan management + FastAPI `Depends()` DI for all DB clients
- `main.py` — App factory, CORS, Prometheus instrumentation, health endpoints

### Ingestion Pipeline (`services/rag-service/ingestion/`)
9-stage pipeline orchestrated by `orchestrator.py`, stages in `stages/`:
`s01_intake` → `s02_ocr` → `s03_metadata` → `s04_identity` → `s05_chunking` → `s06_enrichment` → `s07_embedding` → `s08_indexing` → `s09_export`

- `pipeline.py` in `ingestion/` = actual `ProductionIngestor` class
- Root-level `pipeline.py` = post-processing export fixer (different file!)
- Workers run as `rag-watcher` (×1 replica) with sync ingestion, consuming from Redis stream `ingest:queue`
- Async reranker wrapped via `asyncio.to_thread()` in `retrieval/reranker.py`

### AI Gateway (`services/ai-gateway/`)
LiteLLM proxy with `litellm_config.yaml` — latency-based routing, Redis semantic cache (0.85 threshold), fallback chains. Port mapping: external `:8090` → container `:4000`. Internal services connect via `http://ai-gateway:4000/v1`.

### Frontend (`services/frontend/`)
React 19 + Vite 7 + Tailwind CSS 4. No test runner — validated via lint + build in CI.

### Databases
| DB | Purpose | Key identifier |
|---|---|---|
| Milvus | Vector search (BGE-M3 dense+sparse) | Collection: `legal_docs_v9` |
| Neo4j | Knowledge graph (REPLACES, AMENDS, REFERENCES) | Document nodes |
| PostgreSQL | Ingestion state + LiteLLM state | Table: `ingestion_state` |
| Redis | DB 0: LiteLLM cache, DB 1: ingestion queue | Stream: `ingest:queue` |

## Key Conventions

- **Identity model**: `doc_id` = `namespace/doc_number`, `chunk_id` = `doc_id::p{page}::type_idx` — all stores use these consistently
- **Python style**: 3.10+ type hints (`list[str]`, `X | None`), Pydantic v2, async-first API layer, max line length 150
- **LLM calls**: OpenAI SDK with `base_url` pointed at AI Gateway — see `ingestion/rag_router.py`
- **Structured LLM output**: `response_format={"type": "json_schema", ...}` with Pydantic schema for metadata extraction
- **Config**: `pydantic-settings` `BaseSettings` with `SecretStr` — never log `.get_secret_value()` output
- **Tests** go in `services/rag-service/tests/` — not as one-off scripts in the rag-service root
- **Operational scripts** go in `services/rag-service/scripts/`
- **Agent skills** in `.agents/skills/` (18 skills + shared), workflows in `.agents/workflows/` (14 workflows)
- **Architecture north star**: `.agents/ARCHITECTURE.md` — canonical identity model, store contracts, and target architecture
- **Benchmarks** in `services/rag-service/benchmarks/` — one benchmark + one locustfile, no versioned copies

## CI (GitHub Actions)

Three jobs on push/PR to `master`:
1. **backend-tests** — Python 3.12, `requirements-ci.txt`, `pytest tests/ -v --timeout=60`
2. **frontend-build** — Node 20, `npm ci && npm run lint && npm run build`
3. **lint** — `flake8` on RAG service with max-line-length=150

## Common Pitfalls

- **Two `pipeline.py` files**: `ingestion/pipeline.py` = actual `ProductionIngestor`; root-level `pipeline.py` = post-processing export fixer — always use full import path
- **GPU packages in CI**: `surya-ocr`, `torch` excluded from `requirements-ci.txt`. Use `FORCE_CPU_EMBEDDING=1`, `FORCE_CPU_RERANKER=1` for CPU fallback
- **Redis DB split**: DB 0 = LiteLLM semantic cache, DB 1 = ingestion queue — never mix
- **Model cache volume**: Mount `model_cache:/app/models` with `HF_HOME=/app/models` or Surya (1.3GB) re-downloads every restart
- **Frontend build OOM**: Requires `--max-old-space-size=4096` (in `package.json` build script)
- **Ingestion stale state**: Jobs stuck in `PROCESSING` if worker crashes (1-hour timeout)
- **Neo4j password alias**: Both `NEO4J_PASSWORD` and `NEO4J_PASS` work via Pydantic `AliasChoices`

## Docker

`docker-compose.yml` orchestrates 13 services on the `rag-network` bridge. Key services: `rag-service` (:8005), `rag-watcher` (×1 replica, ingest profile), `ai-gateway` (:8090), `rag-frontend` (:5173), `milvus-standalone` (:19530), `neo4j` (:7474/:7687), plus Prometheus (:9090) and Grafana (:3000). vLLM containers (`vllm-35b` always-on, `vllm-4b` on-demand via `vllm-light` profile) serve local Qwen 3.5 models with GPU reservations.
