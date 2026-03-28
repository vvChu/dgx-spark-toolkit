# Project Guidelines — DGX Spark Toolkit

Vietnamese legal document RAG system on NVIDIA DGX Spark (GB10 Blackwell, 128GB unified memory).

> **Architecture north star**: `.agents/ARCHITECTURE.md` — canonical identity model, store contracts, and target architecture.

## Architecture

```
Frontend(:5173) → RAG Service(:8005) → Milvus + Neo4j + AI Gateway(:8090) → LLM
```

- **RAG Service** (`services/rag-service/`): Layered FastAPI app — `api/routers/` → `services/` → `repositories/` → Milvus/Neo4j
- **Ingestion Workers** (`rag-watcher` ×3): 9-stage pipeline in `ingestion/stages/` orchestrated by `ingestion/orchestrator.py`
- **AI Gateway** (`services/ai-gateway/`): LiteLLM proxy routing to local Qwen 3.5 models + cloud fallbacks. External `:8090` → container `:4000`; internal: `http://ai-gateway:4000/v1`
- **Frontend** (`services/frontend/`): React 19 + Vite 7 + Tailwind CSS 4 (TypeScript)

### Key databases
| DB | Purpose | Collection/Label |
|---|---|---|
| Milvus | Vector search (BGE-M3 dense+sparse) | `legal_docs_v9` |
| Neo4j | Knowledge graph (REPLACES, AMENDS, REFERENCES) | Document nodes |
| PostgreSQL | Ingestion state + LiteLLM state | `ingestion_state` table |
| Redis | DB 0: LiteLLM cache, DB 1: ingestion queue | `ingest:queue` stream |

## Code Style

### Backend (Python)
- **Python 3.10+**, type hints encouraged (`list[str]`, `X | None`), Pydantic v2 models for schemas, max line length **150**
- **Async-first** API layer (FastAPI + `httpx.AsyncClient`), sync ingestion workers
- Sync reranker wrapped via `asyncio.to_thread()` — see `retrieval/reranker.py`
- Config via `pydantic-settings` `BaseSettings` with `SecretStr` — see `core/config.py`
- FastAPI `Depends()` for DI — see `core/database.py` lifespan + dependency functions
- OpenAI SDK with `base_url` pointed at gateway for all LLM calls — see `ingestion/rag_router.py`

### Frontend (TypeScript/React)
- **React 19** with hooks-based architecture — custom hooks in `src/hooks/` (`useChat`, `useCompliance`, `useDashboard`, etc.)
- **Streaming first**: SSE for chat responses, HTTP POST fallback
- Components in `src/components/`, reusable atoms in `src/components/ui/`
- **Tailwind CSS 4** (utility-first, no component library)
- API client via `axios` in `src/lib/`
- **No test runner** — validated via lint + build in CI

## Build and Test

```bash
# Start everything (vLLM + docker compose)
./scripts/start-all.sh

# Stop everything
./scripts/stop-all.sh

# Run tests (from services/rag-service/)
cd services/rag-service && pytest tests/

# Lint (Python)
flake8 services/rag-service/ --max-line-length=150 --exclude=venv,__pycache__,surya_src

# Lint + build (Frontend)
cd services/frontend && npm ci && npm run lint && npm run build

# Smoke test (requires running services)
python3 services/rag-service/scripts/smoke_test.py

# RAG quality audit
python3 services/rag-service/scripts/comprehensive_audit.py
```

### Testing details
- `pytest.ini` auto-excludes `integration` and `gpu` markers
- CI uses `requirements-ci.txt` (excludes GPU packages: torch, surya-ocr)
- `tests/conftest.py` stubs BGE-M3 embedding module + swaps out lifespan, provides mock fixtures (`mock_milvus_repo`, `mock_neo4j_repo`, etc.)
- Required env vars: `NEO4J_PASSWORD`, `LITELLM_MASTER_KEY` (conftest sets safe defaults)

## CI (GitHub Actions)

Three parallel jobs on push/PR to `master`:
1. **backend-tests** — Python 3.12, `requirements-ci.txt`, `pytest tests/ -v --timeout=60`
2. **frontend-build** — Node 20, `npm ci && npm run lint && npm run build`
3. **lint** — `flake8` on RAG service with max-line-length=150

## Project Conventions

- **Identity model**: `doc_id` = `namespace/doc_number`, `chunk_id` = `doc_id::p{page}::type_idx` — all stores use these consistently
- **Two `pipeline.py` files**: root-level `export_postprocessor.py`/`pipeline.py` = post-processing export fixer; `ingestion/pipeline.py` = actual ingestion pipeline (`ProductionIngestor` class)
- **Structured LLM output**: Use `response_format={"type": "json_schema", ...}` with Pydantic schema for metadata extraction
- **Operational scripts** live in `services/rag-service/scripts/` — audits, migrations, evals
- **Proper tests** live in `services/rag-service/tests/` — do NOT add one-off test scripts to rag-service root
- **Agent skills** live in `.agents/skills/`, workflows in `.agents/workflows/`
- **Benchmarks** in `services/rag-service/benchmarks/` — one benchmark + one locustfile, no versioned copies

## Common Pitfalls

- **GPU packages in CI**: `surya-ocr`, `torch` are excluded from `requirements-ci.txt`. Use `FORCE_CPU_EMBEDDING=1` and `FORCE_CPU_RERANKER=1` for CPU fallback
- **Redis DB split**: DB 0 = LiteLLM semantic cache, DB 1 = ingestion queue — never mix
- **Model cache volume**: Mount `model_cache:/app/models` with `HF_HOME=/app/models` or Surya (1.3GB) re-downloads on every restart
- **Frontend build OOM**: Requires `--max-old-space-size=4096` (already in `package.json` build script)
- **Ingestion stale state**: Jobs stuck in `PROCESSING` if worker crashes (1-hour timeout threshold)
- **Neo4j password alias**: Both `NEO4J_PASSWORD` and legacy `NEO4J_PASS` work via Pydantic `AliasChoices`

## Security

- Secrets via `SecretStr` in `core/config.py` — never log `.get_secret_value()` output
- `@model_validator` rejects empty/weak passwords at startup
- AI Gateway master key in `LITELLM_MASTER_KEY` env var
- Neo4j password, Telegram bot token also as `SecretStr`
