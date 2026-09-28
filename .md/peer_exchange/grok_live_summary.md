# 📡 TỔNG HỢP TIẾN ĐỘ THỜI GIAN THỰC TỪ GROK

- **Cập nhật lúc**: `2026-09-28 16:21:10`
- **Session ID**: `01a0e67d-bb9b-7bb1-8597-7c3934efa08c`
- **Workflow ID**: `wf_01a0e688259d7e32abd1bd24bf808e98`
- **Giai đoạn hiện tại**: **`Repair`**
- **Trạng thái**: `complete`
- **Báo cáo cuối cùng (`docs/architecture_audit_report.md`)**: ✅ ĐÃ SẴN SÀNG

## 🤖 Tiến độ Subagents của Grok

| Subagent | Giai đoạn | Trạng thái | Tokens | Thời gian (ms) |
|---|---|---|---|---|
| `explorer-a` | Explore | **done** | 563,059 | 294,081 |
| `explorer-b` | Explore | **done** | 1,256,962 | 514,403 |
| `explorer-c` | Explore | **done** | 680,153 | 466,810 |
| `explorer-d` | Explore | **done** | 850,612 | 449,293 |
| `static-audit` | Audit | **done** | 764,770 | 366,268 |
| `live-verify` | Audit | **done** | 670,751 | 387,836 |
| `report-writer` | Synthesize | **done** | 1,379,408 | 635,401 |
| `reviewer` | Gate | **done** | 81,194 | 97,292 |
| `challenger` | Gate | **done** | 2,705,239 | 589,439 |
| `forensic` | Gate | **done** | 89,100 | 136,737 |
| `stamp` | Stamp | **done** | 305,668 | 172,432 |
| `confirm` | Confirm | **done** | 31,282 | 54,298 |

## 🔍 Các phát hiện cốt lõi từ Grok đã thu thập được

### Subagent: `01a0e688-25cc-7a21-abf5-c60cc39fd0ed` (`01a0e688`)

`docs/ARCHITECTURE.md` matches the tree. `.agents/ARCHITECTURE.md` still calls `pipeline.py` a monolith and also marks the stage split done; that done-claim does not. There is no `ingestion/stages/` package. `DocumentIngestionPipeline.run_pipeline` runs nine methods in one file. `ProductionIngestor` is an alias.

| Stage | Symbol |
|---|---|
| intake | `DocumentIngestionPipeline._stage_intake` |
| ocr | `_stage_ocr` → `DocumentReader.extract` |
| metadata | `_stage_metadata` → `_parse_metadata` / `_parse_metadata_from_text` |
| identity | `_stage_identity` (sets `namespace="VBPL"` only; `doc_id` is `DocumentIdentity.doc_id`) |
| chunking | `_stage_chunking` → `DocumentChunker.chunk_document` |
| enrichment | `_stage_enrichment` → `_parse_relationships_llm` |
| embedding | `_stage_embedding` → `self.model.embed_documents` |
| indexing | `_stage_indexing` → `DocumentStore.index_document_sync` |
| export | `_stage_export` → `DataExporter.export_document` |

Searches under `ingestion/` and `retrieval/migrations/`: `s01_intake` is only the stage name in `pipeline.py` and `models.py`. `xadd` / `xreadgroup` are in `queue.py`. `TRUNCATE` is `StateManager.reset_all`. Content hashes are SHA-256 in `get_file_hash`, MD5 in the `DocumentIdentity` comment and `hub3_bridge.py`. `PipelineEvent`, `alembic`, and `HF_HOME` are absent there. `async def` exists on `ingest_file` (it calls sync `run_pipeline`), `DocumentReader.extract_async`, Hub3 Neo4j sync, sync-backed state wrappers, and `migrate_neo4j`.

```json
{
  "summary": "docs/ARCHITECTURE.md is the description that matches the tree: nine stages are methods on DocumentIngestionPipeline inside pipeline.py, not files under ingestion/stages. The .agents current-state line that calls pipeline.py a monolith is right; evolution item 3 marking that split done is wrong. Intake is _stage_intake, OCR is _stage_ocr via DocumentReader.extract, metadata is _stage_metadata, identity is _stage_identity, chunking is _stage_chunking via DocumentChunker.chunk_document, enrichment is _stage_enrichment, embedding is _stage_embedding, indexing is _stage_indexing via DocumentStore.index_document_sync, and export is _stage_export via DataExporter.export_document. The worker can ACK failures, strand Redis pending entries, and mark a document completed without a successful index or a content-hash check.",
  "findings": [
    {
      "title": "Stage split is marked done but pipeline.py is still the monolith",
      "path": ".agents/ARCHITECTURE.md",
      "evidence": "Item 3 marks the split into stages done. No ingestion/stages directory exists. run_pipeline still calls the nine _stage_* methods in pipeline.py.",
      "severity": "high"
    },
    {
      "title": "Worker ACKs failures because safe_process swallows them",
      "path": "services/rag-service/ingestion/pipeline.py",
      "evidence": "safe_process catches exceptions and returns None. The worker then always calls queue.acknowledge, so failed files are never nacked or retried.",
      "severity": "high"
    },
    {
      "title": "Acknowledge can mark a failed document COMPLETED",
      "path": "services/rag-service/ingestion/ingestion_queue.py",
      "evidence": "claim and acknowledge update the message file_path. Intake and indexing update the SOURCE_DIR relative path, so FAILED can be overwritten or split across two rows.",
      "severity": "high"
    },
    {
      "title": "Redis pending messages are never reclaimed",
      "path": "services/rag-service/ingestion/queue.py",
      "evidence": "claim_next uses xreadgroup with id > only. A false claim_file drops the message without ack or nack, and there is no XAUTOCLAIM.",
      "severity": "high"
    },
    {
      "title": "Indexing failure is still treated as pipeline success",
      "path": "services/rag-service/ingestion/pipeline.py",
      "evidence": "_stage_indexing ignores the dict from index_document_sync, logs exceptions as warnings, caches the relative path, and still returns the document.",
      "severity": "high"
    },
    {
      "title": "Completed files are skipped without comparing content hash",
      "path": "services/rag-service/ingestion/pipeline.py",
      "evidence": "Intake returns None when the relative path is COMPLETED and never calls get_existing_doc_hash. The stored hash is SHA-256; the model comment says MD5.",
      "severity": "high"
    },
    {
      "title": "Identity done-claim does not assign chunk_id",
      "path": "services/rag-service/ingestion/pipeline.py",
      "evidence": "_stage_identity only sets namespace to VBPL. chunk_document does not set chunk_id, and no later stage does, so Milvus can store it empty.",
      "severity": "high"
    },
    {
      "title": "Async database checkmark is a sync SQLAlchemy alias",
      "path": "services/rag-service/core/database.py",
      "evidence": "Checked item 6 requires asyncpg. async_state_manager is assigned the sync PostgresStateManager. No asyncpg usage exists under rag-service.",
      "severity": "high"
    }
  ],
  "uncertainties": [
    "Compose sets HF_HOME to the Hugging Face home cache and mounts model_cache at /app/model_cache, not HF_HOME=/app/models. Container env was not executed.",
    "PipelineEvent and Alembic are absent. Those North Star principles are not marked done. Migrations are one-off scripts.",
    "StateManager.reset_all TRUNCATEs ingestion_state and system_checkpoints. It was not found on the worker hot path.",
    "insert_chunks does not delete existing doc_id rows, and claim_file will not reclaim PROCESSING. A stale claim can duplicate vectors.",
    "migrate_neo4j.py has a default for NEO4J_PASS; the value is omitted. Unknown if every producer enqueues a path equal to rel_path."
  ]
}
```

---

### Subagent: `01a0e688-25e6-7ce0-88ab-4e0739a4abad` (`01a0e688`)

Retrieval stays on async Milvus and Neo4j, with local BGE-M3 embeddings and a local reranker. Gateway calls are async HTTP, but the exact and semantic caches call synchronous Redis on the event loop. `rag-core` matches the vLLM 36B served name `qwen-local-primary`; `rag-light` matches `qwen3.5-9b` on profile-gated `vllm-4b`.

```json
{
  "summary": "Search uses async Milvus, Neo4j, and httpx to the gateway. Embeddings are in-process BAAI/bge-m3 via run_in_executor, and the reranker is a local CrossEncoder via asyncio.to_thread. Gateway names rag-core and qwen-local-primary match vllm-36b served name qwen-local-primary through GATEWAY_LOCAL_URL (host port 8004, not vllm-36b:8000). rag-light matches vllm-4b served name qwen3.5-9b at http://vllm-4b:8000/v1, but that service is profile vllm-light. Caches: LiteLLM Redis DB 0, ingestion queue DB 1, session/context DB 2, semantic plus tier-0 DB 3, HITL DB 4. If the local model is wedged, HyDE can sit on 300s retries; a fast connection refusal falls through rag-core (empty router fallback) to stopped rag-light, and HyDE then embeds the original query.",
  "findings": [
    {
      "title": "Semantic hits are pinned as exact results for a different query",
      "path": "services/rag-service/retrieval/search_pipeline.py",
      "evidence": "Semantic hits are written to the exact key for the new query. Cache writes use the rewritten or HyDE vector, and the exact key ignores use_hyde and use_agentic.",
      "severity": "high"
    },
    {
      "title": "Cached passages skip live validity and can outlive TTL",
      "path": "services/rag-service/retrieval/semantic_cache.py",
      "evidence": "A cache hit returns before Neo4j status refresh. L2 scans entries without reading timestamp, and set() expiry is refreshed on the whole list key.",
      "severity": "high"
    },
    {
      "title": "Sync Redis cache calls block the search event loop",
      "path": "services/rag-service/retrieval/tier0_cache.py",
      "evidence": "Tier-0 and semantic get/set use blocking redis.Redis inside async search, with no socket_timeout. A stalled DB 3 call holds the event loop.",
      "severity": "high"
    },
    {
      "title": "Unauthenticated Redis can replace cached legal passages",
      "path": "docker-compose.yml",
      "evidence": "litellm-redis publishes 16379 with AOF and no requirepass. Exact and semantic caches store result text on DB 3 of that Redis.",
      "severity": "high"
    },
    {
      "title": "BGE-M3 lazy init can stall the event loop",
      "path": "services/rag-service/core/singleton.py",
      "evidence": "embed lookup calls get_embedding_model() on the event loop. LazyInit holds a threading.Lock for the whole BGE-M3 load, which warmup also takes in a thread.",
      "severity": "high"
    },
    {
      "title": "Complex chat queries force HyDE onto a long local chain",
      "path": "services/rag-service/retrieval/hyde.py",
      "evidence": "COMPLEX intent sets use_hyde True. Chat passes use_agentic False, so HyDE runs. complete() then waits up to 300s, three tries, on rag-core twice and profile-off rag-light.",
      "severity": "medium"
    },
    {
      "title": "Search rewrites can silently come from the OCR fallback",
      "path": "services/ai-gateway/litellm_config.yaml",
      "evidence": "claude-haiku-4 is missing from router fallbacks, so LiteLLM uses ocr-fallback. The client accepts that text and the rewrite cache keeps it with no TTL.",
      "severity": "medium"
    },
    {
      "title": "Low-confidence flag does not run grounding",
      "path": "services/rag-service/retrieval/search_pipeline.py",
      "evidence": "If the top score is below 0.65 the pipeline only flips search_grounding_triggered. It still returns and caches those hits, with no extra retrieval.",
      "severity": "low"
    }
  ],
  "uncertainties": [
    "LiteLLM 1.83.3 default_fallbacks behavior was inferred from the config, not executed.",
    "No measurement of whether 0.92 cosine similarity collides on real Vietnamese legal queries.",
    "Host firewalling of port 16379, or a Redis password outside compose, was not verified.",
    "GATEWAY_LOCAL_URL reachability depends on HOST_IP; the compose localhost fallback would not reach vllm-36b from the gateway container.",
    "A wedged vLLM was not load-tested, so the HyDE retry stack timing is from the client timeouts only."
  ]
}
```

---

### Subagent: `01a0e688-25e6-7ce0-88ab-4e2a860db795` (`01a0e688`)

The agent tree is a CCBA spoke catalog dropped onto this DGX toolkit. Root `AGENTS.md` and `CLAUDE.md` are the same 18-line entrypoint. `.agents/workflows` holds 17 operational runbooks, not agent definitions. Skill directories and `catalog.yaml` do not match, and several runbooks can change the live stack.

```json
{
  "summary": "Root AGENTS.md and CLAUDE.md are identical 18-line progressive entrypoints, matching ADR 0004. .agents/AGENTS.md is a separate CCBA hub constitution, and catalog.yaml sets hub_path to . with hub_repo ccba-agent-platform. list_dir shows 90 skill directories. catalog.yaml skills: has 74 name entries (57 on disk, 17 missing including bigbim-classification, ccba-adr-lifecycle, and ccba-seminar-builder; 33 local dirs are unlisted, including vllm-manager, infrastructure-manager, and the Matt Pocock set). It also lists 7 rules and 4 knowledge items; workflows is empty. .agents/rules contains only codebase-engineering-rules.md; ccba_identity.md is missing. All 17 workflow files are operational runbooks (16 declare type: workflow; save-session.md does not). start-all-128k and vllm-128k are deprecated and do not shell out. Enabled mutators include start-all, start-all-32k, rag-only, vllm-32k, stop-all, stop-rag, stop-vllm, setup-remote, update-qwen (qwen-update.sh), ccba-update-models (--force), and pr-copilot-flow (git push and gh pr merge). health, track-ingestion, and save-session are read-oriented. audit-skills can rewrite workflows and playbooks via workflow_optimizer.py. vllm-manager documents docker restart qwen36b and docker compose up. Orchestrator progress was last visited 2026-08-09, with the playbook audit marked done and no active subagents; victory_auditor_1 is not on that roster. Overlapping pairs include setup-matt-pocock-skills with ccba-setup-skills, and grill-me with ccba-grilling.",
  "findings": [
    {
      "title": "Committed gateway bearer in skills and audit notes",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/ccba-ai-gateway-sdk/.env.ai-gateway",
      "evidence": "AI_GATEWAY_KEY and OPENAI_API_KEY are literals. The same bearer appears in ccba-update-models.md, ccba-ai-gateway-sdk/SKILL.md, ccba-platform/SKILL.md, and victory_auditor_1/handoff.md.",
      "severity": "high"
    },
    {
      "title": "Model-update workflow force-patches the live gateway",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/workflows/ccba-update-models.md",
      "evidence": "Workflow description says it patches litellm_config.yaml and restarts ai-gateway; step 2 runs model_auto_updater.py --force. model-updater repeats it.",
      "severity": "high"
    },
    {
      "title": "Compose workflows start and stop production stacks",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/workflows/stop-all.md",
      "evidence": "stop-all runs docker compose down. start-all, start-all-32k, rag-only, and vllm-32k run compose up. stop-rag and stop-vllm stop service groups.",
      "severity": "high"
    },
    {
      "title": "Remote-access workflow changes the host firewall",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/workflows/setup-remote.md",
      "evidence": "Enabled workflow runs sudo bash scripts/setup-remote-access.sh to configure firewall rules and remote access.",
      "severity": "high"
    },
    {
      "title": "Infrastructure skill stops and starts host services",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/infrastructure-manager/SKILL.md",
      "evidence": "Skill instructs bash scripts/start-all.sh, scripts/stop-all.sh, and systemctl --user restart or stop of dgx-chatops.",
      "severity": "high"
    },
    {
      "title": "Skill catalog does not match the skill tree",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/platform-loader/catalog.yaml",
      "evidence": "90 skill directories versus 74 catalog skills: 57 overlap, 17 missing, 33 unlisted. workflows is empty. ccba_identity.md is missing.",
      "severity": "medium"
    },
    {
      "title": "Matt Pocock skills overlap CCBA ports",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/setup-matt-pocock-skills/SKILL.md",
      "evidence": "This skill and ccba-setup-skills both configure tracker, labels, and domain docs. grill-me only launches a grilling session beside ccba-grilling.",
      "severity": "medium"
    },
    {
      "title": "Orchestrator state is a finished August audit",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/.agents/orchestrator/progress.md",
      "evidence": "Last visited 2026-08-09 with every milestone done and no active subagents. victory_auditor_1 is not on the orchestrator roster.",
      "severity": "medium"
    }
  ],
  "uncertainties": [
    "The bearer was used successfully in the August victory handoff. It was not rechecked against the gateway on 2026-09-28.",
    "CLAUDE.md content matches root AGENTS.md. Whether CLAUDE.md is a symlink was not stat-checked.",
    "The 90-directory count is from list_dir, which hides dot-directories. The hidden .env.ai-gateway file was opened directly.",
    "model_auto_updater.py was not read. Force-update behavior is taken from the workflow description and model-updater skill.",
    "Grep skips gitignored files, so further copies of the bearer may exist in other .agents logs."
  ]
}
```

---

### Subagent: `01a0e688-25e7-7022-ab92-01b2d012c677` (`01a0e688`)

Compose keeps Redis DB 0 for the LiteLLM cache and DB 1 for the ingestion queue. The app then forces context state onto DB 2, semantic cache onto DB 3, and HITL onto DB 4. The named volume `model_cache` is mounted, but `HF_HOME` does not use it. Profiles `ingest`, `vllm-light`, and `loadtest` are omitted by `scripts/start-all.sh`.

Credential values were seen and are omitted. The names are `.env` `GRAFANA_ADMIN_PASSWORD` and `TELEGRAM_BOT_TOKEN`, `helm/dgx-spark-toolkit/values.yaml` `neo4j.password` and `database.postgresUrl`, and `docker-compose.yml` `WEBUI_SECRET_KEY` and `ADMIN_SECRET`.

```json
{
  "summary": "Profiles are ingest (rag-watcher), vllm-light (vllm-4b), and loadtest (locust). start-all.sh runs docker compose up -d, so those stay off. Compose REDIS_CACHE_URL is DB 0 and REDIS_QUEUE_URL is DB 1. LiteLLM cache_params uses litellm-redis:6379 with no db index. SessionMemory, TraceStore, and ContextAccumulator force /2; semantic and tier0 caches force /3; HITL forces /4. etcd, MinIO, Milvus, Neo4j, Postgres, Redis AOF, and Open WebUI have named volumes. Healthchecks cover rag-service, ocr-worker, ai-gateway, Postgres, Redis, etcd, MinIO, Milvus, Neo4j, frontend, and both vLLM services. Prometheus, Grafana, Open WebUI, cloudflared, watchdog, and whisper have none. Helm does not override the Milvus collection, so it stays legal_docs_v11. chatops_daemon.py is not in compose; the watchdog calls 172.21.0.1:8095. requirements.txt is ranged, the image installs requirements-app.lock, and the CI lock pins different neo4j and opencv.",
  "findings": [
    {
      "title": "Prometheus and Grafana lose state when the container is replaced",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml",
      "evidence": "prometheus and grafana mount only config and dashboard files. No volume for /prometheus or /var/lib/grafana. rule_files points at alerts.yml, which is not mounted.",
      "severity": "high"
    },
    {
      "title": "RAG healthcheck ignores Redis, Postgres, and OCR readiness",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml",
      "evidence": "The rag-service probe calls /health, which only fails on Milvus, Neo4j, or warmup. Redis and Postgres are checked at /health/pipeline. ocr-worker is depends_on service_started, not healthy.",
      "severity": "high"
    },
    {
      "title": "Gateway liveliness probe skips Postgres and Redis",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml",
      "evidence": "ai-gateway healthcheck requests /health/liveliness. depends_on includes litellm-db and litellm-redis. litellm_config.yaml sets background_health_checks to false.",
      "severity": "high"
    },
    {
      "title": "Ingestion watcher has no healthcheck and Milvus does not wait for its stores",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml",
      "evidence": "rag-watcher healthcheck is disabled. OCR and ai-gateway use service_started. milvus-standalone depends_on etcd and MinIO with no service_healthy condition, and its healthcheck has no start_period.",
      "severity": "high"
    },
    {
      "title": "Helm and Compose disagree on the RAG port",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/helm/dgx-spark-toolkit/values.yaml",
      "evidence": "Helm service.port is 8000; compose publishes 8005:8000. Container port is 8000 in both. LiteLLM image main-latest versus v1.83.3-stable. RAG limit 16Gi versus 12G; watcher 8Gi versus 14G. Milvus 19530 matches. No collection override.",
      "severity": "high"
    },
    {
      "title": "Backpressure and table cache break the Redis DB split",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml",
      "evidence": "Compose sets rag REDIS_URL from REDIS_QUEUE_URL (/1) and gateway plus watchdog from REDIS_CACHE_URL (/0). Watchdog writes rag:ingestion:paused on that cache DB. Queue is_paused reads the queue client. chunking.py caches table summaries on REDIS_URL.",
      "severity": "medium"
    },
    {
      "title": "model_cache is mounted but HF_HOME does not use it",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/docker-compose.yml",
      "evidence": "HF_HOME is /home/appuser/.cache/huggingface on a host bind. Named volume model_cache is mounted at /app/model_cache, not that path. PITFALLS says HF_HOME=/app/models. Helm templates declare no volumeMounts.",
      "severity": "medium"
    },
    {
      "title": "CI and app requirement locks pin different stacks",
      "path": "/home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-ci.lock",
      "evidence": "App lock pins neo4j 5.26.0 and opencv-python-headless 4.11.0.86. CI lock pins neo4j 5.23.1 and opencv 5.0.0.93. requirements.txt caps opencv below 5. Docker installs requirements-app.lock, not requirements.txt. surya-ocr is only in requirements.txt.",
      "severity": "medium"
    }
  ],
  "uncertainties": [
    "LiteLLM /health/liveliness is not implemented in this repo, so it is not proven here that the handler ignores Postgres and Redis.",
    "A Docker process restart keeps the writable layer; Prometheus and Grafana data are lost on container replace, not necessarily on every restart.",
    "Helm neo4j.password is in Settings._WEAK_PASSWORDS and the chart litellm-key falls back to a denylisted placeholder; this was not checked on a live cluster.",
    "Root .env MILVUS_COLLECTION is not injected by the compose service block; legal_docs_v11 matches only because that is the code default.",
    "requirements-ci.txt allows prometheus-fastapi-instrumentator>=6.0.0 while the app floor is 8.1.0; both locks currently pin 8.1.0."
  ]
}
```

---

### Subagent: `01a0e68f-ff8a-7942-92da-0af38aae3be3` (`01a0e68f`)

The North Star checklist marks several mechanisms done, but the tree still has a single pipeline module, a sync database alias, and no versioned Milvus migrations. Stage methods, Redis stream calls, Prometheus counters, and a named model volume are substitutes, not the stated designs.

```json
{"rows":[{"id":"NS1","principle":"Pipeline as stages","completion":"not_met","gap":"Evolution item 3 marks the file split done, but ingestion/stages/01_intake.py through 09_export.py do not exist. Nine _stage_* methods remain inside the pipeline.py monolith the Current State still says must be split.","evidence":"services/rag-service/ingestion/pipeline.py run_pipeline calls nine _stage_* methods. The ingestion/stages files 01_intake.py through 09_export.py are absent.","effort":"M","effort_note":"The nine methods already live in services/rag-service/ingestion/pipeline.py; splitting them and fixing dict handoffs in chunking.py and document_store.py takes several days."},{"id":"NS2","principle":"Pydantic models","completion":"partial","gap":"DocumentIdentity, Chunk, and ProcessedDocument exist as dataclasses, not Pydantic models. OCR pages, chunk_document results, metadata, and index enrichment still travel as dicts with optional keys.","evidence":"ingestion/models.py DocumentIdentity, Chunk, and ProcessedDocument are dataclasses. pipeline._stage_ocr assigns doc.pages, and DocumentChunker.chunk_document returns list[dict].","effort":"M","effort_note":"models.py needs a Pydantic conversion, and pipeline.py, chunking.py, and document_store.py still pass page and chunk dicts on the hot path."},{"id":"NS3","principle":"Redis Streams","completion":"partial","gap":"xadd and xreadgroup exist, but the claim is not atomic. A false claim_file drops the already-read entry with no ack, nack, or XAUTOCLAIM, and safe_process swallows errors so run always acknowledges.","evidence":"queue.py RedisQueue.enqueue calls xadd and claim_next calls xreadgroup on '>'. IngestionQueue.claim_next drops the entry when claim_file is false. No xautoclaim.","effort":"M","effort_note":"queue.py, ingestion_queue.py, and pipeline.py need pending reclaim, a nack when claim_file fails, and safe_process to stop hiding errors before acknowledge."},{"id":"NS4","principle":"Full async","completion":"not_met","gap":"Item 6 checks asyncpg, but nothing imports it. async_state_manager is the sync SQLAlchemy StateManager. ingest_file calls sync run_pipeline, which uses httpx.Client, while Tier0ExactCache uses blocking redis.Redis. AsyncClient and AsyncMilvusClient exist elsewhere.","evidence":"database.py assigns async_state_manager to sync PostgresStateManager. asyncpg is pinned in requirements-app.lock but never imported. ingest_file calls sync run_pipeline.","effort":"L","effort_note":"state_manager.py, core/database.py, pipeline.py, and retrieval/tier0_cache.py stay synchronous; using the pinned asyncpg without blocking the loop is more than five days."},{"id":"NS5","principle":"Model cache volume","completion":"partial","gap":"A named model_cache volume exists, but it is mounted at /app/model_cache. HF_HOME points at the Hugging Face home cache, so the required /app/models mount is not what the process uses.","evidence":"docker-compose.yml sets HF_HOME to /home/appuser/.cache/huggingface and mounts named volume model_cache at /app/model_cache, not /app/models.","effort":"S","effort_note":"docker-compose.yml is the runtime mount; retargeting HF_HOME and model_cache, then aligning docs/PITFALLS.md and docs/DEVELOPMENT.md, is under two days."},{"id":"NS6","principle":"Idempotent re-ingestion","completion":"partial","gap":"Completed paths are skipped by status, not by comparing the stored content hash. insert_chunks does not upsert by doc_id plus hash, reset_all still TRUNCATEs, and a failed index return can still be acknowledged as COMPLETED.","evidence":"pipeline._stage_intake returns None when is_document_processed sees COMPLETED. get_existing_doc_hash has no callers. reset_all runs TRUNCATE. insert_chunks only inserts.","effort":"M","effort_note":"pipeline.py, state_manager.py, document_store.py, and milvus_repo.py must compare hashes, upsert by doc_id, and stop using TRUNCATE or a blind COMPLETED ack."},{"id":"NS7","principle":"Observable pipeline","completion":"partial","gap":"Stage histograms and counters are scraped and a Grafana ingestion dashboard graphs them. There is no PipelineEvent type emitting structured events into those series.","evidence":"pipeline.py STAGE_DURATION records rag_stage_duration_seconds. grafana-ingestion-dashboard.json queries that metric. No PipelineEvent symbol exists.","effort":"S","effort_note":"pipeline.py can emit a PipelineEvent beside the existing STAGE_DURATION counters; monitoring/grafana-ingestion-dashboard.json already graphs those series."},{"id":"NS8","principle":"Schema migration","completion":"not_met","gap":"There is no Alembic-style version history for Milvus. Startup only creates a missing collection, and the reindex script drops and recreates it. migrate_sparse is a one-off script, not a versioned migration.","evidence":"milvus_repo.py ensure_collection_schema creates a missing collection and does not version it. reindex_milvus_clean.py main calls drop_collection. Alembic is absent.","effort":"L","effort_note":"repositories/milvus_repo.py, scripts/reindex_milvus_clean.py, and retrieval/migrations/migrate_to_native_sparse.py need a versioned migrator instead of create-if-missing and drop-and-recreate."}],"doc_conflicts":[".agents/ARCHITECTURE.md item 3 checks the stage-file split done, but Current State still calls pipeline.py a monolith. docs/ARCHITECTURE.md correctly keeps the nine stages in pipeline.py.","Item 6 checks asyncpg done. No module imports asyncpg; core/database.py assigns sync PostgresStateManager to async_state_manager, which /health/pipeline then calls.","docs/PITFALLS.md and docs/DEVELOPMENT.md require HF_HOME=/app/models on model_cache. docker-compose.yml uses the Hugging Face home path and mounts model_cache at /app/model_cache.","docs/ARCHITECTURE.md says intake hash-dedups and identity sets chunk_id. _stage_intake skips COMPLETED without get_existing_doc_hash, and _stage_identity only sets namespace VBPL.","The identity section says chunk_id doc_id::p{page}::{type}_{idx} is implemented. DocumentChunker.chunk_document leaves chunk_id unset, and the model comment says MD5 while get_file_hash is SHA-256.","Item 5 checks an atomic Redis Streams claim. claim_next reads only new ids, and a false claim_file drops the message with no ack and no XAUTOCLAIM."]}
```

---

### Subagent: `01a0e68f-ff8b-71f0-ad3a-2f6d13ce8330` (`01a0e68f`)

Live checks finished without editing the repo, installing packages, restarting Docker, or writing to Redis, Milvus, Postgres, or Neo4j. Pytest exited 1 on one catalog assertion. Flake8 exited 0 only because F401 and F821 are ignored. Compileall and the three requested imports succeeded. The pip script itself cannot run; conflicts below come from `python -m pip check`.

```json
{"pytest_command":"cd services/rag-service && timeout 420 ./venv/bin/pytest tests/ -q --tb=line -m 'not integration and not gpu'","pytest_exit_code":1,"pytest_summary":"FAILED tests/test_hub3_bridge.py::TestCatalogDiscovery::test_load_master_catalog_category_filter","pytest_failures":["tests/test_hub3_bridge.py::TestCatalogDiscovery::test_load_master_catalog_category_filter"],"flake8_command":"timeout 180 services/rag-service/venv/bin/flake8 services/rag-service --config=services/rag-service/.flake8","flake8_exit_code":0,"flake8_summary":"Exit 0 with no reported findings. This is not a clean bill: services/rag-service/.flake8 ignore includes F401 and F821, so unused imports and undefined names are hidden globally; per-file-ignores repeat F401 and F821 for tests.","flake8_ignored_codes":["E402","W291","W293","E501","E226","E241","E704","E741","F401","F841","F541","F811","F821","W503","W504","W391","E111","E117","E124","E127","E128","E129","E131","E231","E261","E302","E303","E305","E306","E401","E701"],"import_command":"cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service && timeout 180 ./venv/bin/python -m compileall -q -x 'venv|__pycache__|autoresearch/exports' ingestion retrieval core api repositories models; timeout 30 ./venv/bin/python -c 'import ingestion.models, ingestion.queue, retrieval.search_pipeline'","import_ok":true,"import_failures":[],"dependency_command":"cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service && timeout 120 ./venv/bin/python -m pip check","dependency_conflicts":["proto-plus 1.27.0 has requirement protobuf<7.0.0,>=3.19.0, but you have protobuf 7.34.1.","google-api-core 2.29.0 has requirement protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<7.0.0,>=3.19.5, but you have protobuf 7.34.1.","googleapis-common-protos 1.72.0 has requirement protobuf!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<7.0.0,>=3.20.2, but you have protobuf 7.34.1.","grpcio-reflection 1.78.0 has requirement protobuf<7.0.0,>=6.31.1, but you have protobuf 7.34.1.","grpcio-status 1.71.2 has requirement protobuf<6.0dev,>=5.26.1, but you have protobuf 7.34.1.","opentelemetry-proto 1.40.0 has requirement protobuf<7.0,>=5.0, but you have protobuf 7.34.1.","google-ai-generativelanguage 0.6.15 has requirement protobuf!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<6.0.0dev,>=3.20.2, but you have protobuf 7.34.1.","grpcio-health-checking 1.78.0 has requirement protobuf<7.0.0,>=6.31.1, but you have protobuf 7.34.1.","sglang 0.5.9 has requirement openai==2.6.1, but you have openai 2.26.0.","sglang 0.5.9 has requirement transformers==4.57.1, but you have transformers 4.57.5.","moviepy 2.2.1 has requirement pillow<12.0,>=9.2.0, but you have pillow 12.1.1.","yt-dlp 2024.4.9 has requirement websockets>=12.0, but you have websockets 10.4."],"limitations":["Pytest printed no N-failed/M-passed footer. pytest.ini addopts already passes -q and the command passed -q again, so pytest 9.0.2 verbosity is -2 and summary_stats() returns when verbosity < -1. Progress glyphs before FAILURES were 526 '.' and 1 'F'. The pytest process exit was 1, not 124; wall time was about 12.23s.","timeout 120 ./venv/bin/pip check exited 127: the script exists but its shebang is #!/home/vvc/Documents/dgx-spark-toolkit/services/rag-service/venv/bin/python3, and that interpreter is missing. Conflict lines are from timeout 120 ./venv/bin/python -m pip check, which exited 1. Nothing was installed.","Read requirements.txt, requirements-app.lock, and requirements-ci.txt: they name different versions or constraints for prometheus-fastapi-instrumentator, pillow, opencv-python-headless, watchdog, sentence-transformers, FlagEmbedding, surya-ocr, openpyxl, prometheus_client, pyyaml, numpy, tqdm, python-dotenv, fastapi, uvicorn, httpx, pydantic-settings, python-docx, sqlalchemy, psycopg2-binary, asyncpg, pymupdf, and pdfplumber. Also read requirements-ci.lock: opencv-python-headless==5.0.0.93 and watchdog==6.0.0 are outside the requirements.txt caps, pdfplumber==0.11.10 differs from app.lock 0.11.9, neo4j==5.23.1 differs from app.lock 5.26.0, and the CI lock has no PyYAML pin.","Installed pillow is 12.1.1 while requirements-app.lock pins pillow==12.3.0.","Importing retrieval.search_pipeline loads retrieval/__init__.py, reranker, sentence_transformers, transformers, and user-site torchao at /home/vvc/.local/lib/python3.12/site-packages/torchao/kernel/intmm.py, which printed import error: No module named 'triton' and continued. compileall and the three imports exited 0. main.py was not imported. No hang and no server was opened.","Did not start or stop Docker and did not write to Redis, Milvus, Postgres, or Neo4j. compileall only refreshed bytecode under the named packages."]}
```

---

### Subagent: `01a0e695-eac2-7921-aff4-48bf77f69e30` (`01a0e695`)

Đã ghi báo cáo 305 dòng tại `docs/architecture_audit_report.md`. Trạng thái Final Gate là chờ phản biện, với 17 đề xuất.

```json
{"wrote_file": true, "path": "/home/vvc/Codebase/dgx-spark-toolkit/docs/architecture_audit_report.md", "proposal_count": 17}
```

---

### Subagent: `01a0e69f-9cfb-79f3-b1d5-9f3f2eb4e2f9` (`01a0e69f`)

The report meets the acceptance shape: sections A–D are non-empty, NS1–NS8 each have a gap, evidence, and a cost, all 17 proposals carry the five labels and a named file in Giải pháp, the live counts match the live JSON, and no key or token value is present.

```json
{"verdict":"pass","required_changes":[]}
```

---

### Subagent: `01a0e69f-9cfb-79f3-b1d5-9f41bbb432b0` (`01a0e69f`)

The report’s North Star table has no Đạt row, and the nine stages are still methods on `DocumentIngestionPipeline` in `pipeline.py`, not files under `ingestion/stages/`. `ingest_file` calls synchronous `run_pipeline`, and nothing imports `asyncpg`. Those claims hold. Three sentences are stronger than the code.

```json
{"verdict":"revise","required_changes":["Tầng A — Ingestion Pipeline: delete «chỉ log warning» from the `_stage_indexing` sentence. A returned `{\"status\": \"failed\"}` is ignored with no log in that method; `logger.warning` runs only when `index_document_sync` raises or `document_store` is missing. Keep that the document is still returned and the worker still acknowledges.","Tầng C — Hạ tầng agent: downgrade «workflows trong catalog không thấy bằng grep tên khóa». `catalog.yaml` contains `workflows: []` — the key is present and the list is empty.","Tầng D — Vận hành: downgrade «/health chỉ fail khi Milvus, Neo4j hoặc warmup lỗi». `/health` is 503 unless Milvus and Neo4j are `ok` or `reconnected` (so `not initialized` fails) and warmup is `ready`, `skipped`, or `disabled` (so `pending` and `in_progress` fail). Keep that Redis and Postgres are checked only on `/health/pipeline`."]}
```

---

### Subagent: `01a0e69f-9cfc-7da1-9522-3dd968efa7a2` (`01a0e69f`)

The report at `docs/architecture_audit_report.md` is present and 305 lines. Headings `Tầng A` through `Tầng D` are present, and the North Star matrix contains `NS1` through `NS8`. All 17 `####` proposals include **Vấn đề**, **Bằng chứng**, **Giải pháp**, **Effort**, and **Rủi ro**. Pytest summary, flake8 exit 0, `import_ok` true, and the twelve dependency conflicts match the live JSON. These five evidence paths exist: `services/rag-service/ingestion/pipeline.py`, `services/rag-service/retrieval/search_pipeline.py`, `docker-compose.yml`, `.agents/ARCHITECTURE.md`, and `helm/dgx-spark-toolkit/values.yaml`. No secret-like value appears in the report.

```json
{"verdict":"pass","required_changes":[]}
```

---

### Subagent: `01a0e6a8-9bbb-7d13-acc5-31ab256a31ea` (`01a0e6a8`)

Đã cập nhật `docs/architecture_audit_report.md`. Cổng cuối là **Chưa đạt** vì `gates_clean` là false. Ba phán quyết được ghi nguyên văn: reviewer pass, challenger revise, forensic pass.

Ba chỗ challenger yêu cầu đã được hạ sau khi mở lại mã, không nâng hàng North Star và không thêm số test:

- Tầng A: dict `{"status": "failed"}` từ `index_document_sync` bị bỏ qua, không log trong `_stage_indexing`. `logger.warning` chỉ khi hàm ném exception hoặc thiếu `document_store`. Document vẫn được trả về và worker vẫn `acknowledge`.
- Tầng C: `catalog.yaml` có khóa `workflows` với giá trị `[]`.
- Tầng D: `/health` trả 503 trừ khi Milvus và Neo4j là `ok` hoặc `reconnected` và warmup là `ready`, `skipped` hoặc `disabled`. Redis và Postgres chỉ nằm ở `/health/pipeline`.

Năm nhãn đề xuất (**Vấn đề**, **Bằng chứng**, **Giải pháp**, **Effort**, **Rủi ro**) giữ nguyên trên 17 mục.

```json
{"wrote_file":true,"path":"/home/vvc/Codebase/dgx-spark-toolkit/docs/architecture_audit_report.md","proposal_count":17}
```

---

### Subagent: `01a0e6ab-3d7c-79e1-aaf9-1f8d849b840b` (`01a0e6ab`)

The report meets the confirming bar. Tầng A–D and NS1–NS8 are present, every proposal still has Vấn đề, Bằng chứng, Giải pháp, Effort, and Rủi ro, and the Final Gate is Chưa đạt while quoting reviewer pass, challenger revise, and forensic pass. The three challenger claims are corrected in Tầng A, C, and D, and the gate does not say Đạt.

```json
{"verdict":"pass","required_changes":[]}
```

---

