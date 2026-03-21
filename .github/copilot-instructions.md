# Project Guidelines — DGX Spark Toolkit

Vietnamese legal document RAG system on NVIDIA DGX Spark (GB10 Blackwell, 128GB unified memory).

## Architecture

```
Frontend(:5173) → RAG Service(:8005) → Milvus + Neo4j + AI Gateway(:8090) → LLM
```

- **RAG Service** (`services/rag-service/`): FastAPI app with layered architecture — `api/routers/` → `services/` → `repositories/` → Milvus/Neo4j
- **Ingestion Workers** (`rag-watcher` ×3): 9-stage pipeline in `ingestion/` — intake → OCR → metadata → identity → chunking → enrichment → embedding → indexing → export
- **AI Gateway** (`services/ai-gateway/`): LiteLLM proxy routing to local Qwen 3.5 models + cloud fallbacks
- **Frontend** (`services/frontend/`): React 19 + Vite + Tailwind

### Key databases
| DB | Purpose | Collection/Label |
|---|---|---|
| Milvus | Vector search (BGE-M3 dense+sparse) | `legal_docs_v9` |
| Neo4j | Knowledge graph (REPLACES, AMENDS, REFERENCES) | Document nodes |
| PostgreSQL | Ingestion state + LiteLLM state | `ingestion_state` table |
| Redis | DB 0: LiteLLM cache, DB 1: ingestion queue | `ingest:queue` stream |

## Code Style

- **Python 3.10+**, type hints encouraged (`list[str]`, `X | None`), Pydantic v2 models for schemas
- **Async-first** API layer (FastAPI + `httpx.AsyncClient`), sync ingestion workers
- Sync reranker wrapped via `asyncio.to_thread()` — see `reranker.py`
- Config via `pydantic-settings` `BaseSettings` with `SecretStr` — see `core/config.py`
- FastAPI `Depends()` for DI — see `core/database.py` lifespan + dependency functions
- OpenAI SDK with `base_url` pointed at gateway for all LLM calls — see `ingestion/rag_router.py`

## Build and Test

```bash
# Start everything (vLLM + docker compose)
./scripts/start-all.sh

# Stop everything
./scripts/stop-all.sh

# Run tests (from services/rag-service/)
cd services/rag-service && pytest tests/

# Lint
flake8 services/rag-service/

# Smoke test (requires running services)
python3 services/rag-service/scripts/smoke_test.py

# RAG quality audit
python3 services/rag-service/scripts/comprehensive_audit.py
```

## Project Conventions

- **Identity model**: `doc_id` = `namespace/doc_number`, `chunk_id` = `doc_id::p{page}::type_idx` — all stores use these consistently
- **Two `pipeline.py` files**: root-level = post-processing export fixer; `ingestion/pipeline.py` = actual ingestion pipeline (1400+ lines `ProductionIngestor` class)
- **Structured LLM output**: Use `response_format={"type": "json_schema", ...}` with Pydantic schema for metadata extraction
- **Operational scripts** live in `services/rag-service/scripts/` — audits, migrations, evals
- **Proper tests** live in `services/rag-service/tests/` — do NOT add one-off test scripts to rag-service root
- **Agent skills** live in `.agents/skills/`, workflows in `.agents/workflows/`
- **Benchmarks** in `services/rag-service/benchmarks/` — one benchmark + one locustfile, no versioned copies

## Security

- Secrets via `SecretStr` in `core/config.py` — never log `.get_secret_value()` output
- `@model_validator` rejects empty/weak passwords at startup
- AI Gateway master key in `LITELLM_MASTER_KEY` env var
- Neo4j password, Telegram bot token also as `SecretStr`
