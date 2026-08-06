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
- Routers: `search`, `chat`, `chat_stream` (SSE), `admin`, `analysis` (conflict/compliance), `evaluation`, `graph`, `preview`, `stats`, `traces`
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

### Retrieval Layer (`services/rag-service/retrieval/`)
HyDE, query rewriting, agentic retrieval, graph-timeline retrieval, async reranker (via `asyncio.to_thread()`), semantic cache, session memory.

### Frontend (`services/frontend/`)
React 19 + Vite 7 + Tailwind CSS 4. API client: `src/lib/api.ts` (blocking) + `src/lib/streamApi.ts` (SSE). Graph viz via `react-force-graph`, Markdown via `react-markdown` + `remark-gfm`. No test runner — validated via lint + build in CI.

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
- **Operational scripts** go in `services/rag-service/scripts/` (23+ scripts: audits, migrations, evals, OCR benchmarks, data integrity repairs)
- **Agent skills** in `.agents/skills/` (18 skills + shared), workflows in `.agents/workflows/` (14 workflows including `start-all-128k`, `vllm-32k`, `health`, `track-ingestion`)
- **Architecture north star**: `.agents/ARCHITECTURE.md` — canonical identity model, store contracts, and target architecture
- **Benchmarks** in `services/rag-service/benchmarks/` — one benchmark + one locustfile, no versioned copies
- **Autoresearch** (`services/rag-service/autoresearch/`): Karpathy-style autonomous RAG optimization playground. Edit only `optimize_rag.py`; `prepare.py` and `program.md` are read-only. Branch naming: `autoresearch/<tag>`
- **vLLM backports** (`vllm_backport/`): Custom Qwen3 model implementations (MoE, VL, VL-MoE) for DGX Blackwell compatibility
- **Monitoring**: Prometheus + Grafana dashboards in `monitoring/` — vLLM, RAG, and ingestion dashboards with alert rules

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

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `NEO4J_PASSWORD` / `NEO4J_PASS` | Neo4j auth (AliasChoices) |
| `LITELLM_MASTER_KEY` | AI Gateway auth |
| `VITE_API_URL` | Frontend → backend base URL |
| `QWEN35B_SNAPSHOT`, `QWEN35B_MODEL_DIR` | vLLM model path/version |
| `PRIMARY_VISION_MODEL`, `FALLBACK_VISION_MODEL` | Vision model routing |
| `FORCE_CPU_EMBEDDING=1`, `FORCE_CPU_RERANKER=1` | CPU fallback for CI/dev |
| `HF_HOME=/app/models` | Hugging Face cache mount |

## Docker

`docker-compose.yml` orchestrates 15+ services on the `rag-network` bridge.

### Docker profiles
| Profile | Services | Purpose |
|---|---|---|
| *(default)* | rag-service, ai-gateway, milvus, neo4j, postgres, redis, prometheus, grafana | Core stack |
| `ingest` | rag-watcher (×1) | Ingestion workers |
| `vllm-light` | vllm-4b | On-demand small model |
| `loadtest` | locust (:8089) | Performance testing |

### Deployment targets
- **Docker Compose** (`docker-compose.yml`) — primary
- **Helm** (`helm/dgx-spark-toolkit/`) — Kubernetes deployment with HPA, Nginx ingress (`rag.dgxspark.local`)

### vLLM models
- `vllm-35b` (Qwen3.5-35B, always-on, 96GB, 32k ctx)
- `vllm-4b` (Qwen3.5-9B AWQ, on-demand via `vllm-light` profile, 12GB, 8k ctx)

## Agent skills

### Issue tracker

Issues and specs for this repo live as GitHub issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The label vocabulary maps canonical roles to GitHub issue labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo layout (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.

