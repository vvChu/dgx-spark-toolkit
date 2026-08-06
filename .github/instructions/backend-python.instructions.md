---
description: "Use when editing Python backend code in the RAG service: FastAPI routers, services, repositories, ingestion stages, retrieval modules, config, models."
applyTo: "services/rag-service/**/*.py"
---
# Backend Python Conventions

## Architecture layers
`api/routers/` → `services/` → `repositories/` → Milvus/Neo4j. Never skip layers; routers call services, services call repositories.

## Patterns

### Routers
- One `APIRouter()` per file, mounted in `main.py`
- Use `Depends(get_X_service)` for DI — see `core/database.py` for dependency functions
- Always type request/response with Pydantic v2 models from `models/schemas.py`
- Async handlers (`async def`) for all API endpoints

### Config
- All settings in `core/config.py` via `pydantic-settings` `BaseSettings`
- Secrets must use `SecretStr` — never log `.get_secret_value()` output
- Use `AliasChoices` for env var aliases (see `NEO4J_PASSWORD` pattern)
- Access via `get_settings()` (cached with `@lru_cache`)

### Async vs Sync
- API layer: **always async** (FastAPI + `httpx.AsyncClient`)
- Ingestion workers: **sync** (run in `rag-watcher` process)
- Sync-heavy code in async context: wrap via `asyncio.to_thread()` (see `retrieval/reranker.py`)

### LLM calls
- Always use OpenAI SDK with `base_url` pointed at AI Gateway (`http://ai-gateway:4000/v1`)
- For structured output: `response_format={"type": "json_schema", ...}` with Pydantic schema
- Route through `ingestion/rag_router.py` — never call vLLM directly

### Type hints
- Python 3.10+ style: `list[str]`, `dict[str, Any]`, `X | None` (not `Optional[X]`)
- Pydantic v2 models for all schemas — use `model_validator`, `field_validator`

### Testing
- Tests in `services/rag-service/tests/` — NOT as scripts in rag-service root
- `conftest.py` stubs BGE-M3 embedding + swaps lifespan
- Use existing mock fixtures: `mock_milvus_repo`, `mock_neo4j_repo`, etc.
- Mark GPU/integration tests: `@pytest.mark.gpu`, `@pytest.mark.integration` (auto-excluded)

## Max line length
**150 characters** — enforced by flake8 in CI.
