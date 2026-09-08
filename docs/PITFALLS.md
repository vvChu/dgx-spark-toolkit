# Common Pitfalls & Troubleshooting

Critical technical gotchas, anti-patterns, and environment constraints to keep in mind when modifying or debugging the system.

## 1. Dual `pipeline.py` Naming Conflict
- **`services/rag-service/ingestion/pipeline.py`**: The actual production document ingestion module defining the `ProductionIngestor` class.
- **Root-level `pipeline.py`**: A standalone legacy post-processing export repair script.
- **Rule**: Never use relative or ambiguous imports for `pipeline.py`. Always use explicit full module paths (e.g., `from ingestion.pipeline import ProductionIngestor`).

## 2. GPU Packages & Fallbacks in CI
- Heavy GPU-dependent libraries (`surya-ocr`, `torch`, `cuda-python`) are strictly excluded from `requirements-ci.txt` to keep CI builds fast and lightweight.
- When writing tests or running locally without GPUs, always set:
  ```bash
  export FORCE_CPU_EMBEDDING=1
  export FORCE_CPU_RERANKER=1
  ```

## 3. Strict Redis Database Separation
- **Redis DB 0**: Dedicated strictly to LiteLLM semantic cache storage.
- **Redis DB 1**: Dedicated strictly to the ingestion streaming job queue (`ingest:queue`).
- **Rule**: Never send cache keys to DB 1 or queue tasks to DB 0 to avoid cache evictions clearing job queues.

## 4. Model Cache Volume Persistence
- When starting Docker containers, ensure `HF_HOME=/app/models` is mounted to persistent volume `model_cache`.
- Without this mount, Surya OCR weights (~1.3GB) and embedding models will re-download on every container restart.

## 5. Frontend Build Memory Exhaustion (OOM)
- The React 19 / Vite build with extensive graph visualization packages requires significant memory during bundle optimization.
- **Fix**: The build command in `package.json` must be invoked with `--max-old-space-size=4096`.

## 6. Stale Ingestion Jobs in Workers
- If a `rag-watcher` worker container crashes or restarts during active processing, affected documents may remain stuck in state `PROCESSING`.
- The system includes a 1-hour timeout reaper, but manual resets can be performed via the admin maintenance script in `services/rag-service/scripts/`.

## 7. Neo4j Credential Aliasing
- Pydantic Settings accepts either `NEO4J_PASSWORD` or `NEO4J_PASS` via `AliasChoices`.
- Ensure custom setup scripts or connection strings check both aliases before erroring.

## 8. Centralized API Proxy Protocol & Prefix (`openai/` vs `anthropic/`)
- **Context**: Centralized API Proxy (`GATEWAY_PROXY_URL=http://100.83.192.30:8045/v1`) is an OpenAI-compatible gateway (New API / One API).
- **Rule**: In `litellm_config.yaml`, **ALL models routed through this proxy (including Claude Opus/Sonnet/Haiku) MUST use the `openai/` prefix**:
  ```yaml
  model: openai/claude-opus-4-6-thinking
  api_base: os.environ/GATEWAY_PROXY_URL
  ```
- **Anti-pattern**: Never use `anthropic/` with `GATEWAY_PROXY_URL`. When LiteLLM detects `anthropic/`, it switches to Anthropic native protocol and appends `/v1/messages` to `api_base`, generating duplicate paths like `http://100.83.192.30:8045/v1/v1/messages` (Protocol: Claude) and causing immediate **HTTP 404 Not Found (0ms)** errors on the proxy.
