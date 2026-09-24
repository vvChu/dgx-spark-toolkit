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
- **Redis DB 2**: Dedicated strictly to the Context Lake (`SessionMemory`, `TraceStore`, `ContextAccumulator`).
- **Redis DB 3**: Dedicated strictly to `SemanticCache` L2 persistent cache.
- **Redis DB 4**: Dedicated strictly to `HITLService` low-confidence review queue.
- **Rule**: Never cross-post keys between DB partitions (e.g. sending cache keys to DB 1 or queue tasks to DB 0) to avoid cache evictions clearing job queues or corrupting conversational state.

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

## 9. The Semantic Cache Latency Illusion (Cold-Cache vs Cached SLAs)
- **Trap**: Performance benchmarks and latency tests for LLM calls / fallback chains may falsely report fast response times (e.g., < 3.0s) because subsequent calls hit `SemanticCache` (Redis DB 3) or LiteLLM cache (Redis DB 0) from previous test runs.
- **Consequence**: When a cold query arrives or the service restarts, a broken upstream model may trigger retries (e.g., 3 retries × 20s = 60s), causing silent `ReadTimeout` crashes.
- **Rule**: Always benchmark latency on **Cold Cache** using unique dynamic UUID prompts (`f"UUID_{uuid.uuid4().hex[:6]} ..."`) or cache-bypass headers. Never trust warm cached calls as SLA proof.

## 10. Multi-Key Deprecation Asymmetry (Provider Lifecycle Desync)
- **Trap**: Recommending or deploying a cloud model based on a single passing API key test.
- **Consequence**: Models like `gemini-2.5-flash-lite` remain active on legacy accounts/keys, but return `HTTP 404 NOT_FOUND` on newer projects. In round-robin pools, requests routed to newer keys will crash. Similarly, models like `gemini-3.1-flash-lite` suffer upstream 503 high-demand spikes during peak hours.
- **Rule**: Always validate model availability across at least 3 distinct API keys in the gateway pool. For real-time RAG (query rewrite, timeline, rerank), strictly prioritize ultra-stable models (`claude-haiku-4` -> `rag-core` on-premise GPU).

## 11. Vector DB Audit Sampling Blind Spot (Always Enforce Set Parity)
- **Trap**: Auditing vector database quality using random entity sampling (e.g. `client.query(limit=2000)`).
- **Consequence**: The audit may score 95+/100 while entirely missing a whole document (e.g., 641 chunks missing from an un-ingested file), because sampling only inspects entities that already exist.
- **Rule**: Audit tools MUST enforce a Set Parity check: `missing = set(exported_json_doc_ids) - set(milvus_doc_ids)`. Any missing document must incur severe penalties (≥ 25 pts) and trigger gate rejection.

## 12. Bilingual Diacritic Spoofing & Bare Negation False Interrogatives
- **Trap**: Detecting language or interrogatives in synthetic queries using naive diacritic checks (`_VN_DIACRITICS.search(line)`) or standalone negation words like `'không'`.
- **Consequence**: English queries quoting Vietnamese terms in parentheses (e.g., `What are the requirements for (thẩm duyệt)?`) or declarative sentences containing negative particles are falsely classified as valid Vietnamese questions, allowing AI scratchpads and prompt echoes into the vector database.
- **Rule**: Always strip parentheses and quotes (`re.sub(r'\(.*?\)|"[^"]*"', '', line)`) before testing diacritics. Replace bare `'không'` with explicit compound interrogatives (`'được không'`, `'phải không'`, `'hay không'`), and aggressively reject English interrogatives (`\b(?:what|who|where|how|which)\b`). Use `re.split(r'\s+/\s+', line)` to preserve citations like `52/2019/TT-BCA`.

## 13. Dataclass Serialization & Linux Hidden File Traps in Exporters
- **Trap**: Passing dataclass objects (`ProcessedDocument`, `Chunk`) directly to `json.dump()` or deriving filenames directly from relative paths (e.g. `../52/2019/TT-BCA`).
- **Consequence**: Unhandled dataclasses cause `TypeError` crashes during export. Unstripped leading dots (`safe_filename = doc_id.replace(...).lstrip('.')`) create hidden files on Linux (e.g., `.._52_2019_TT-BCA.json`), making exported documents invisible to file crawlers and resulting in complete data loss in Milvus.
- **Rule**: In exporter pipelines, always normalize filenames with `.lstrip('.')` and ensure multi-tier serialization guards (`to_dict()`, `asdict()`, `vars()`).

## 14. Cold-Startup Model Warmup Budget vs Theoretical Latency (DGX Spark GB10)
- **Trap**: Estimating startup warmup duration based on theoretical or desktop benchmarks (e.g., assuming ~22s for BGE-M3 and ~12s for Reranker $\rightarrow$ setting a 60s timeout).
- **Consequence**: In production on DGX Spark GB10 Blackwell hardware with full tokenizers, cold cache, and PyTorch CUDA context compilation, BGE-M3 (CPU) takes **~60s** (10.7s load + 49.3s cold query embed) and BGE-Reranker (GPU) takes **~34s** (load + predict), totalling **~94s**. Setting `WARMUP_TIMEOUT_SECONDS = 60s` causes 100% false timeouts on cold boot, dropping the container into degraded mode (503).
- **Rule**: Set `WARMUP_TIMEOUT_SECONDS >= 110.0s`, safely below Docker's `start_period: 120s`. Use `asyncio.shield` so that if I/O spikes exceed the timeout, the worker continues in the background and self-heals by updating `warmup_status = ready` upon completion.

## 15. Mutex Lock Leaks & Deadlocks in Asynchronous ML Warmup
- **Trap**: Performing argument validation or type conversion (e.g., `float(timeout)`) *after* acquiring a non-blocking mutex (`_warmup_thread_lock.acquire(blocking=False)`).
- **Consequence**: An unhandled `ValueError` or task dispatch failure before creating the worker task aborts the function while leaving the lock acquired in process memory. All subsequent warmup triggers (and `/admin/warmup` requests) permanently return `HTTP 409 Conflict` (`already_in_progress`) until the entire container process is restarted.
- **Rule**: Always validate and parse all arguments *before* acquiring concurrency locks. Wrap worker task dispatch in `try...except` blocks that explicitly release the lock if dispatch fails.

