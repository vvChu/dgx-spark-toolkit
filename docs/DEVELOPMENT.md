# Development, Testing & CI

Guidelines and commands for running tests, linting, continuous integration, and managing environment configurations across services.

## Testing & Validation

### Backend Tests (Python / FastAPI)
Run from repository root:
```bash
# Run all unit tests
cd services/rag-service && pytest tests/

# Run a specific test file
cd services/rag-service && pytest tests/test_config.py

# Run a specific test function with verbose output
cd services/rag-service && pytest tests/test_config.py::test_name -v
```

**Testing Constraints & Notes:**
- `pytest.ini` automatically excludes tests marked with `integration` and `gpu`.
- Tests stub out the BGE-M3 embedding module and replace the lifespan context (see `tests/conftest.py`).
- Required test environment variables: `NEO4J_PASSWORD`, `LITELLM_MASTER_KEY` (`conftest.py` sets safe local defaults).
- All new tests must be placed in `services/rag-service/tests/`.

### Frontend Validation (React / TypeScript)
Run from `services/frontend/`:
```bash
cd services/frontend
npm ci          # Clean install dependencies
npm run lint    # ESLint verification
npm run typecheck # TypeScript static type verification
npm run build   # Production build with 4GB heap allocation
npm run dev     # Start local development server
```

### Python Linting
Check PEP8 compliance and type standards:
```bash
flake8 services/rag-service/ --config=services/rag-service/.flake8
```

### Operational & Audit Scripts
Located in `services/rag-service/scripts/` (requires running infrastructure):
```bash
# Smoke test core API routes
python3 services/rag-service/scripts/smoke_test.py

# Run comprehensive RAG quality audit
python3 services/rag-service/scripts/comprehensive_audit.py
```

## Continuous Integration (GitHub Actions)

On every push or PR to `master`, CI executes 3 parallel jobs:
1. **`backend-tests`**: Python 3.12, installs `requirements-ci.txt` (excluding heavy GPU packages like torch/surya), executes `pytest tests/ -v --timeout=60`.
2. **`frontend-build`**: Node 20, runs `npm ci && npm run lint && npm run typecheck && npm run build`.
3. **`lint`**: Executes `flake8` on the RAG service with `--max-line-length=150`.

## Environment Variables

| Variable | Target Service | Purpose & Notes |
|---|---|---|
| `NEO4J_PASSWORD` / `NEO4J_PASS` | RAG Service | Authentication password for Neo4j (handled via Pydantic `AliasChoices`). |
| `LITELLM_MASTER_KEY` | AI Gateway / RAG | Master token for authenticating calls to AI Gateway proxy. |
| `VITE_API_URL` | Frontend | Base URL pointing from frontend client to RAG backend API. |
| `QWEN35B_SNAPSHOT`, `QWEN35B_MODEL_DIR` | vLLM / Ingestion | Local model checkpoint paths on DGX Spark storage. |
| `PRIMARY_VISION_MODEL`, `FALLBACK_VISION_MODEL` | Ingestion / Gateway | Model routing aliases for multimodal OCR extraction. |
| `FORCE_CPU_EMBEDDING=1`, `FORCE_CPU_RERANKER=1` | RAG Service | Enables CPU fallback mode for local testing without GPU. |
| `HF_HOME=/app/models` | Docker / Ingestion | Hugging Face model cache directory mount point. |
