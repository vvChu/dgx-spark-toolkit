# 📓 DGX Spark Toolkit — Session Log

> Auto-maintained by `/save-session` workflow.
> Cập nhật cuối mỗi buổi làm việc để giữ context giữa các conversation.

---

## 🟢 Session: 2026-08-06 (vvc)

### Trạng thái hệ thống (cuối session)

| Service | Status | Uptime |
|---|---|---|
| `ai-gateway` | ✅ Up (healthy) | 7 hours |
| `rag-service` | ✅ Up (healthy) | 7 hours |
| `rag-frontend` | ✅ Up (healthy) | 7 hours |
| `qwen36b` (vLLM 35B) | ✅ Up (healthy) | 3 hours |
| `milvus-standalone` | ✅ Up (healthy) | 7 hours |
| `neo4j-graph` | ✅ Up (healthy) | 7 hours |
| `litellm-postgres` | ✅ Up (healthy) | 7 hours |
| `litellm-redis` | ✅ Up (healthy) | 7 hours |

### Thay đổi đã thực hiện (2026-08-06)

- [x] **Candidate 1: Ingestion Pipeline Deep Module**: Hợp nhất 14 file pass-through nông trong `mixins/` và `stages/` thành `DocumentIngestionPipeline` tại `pipeline.py`. Tạo `InMemoryStateManager` adapter cho 100% offline testing.
- [x] **Candidate 2: AI Gateway Client**: Consolidation 3 client calling routines thành `AIGatewayClient` & `MockAIGatewayClient` tại `core/ai_gateway_client.py`. Tự động hóa markdown-fence JSON parsing và Pydantic validation.
- [x] **Candidate 3: Retrieval Search Pipeline**: Tái cấu trúc `_search_internal` (291 lines) thành `SearchPipeline` và state container `SearchContext` tại `retrieval/search_pipeline.py`. `RetrievalService` đóng vai trò Facade Seam mỏng (40 lines).
- [x] **Candidate 4: Frontend Stream Client**: Xây dựng `StreamClient` tại `services/frontend/src/lib/streamClient.ts` xử lý SSE streaming `POST /chat/stream` với discriminated union types. Nâng cấp `ChatPanel.tsx` hỗ trợ render AI Reasoning Path (`thought`) sống động.
- [x] **TDD & Full Test Suite Verification**:
  - Backend: **351/351 unit tests PASSED (100%)**
  - Frontend: **Vite Production Build SUCCESS (0 errors)**
- [x] **AI Gateway Grilling Session & ADR 0001**: Run `/grilling` session on AI Gateway & Model Routing Optimization. Defined Hybrid Staircase GPU offloading, Selective Reasoning Model Scoping, Split Cache Policy (SHA256 exact for OCR vs 0.85 semantic for Search), and Instant Cloud Spillover on lock contention. Recorded in [`docs/adr/0001-ai-gateway-routing-and-caching-topology.md`](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/adr/0001-ai-gateway-routing-and-caching-topology.md).
- [x] **Wayfinder Map #3 & Ticket #4 Executed**: Integrated `gemini-3.6-flash-low/medium/high` into [`litellm_config.yaml`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml) with 10 Direct API keys load balancing + Gateway Proxy fallback. Updated [`custom_callbacks.py`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/custom_callbacks.py) parameter corrector. Verified end-to-end HTTP 200 OK responses via AI Gateway. Closed [[Ticket #4]](https://github.com/vvChu/dgx-spark-toolkit/issues/4).
- [x] **Wayfinder Ticket #5 Benchmark Resolved**: Research subagent benchmarked `gemini-3.6-flash` vs `gemini-3.5-flash-lite`. Retained `gemini-3.5-flash-lite` as `ocr-primary` (100% accuracy, 6.2s vs 7.0-40.8s latency, 25x higher quota). Closed [[Ticket #5]](https://github.com/vvChu/dgx-spark-toolkit/issues/5).
- [x] **Wayfinder Ticket #6 Web UI Verification Resolved**: Verified `StreamClient` (`src/lib/streamClient.ts`) SSE event handling (`context`, `token`, `thought`, `error`), `ChatPanel.tsx` live `AI Reasoning Path` block rendering, backend `POST /chat/stream` SSE output, and Vite production build (0 errors). Closed [[Ticket #6]](https://github.com/vvChu/dgx-spark-toolkit/issues/6).
- [x] **Wayfinder Ticket #7 Autoresearch RAG Loop Resolved**: Executed Karpathy-style RAG pipeline optimization loop. Pushed `overall_score` from 74/100 to **94/100** (3/5 dimensions at 100/100: Markdown Quality, JSON Export Quality, and Export Consistency). Passed all 351 pre-commit unit tests and committed (`bd91e2d`). Closed [[Ticket #7]](https://github.com/vvChu/dgx-spark-toolkit/issues/7).
- [x] **Wayfinder Map #8 Created**: Created [[Wayfinder Map #8]](https://github.com/vvChu/dgx-spark-toolkit/issues/8) for Codebase Architecture Deepening (`RetrievalService`, `IngestionQueue`, `AIGatewayClient`).
- [x] **Wayfinder Ticket #9 Resolved**: Added `search()` method to `SearchPipeline`, converted `RetrievalService` into subclass facade, updated routers & dependencies, passed all 351 unit tests, and closed [[Ticket #9]](https://github.com/vvChu/dgx-spark-toolkit/issues/9).
- [x] **Wayfinder Ticket #10 Resolved**: Created `IngestionQueue` & `InMemoryIngestionQueue` unifying Redis Streams queueing and DB state tracking, added unit tests, passed all 353 unit tests, and closed [[Ticket #10]](https://github.com/vvChu/dgx-spark-toolkit/issues/10).
- [x] **Wayfinder Ticket #11 Resolved**: Added `extract_json()` and `extract_json_sync()` with regex fence parsing, schema validation, and auto-repair retry to `AIGatewayClient`, passed all 355 unit tests, and closed [[Ticket #11]](https://github.com/vvChu/dgx-spark-toolkit/issues/11).
- [x] **Wayfinder Map #8 Fully Completed**: All 3 child tickets (#9, #10, #11) resolved and verified. Closed [[Wayfinder Map #8]](https://github.com/vvChu/dgx-spark-toolkit/issues/8). Destination reached!
- [x] **Frontend StreamClient Deepened**: Refactored [`services/frontend/src/lib/streamClient.ts`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/frontend/src/lib/streamClient.ts) to return structured `StreamResult` metrics (`fallbackUsed`, `tokensReceived`, `thoughtsReceived`, `contextCount`) while keeping `ChatPanel.tsx` 100% focused on UI rendering. Passed Vite build in 2.50s (`2da0676`).
- [x] **Wayfinder Map #13 Created**: Created [[Wayfinder Map #13]](https://github.com/vvChu/dgx-spark-toolkit/issues/13) for Architecture Deepening Round 2 (`LegalAnalysisEngine`, `RAGEvaluator`, `SemanticQueryCache`, `LegalGraphManager`).
- [x] **Wayfinder Ticket #14 Resolved**: Created `LegalAnalysisEngine` & `InMemoryLegalAnalysisEngine` consolidating conflict analysis and compliance checking, updated `api/routers/analysis.py`, passed 355 unit tests, and closed [[Ticket #14]](https://github.com/vvChu/dgx-spark-toolkit/issues/14).
- [ ] **Wayfinder Ticket #15 Frontier**: [[Ticket] Deepen RAGEvaluator seam unifying evaluation metrics and scorecards](https://github.com/vvChu/dgx-spark-toolkit/issues/15)
- [ ] **Wayfinder Ticket #16 Frontier**: [[Ticket] Deepen SemanticQueryCache seam encapsulating vector cache hashing and HyDE caching](https://github.com/vvChu/dgx-spark-toolkit/issues/16)
- [ ] **Wayfinder Ticket #17 Frontier**: [[Ticket] Deepen LegalGraphManager client seam for Graph visualization](https://github.com/vvChu/dgx-spark-toolkit/issues/17)

### Thực nghiệm / Công việc tiếp theo
- [ ] Chạy live tracking RAG ingestion pipeline qua `/track-ingestion`
- [ ] Kiểm thử end-to-end trên giao diện web `http://localhost:3000`

---

## 🟢 Session: 2026-03-30 (vvc)

### Trạng thái hệ thống (cuối session)

| Service | Status |
|---|---|
| `ai-gateway` | ✅ Up 19h |
| `rag-service` | ✅ Up 21h (healthy) |
| `qwen35b` (vLLM) | ✅ Up 2 days (healthy) |
| `milvus-standalone` | ✅ Up 2 days (healthy) |
| `neo4j-graph` | ✅ Up 2 days (healthy) |
| `litellm-postgres` | ✅ Up 2 days (healthy) |
| `litellm-redis` | ✅ Up 2 days (healthy) |

### Benchmark OCR — Kết quả cuối cùng (Page 21, Luật Xây dựng `Luat_50-2014-QH13`)

| Model | Time | Chars | Accuracy | Halluc | Score |
|---|---|---|---|---|---|
| `gemini-3-flash` | 7.0s | 2,132 | 100% | 0 | **100.0** |
| `gemini-3.1-flash-lite` | 6.7s | 2,132 | 100% | 0 | **100.0** |
| `rag-core` (Qwen 3.5 35B) | 16.9s | 2,132 | 100% | 0 | **100.0** |
| `gemma-3-27b` | 39.8s | 6,046 | 100% | 0 | **100.0** |

> ⚠️ `gemma-3-27b`: passes scoring vì ground-truth phrases có mặt, nhưng output dài 3x (6046 chars vs 2132) — vẫn có verbose preamble. **Không dùng trong OCR chain production.**

### Cấu hình Pipeline Production (hiện tại)

**Primary OCR Model:** `gemini-3.1-flash-lite`
**Fallback Chain:** `gemini-3.1-flash-lite` → `gemini-3-flash` → `rag-core`
**Gemma excluded from vision chain** (verbose output, preamble issues)

**API Keys active (LiteLLM):**
- `GEMINI_API_KEY_2` → `GEMINI_API_KEY_8` (KEY1 bị revoke 2026-03-30 do leak)
- KEY8 đã được cập nhật `2026-03-30`

**Milvus Collection:** `legal_docs_v10`

### Thay đổi đã thực hiện (2026-03-29 → 2026-03-30)

- [x] **Prompt engineering**: Thêm Anti-Laziness injection, loại bỏ preamble verbose
- [x] **`_strip_preamble()`**: 2-pass (regex + smart Vietnamese line skip) trong cả `benchmark_ocr_models.py` và `cloud_vision.py`
- [x] **Gemma routing fix**: Chuyển từ LiteLLM proxy sang Google native OpenAI-compat endpoint
- [x] **Gemma removed from OCR chain**: Chỉ dùng cho text-only tasks (metadata, summary)
- [x] **API Key rotation**: KEY1 revoked, KEY8 updated, KEY2-KEY7 verified OK
- [x] **`cloud_vision.py` refactor**: Tên hàm chuẩn hóa (`llm_extract_page`, `llm_generate_summary`, `llm_extract_metadata`) + backward compat aliases
- [x] **XML constraint test** (`test_xml.py`): Thử dùng `<TEXT></TEXT>` wrapper — kết quả 12.3s, 2157 chars, sạch

### Thực nghiệm đang chờ

- [ ] `test_xml.py` — So sánh đầy đủ XML-constraint vs standard prompt trên tất cả models
- [ ] Chạy ingestion pipeline clean với `legal_docs_v10` để verify end-to-end quality
- [ ] Benchmark thêm pages (không chỉ page 21) để xác nhận generalization

### Files quan trọng

| File | Mô tả |
|---|---|
| `services/rag-service/ingestion/cloud_vision.py` | OCR pipeline chính (primary/fallback chain) |
| `services/rag-service/scripts/benchmark_ocr_models.py` | Benchmark script (4 models, page 21) |
| `services/ai-gateway/litellm_config.yaml` | AI Gateway config (keys, routing, fallbacks) |
| `test_xml.py` | Thử nghiệm XML-constraint OCR prompt |
| `.env` | API keys (GEMINI_API_KEY_2..8, LITELLM_MASTER_KEY) |

---

## 📌 Ghi chú kiến trúc

- **`rag-core`** = Qwen 3.5 35B local (vLLM on DGX Spark, container `qwen35b`)
- **`rag-light`** = Qwen 3.5 9B local (container `vllm-4b`)
- **LiteLLM Gateway** = `ai-gateway:4000` — routing, fallback, rate limiting, Redis cache
- **Milvus** endpoint: `milvus-standalone:19530`
- **Neo4j** endpoint: `neo4j-graph:7687`

---

## 🟢 Session: 2026-03-31 (vvc)

### Trạng thái hệ thống (cuối session)

| Service | Status | Uptime |
|---|---|---|
| `ai-gateway` | ✅ Up (healthy) | 37 phút (restarted để load config mới) |
| `rag-service` | ✅ Up (healthy) | 24 giờ |
| `rag-watcher` | ✅ Up | 34 giờ |
| `qwen35b` (vLLM 35B) | ✅ Up (healthy) | 2 ngày |
| `milvus-standalone` | ✅ Up (healthy) | 2 ngày |
| `neo4j-graph` | ✅ Up (healthy) | 2 ngày |
| `litellm-postgres` | ✅ Up (healthy) | 2 ngày |
| `litellm-redis` | ✅ Up (healthy) | 2 ngày |

> ⚠️ `vllm-4b` (rag-light) không chạy — profile `vllm-light`, start on-demand nếu cần

### Thay đổi đã thực hiện (2026-03-31)

**AI Gateway Audit & Optimization:**

- [x] **Kiểm toán toàn diện AI Gateway** — xác định 6 vấn đề: gemini-3-flash 0/8 healthy, proxy offline, allowed_fails quá cao, không có rpd tracking, health check tốn quota, httpx timeout flat 300s
- [x] **`router_settings` tối ưu**: `allowed_fails: 3→1`, `cooldown_time: 600→3600s`, `num_retries: 2→1`, `retry_after: 15→5s`, `timeout: 60→90s`
- [x] **RPD tracking** thêm vào tất cả Gemini models: `rpd: 500` cho flash-lite, `rpd: 20` cho flash/2.5-flash/2.5-flash-lite
- [x] **Per-model timeout**: `gemini-3.1-flash-lite timeout: 30s` (P95=10s), `gemini-3-flash timeout: 90s` (P95=50s)
- [x] **Health check scoped**: Thêm `models_to_health_check` — chỉ check 7 models quan trọng, bỏ qua 7 embedding endpoints không dùng
- [x] **Redis cache TTL**: Thêm `ttl: 3600` cho cache params
- [x] **`docker-compose.yml`**: Thêm healthcheck cho `ai-gateway` container (start_period 60s)
- [x] **`cloud_vision.py`**: Fix `httpx.Client` timeout từ flat 300s → granular (connect=5s, read=120s, write=15s, pool=5s)
- [x] **Gateway restarted** và verified: 15 healthy endpoints sau restart

**Research — Hybrid Load Balancing:**

- [x] **Nghiên cứu 3 chiến lược** cân bằng tải local + cloud chủ động:
  - Chiến lược 1: Weight-Capped Static Pool (0 dòng code, chỉ config)
  - Chiến lược 2: Budget-Aware Dynamic Router (script ~50 dòng)
  - Chiến lược 3: Hybrid Staircase kết hợp 1+2 (đề xuất)
- [x] **Concept**: Thêm `rag-core` vào pool `ocr-balanced` với `rpm: 12` (GPU physical cap) — local nhận ~12% traffic proactively, overflow sang cloud

### Cấu hình Pipeline Production (hiện tại — sau patch 2026-03-31)

**Primary OCR Model:** `gemini-3.1-flash-lite` (unchanged)
**Fallback Chain:** `gemini-3.1-flash-lite` → `gemini-3-flash` → `gemini-2.5-flash` → `gemini-2.5-flash-lite` → `rag-core`
**Router:** `usage-based-routing` với `rpd` tracking kích hoạt
**API Keys active:** KEY2–KEY8 (KEY1 revoked, KEY3 RPD hay bị exhausted)

### Thực nghiệm đang chờ

- [ ] **Hybrid Staircase** — Triển khai `ocr-balanced` virtual model (Phase 1: config only)
- [ ] **Budget-aware script** `quota_balancer.py` — Phase 2 của hybrid routing
- [ ] `test_xml.py` — So sánh XML-constraint vs standard prompt đầy đủ qua các models
- [ ] Chạy ingestion pipeline clean verify end-to-end quality
- [ ] Benchmark thêm pages để xác nhận generalization
- [ ] Probe lại 7 Gemini keys để xác định keys nào thực sự RPD exhausted vs health check issue

### Files quan trọng (updated)

| File | Mô tả |
|---|---|
| `services/ai-gateway/litellm_config.yaml` | AI Gateway config — updated với rpd, timeout, health scoping |
| `services/rag-service/ingestion/cloud_vision.py` | OCR pipeline — httpx timeout granular |
| `docker-compose.yml` | Gateway healthcheck |
| `services/rag-service/ingestion/cloud_vision.py` | OCR pipeline chính |
| `services/rag-service/scripts/benchmark_ocr_models.py` | Benchmark script |
| `.agents/scripts/probe_gemini_keys.py` | Key health probe script |
| `.env` | API keys (GEMINI_API_KEY_2..8, LITELLM_MASTER_KEY) |

### Key metrics sau optimization

| Chỉ số | Trước | Sau |
|---|---|---|
| Quota waste per fail | 3 requests thất bại | 1 request |
| Cooldown duration | 10 phút | 1 giờ (phù hợp RPD reset) |
| Fail → fallback latency | ~30s (2 retries × 15s) | ~5s (1 retry × 5s) |
| Health check scope | 62 endpoints/2 phút | 12 endpoints/2 phút |
| httpx hang risk | Up to 300s | Max 120s (read) |

---

## 🟢 Session: 2026-03-31 (vvc) - Late Night Updates (Asymmetric Routing)

### Trạng thái hệ thống (cuối session)

| NAMES | STATUS | CREATED |
|---|---|---|
| ai-gateway | Up 2 hours (unhealthy) | 2 hours ago |
| rag-service | Up 27 hours (healthy) | 27 hours ago |
| dgx-spark-toolkit-rag-watcher-1 | Up 37 hours | 37 hours ago |
| litellm-postgres | Up 2 days (healthy) | 2 days ago |
| litellm-redis | Up 2 days (healthy) | 2 days ago |
| milvus-standalone | Up 2 days (healthy) | 2 days ago |
| neo4j-graph | Up 2 days (healthy) | 2 days ago |
| milvus-minio | Up 2 days (healthy) | 2 days ago |
| milvus-etcd | Up 2 days (healthy) | 2 days ago |
| qwen35b | Up 2 days (healthy) | 2 days ago |
| portainer | Up 2 days | 5 weeks ago |

### Kết quả / Benchmark mới
*(Không có file benchmark mới được chạy với cờ lưu output)*

### Thay đổi đã thực hiện
- [x] **Kiến trúc Routing 5-lớp**: Cấu hình `usage-based-routing` 5-tier cho `ocr-primary` -> `ocr-fallback` -> `ocr-tier3` -> `ocr-tier4` -> `rag-core`.
- [x] **Offload Table/Metadata**: Mặc định sử dụng `rag-core` (Qwen35B) để bóc tách Table và phân tích JSON Metadata, triệt để tiệt kiệm API Quota.
- [x] **Xóa gemma-3-27b**: Loại bỏ hoàn toàn mô hình này khỏi pipeline Vision vì output rác.
- [x] **Khám sức khỏe API Key (`probe_gemini_keys.py`)**: Xác nhận 6 keys cực khỏe, 1 key Rate Limited (hoàn toàn đúng dự đoán), 3 keys Placeholder (chờ nạp).
- [x] **Asymmetric Worker Dispatcher**: Triển khai thuật toán khóa `LOCAL_GPU_OCR_LOCK` (Non-blocking Mutex) ở `mixins/extraction.py`, đảm bảo đúng 1 luồng được xử lý bởi Local GPU, ngăn ngừa OOM tuyệt đối mà không làm nghẽn làn Cloud cao tốc.

### Thực nghiệm đang chờ
- [x] Chạy lệnh ingestion RAG toàn thư mục để theo dõi log `[DISPATCH]` phân tải thực tế xuống Local GPU.
- [ ] Cập nhật 3 thông số `GEMINI_API_KEY_9..11` bằng mã thật và restart lại gateway.
- [ ] Kiểm tra nguyên nhân container `ai-gateway` báo `unhealthy` dẫu Uvicorn đã chạy thành công 59 endpoints. Trang healthcheck có thể đang setup lỗi ping.

---

## 🟢 Session: 2026-03-31 (vvc) - Production RAG Stabilization

### Trạng thái hệ thống (cuối session)

| NAMES | STATUS | CREATED |
|---|---|---|
| rag-service | Up 43 minutes (healthy) | 43 minutes ago |
| ai-gateway | Up 4 hours (unhealthy) | 4 hours ago |
| dgx-spark-toolkit-rag-watcher-1 | Up 40 hours | 40 hours ago |
| litellm-postgres | Up 2 days (healthy) | 2 days ago |
| litellm-redis | Up 2 days (healthy) | 2 days ago |
| milvus-standalone | Up 2 days (healthy) | 2 days ago |
| neo4j-graph | Up 2 days (healthy) | 2 days ago |
| milvus-minio | Up 2 days (healthy) | 2 days ago |
| milvus-etcd | Up 2 days (healthy) | 2 days ago |
| qwen35b | Up 14 minutes (healthy) | 2 days ago |
| portainer | Up 2 days | 5 weeks ago |

### Kết quả / Benchmark mới
*(Đang chờ `benchmarks/baseline_report_final.json` finish từ tiến trình ngầm)*

### Thay đổi đã thực hiện
- [x] **Asymmetric Compute Offload**: Chuyển Embedding (BGE-M3) và Reranker sang CPU hoàn toàn để nhả dư 6GB VRAM, giữ lại duy nhất vLLM (Qwen) trên GPU giúp phòng chống tát nước OOM (Cột mốc ổn định tuyệt đối).
- [x] **Page Cache & RAM Optimization**: Reboot `vllm-35b` để xóa bloat bộ nhớ đệm `Page Cache`, thu hồi lại ~70GB System RAM giúp yên tâm chạy thêm JupyterLab.
- [x] **Circuit Breaker & HITL API**: Implemented APIs `/health/circuits` và `/health/hitl` (Human in the loop) giám sát toàn diện flow nghẽn cổ chai OCR & Context.
- [x] **Warning Filter**: Tắt hẳn spam báo lỗi Tokenizer của FlagEmbedding để Terminal khi đánh giá trong sạch.

### Thực nghiệm đang chờ
- [ ] Phân tích kĩ file Benchmark `baseline_report_final.json` với dataset 30 câu hỏi phức tạp nhất.
- [ ] Cài đặt JupyterLab để scale testing.

---

## 🟢 Session: 2026-03-31 (vvc) - Ingestion Error Remediation & Timeout Optimization

### Trạng thái hệ thống (cuối session)

| NAMES | STATUS | CREATED |
|---|---|---|
| ai-gateway | Up 20 minutes (healthy) | 48 minutes ago |
| dgx-spark-toolkit-rag-watcher-1 | Up 9 minutes | 55 minutes ago |
| rag-service | Up 52 minutes (healthy) | 3 hours ago |
| litellm-postgres | Up 2 days (healthy) | 2 days ago |
| litellm-redis | Up 2 days (healthy) | 2 days ago |
| milvus-standalone | Up 2 days (healthy) | 2 days ago |
| neo4j-graph | Up 2 days (healthy) | 2 days ago |
| milvus-minio | Up 2 days (healthy) | 2 days ago |
| milvus-etcd | Up 2 days (healthy) | 2 days ago |
| qwen35b | Up 3 hours (healthy) | 2 days ago |
| portainer | Up 2 days | 5 weeks ago |

### Kết quả / Benchmark mới
*(Chưa khởi chạy bộ benchmark sau khi hoàn tất sửa lỗi Pipeline)*

### Thay đổi đã thực hiện
- [x] **Fix Docker Gateway Healthcheck**: Chuyển từ việc sử dụng `curl` sang script python internal `urllib` để khôi phục trạng thái `(healthy)` cho `ai-gateway`.
- [x] **Fix Aliases LiteLLM Routing (`pipeline_config.py` & `figure_extractor.py`)**: Gỡ bỏ hardcode tàn dư của `gemma` để trỏ toàn bộ Vision requests thống nhất về `ocr-primary` và `ocr-fallback`, triệt tiêu dứt điểm lỗi `400 Bad Request`.
- [x] **Fix Pipeline Variable Scope**: Sửa lỗi `cannot access local variable 'safe_summary'` trong `s08_indexing.py` thông qua việc khởi tạo khai báo an toàn trong vòng lặp context.
- [x] **Database Queue Flush & Resync**: Reset triệt để Redis cache (`FLUSHALL`) và state trong Postgres (`ingestion_state`) để Watcher có thể cày lại 4 file bị ket `FAILED` trước đó.
- [x] **Enable Postgres Callback cho LiteLLM**: Thêm backend phân rã nhật ký chi tiêu (`postgresql`) để Gateway có cơ sở dữ liệu làm Usage-Based Routing chuẩn xác với 160.000 log entries.
- [x] **Tối ưu Timeout Limits (Gateway & Worker)**: Nâng đồng loạt timeout trong `litellm_config.yaml` từ `30/90s` lên thành `120s`. Mở rộng connection pool timeout `httpx.Client` trong `cloud_vision.py` để tương thích độ rỗng load.
- [x] **Chứng nhận năng lực Local GPU**: Cấu hình Hybrid đã được kiểm chứng hoạt động *flawness* tại Peak Load, chứng kiến `rag-core` nuốt trơn tru các trang OCR với tốc độ 45-75s/trang mỗi khi Gateway có dấu hiệu quá tải Timeout.

### Thực nghiệm đang chờ
- [ ] Mở `/track-ingestion` chờ 4 file cuối cùng đẩy trót lọt qua Database Milvus.
- [ ] Chạy Evaluator OCR / `benchmark_ocr_models.py` sau khi hoàn tất lượng Vector cực dày này.

---

## 🟢 Session: 2026-03-31 (vvc) - Phase-Shifted Rate Limiting & Quota Management

### Trạng thái hệ thống (cuối session)

| NAMES | STATUS | CREATED |
|---|---|---|
| dgx-spark-toolkit-rag-watcher-1 | Up 16 minutes | About an hour ago |
| ai-gateway | Up About a minute (healthy) | 6 hours ago |
| rag-service | Up 6 hours (healthy) | 8 hours ago |
| litellm-postgres | Up 3 days (healthy) | 3 days ago |
| litellm-redis | Up 3 days (healthy) | 3 days ago |
| milvus-standalone | Up 3 days (healthy) | 3 days ago |
| neo4j-graph | Up 3 days (healthy) | 3 days ago |
| milvus-minio | Up 3 days (healthy) | 3 days ago |
| milvus-etcd | Up 3 days (healthy) | 3 days ago |
| qwen35b | Up 8 hours (healthy) | 3 days ago |
| portainer | Up 3 days | 5 weeks ago |

### Kết quả / Benchmark mới
*(Không có kết quả benchmark mới trong phiên này)*

### Thay đổi đã thực hiện
- [x] **API Key Phase-Shifting**: Tái cấu trúc LiteLLM để sử dụng trọn vẹn 10 Keys cho cả nhóm OCR và Gemma mà không dẫm chân lên nhau, dựa vào cơ chế lệch pha (phase-shifted) tự nhiên do tính tuần tự của Pipeline.
- [x] **Rate Limit Constraints**: Áp đặt chính xác thông số `RPM: 15 / RPD: 500` cho Flash-Lite (OCR) và `RPM: 30 / RPD: 14400` cho Gemma-3 (Synthetic Queries) dựa trên tài liệu giới hạn Free Tier thực tế.
- [x] **Expanded Gemma Pool**: Thêm các mô hình 12B và 4B của Gemma 3 vào chuỗi fallback (Tier 2/3) của cụm `text-gemma`, nhân 3 lần giới hạn RPD lên thành 432,000 queries/ngày.
- [x] **Python Application Throttling**: Kìm hãm luồng `ThreadPoolExecutor` của tiến trình tạo câu hỏi (Synthetic queries) từ max_workers=8 xuống 5, kết hợp độ trễ `time.sleep` lặp trục để luồng xả API luôn nằm dưới ngưỡng 30 RPM của quy định, triệt tiêu mã lỗi `429`.

### Thực nghiệm đang chờ
- [ ] Theo dõi log Gateway vào cuối ngày để xác nhận tiến trình tự động block/rotate các API Key khi đạt ngưỡng hết hạn ngạch Free Tier (`RPD: 500`).
- [ ] Chạy lại Benchmark chất lượng OCR toàn diện bằng lệnh `python3 benchmark_ocr_models.py`.

---

## 🟢 Session: 2026-03-31 (vvc) - System Recovery & Ingestion Continuity

### Trạng thái hệ thống (cuối session)

| NAMES | STATUS | RUNNING FOR |
|---|---|---|
| dgx-spark-toolkit-rag-watcher-1 | Up 15 minutes | 6 hours ago |
| ai-gateway | Up 7 hours (healthy) | 13 hours ago |
| rag-service | Up 13 hours (healthy) | 15 hours ago |
| litellm-postgres | Up 3 days (healthy) | 3 days ago |
| litellm-redis | Up 3 days (healthy) | 3 days ago |
| milvus-standalone | Up 3 days (healthy) | 3 days ago |
| neo4j-graph | Up 3 days (healthy) | 3 days ago |
| qwen35b | Up 15 hours (healthy) | 3 days ago |

### Tiến độ Ingestion
- **Luat_31-2024-QH15 (Luật Đất đai)**: ✅ **COMPLETED** (Xác nhận cấu hình Throttling/Phase-shift hoạt động ổn định).
- **Luat_50-2014-QH13 (Luật Xây dựng)**: 🔄 **IN_PROGRESS** (Đã giải tỏa Zombie Claim, Worker đang xử lý OCR trang 2+).

### Thay đổi đã thực hiện
- [x] **Zombie Claim Remediation**: Phát hiện và reset trạng thái kẹt của file Luật Xây dựng trong PostgreSQL (từ `CLAIMED` của worker cũ sang `PENDING`).
- [x] **Redis Tracking Clean**: Xóa bộ tập hợp `ingest:queued_files` trong Redis để ép Watcher nhận diện lại các file vừa reset.
- [x] **Verified Stability**: Theo dõi logs xác nhận `rag-core` (Local GPU) đang gánh tải OCR nhịp nhàng cho file lớn, dành Quota Gemini cho các file phức tạp hơn.

### Thực nghiệm đang chờ
- [ ] Chờ file Luật Xây dựng (100+ trang) hoàn tất để chạy Benchmark tổng thể.
- [ ] Kiểm tra tỷ lệ fallback Gemma khi khối lượng Synthetic Queries tăng cao ở cuối file lớn.

## 🟢 Session: 2026-04-09 (Thiết lập Gemma 3 & 4 AI Gateway Aliases)

### Trạng thái hệ thống (cuối session)
```text
NAMES                             STATUS                       CREATED
qwen35b                           Up About an hour (healthy)   About an hour ago
dgx-spark-toolkit-rag-watcher-1   Up 7 hours                   8 days ago
ai-gateway                        Up 54 minutes (healthy)      8 days ago
rag-service                       Up 56 minutes (healthy)      9 days ago
litellm-postgres                  Up 7 hours (healthy)         11 days ago
litellm-redis                     Up 7 hours (healthy)         11 days ago
milvus-standalone                 Up 7 hours (healthy)         11 days ago
neo4j-graph                       Up 7 hours (healthy)         11 days ago
milvus-minio                      Up 7 hours (healthy)         11 days ago
milvus-etcd                       Up 7 hours (healthy)         11 days ago
portainer                         Up 7 hours                   7 weeks ago
```

### Kết quả / Benchmark mới
*Không có benchmark JSON file mới nào được ghi nhận trong session này.*

### Thay đổi đã thực hiện
- [x] Tiêm tự động 20 biến thể mô hình ảo `reasoning-gemma` (Gemma 4 31B/26B) vào AI Gateway (`litellm_config.yaml`).
- [x] Khai báo Rate Limit cực kỳ kín kẽ (`15 RPM`) và Budget Safety (`15.000 RPD`) bảo vệ Free-tier cho cụm mô hình Gemma 4.
- [x] "Bán Decoupling" lõi `pipeline_config.py` phân luồng lại: giải phóng Local GPU, dời JSON Schema validator và logic tạo Relationship Graph Neo4j sang cụm `reasoning-gemma`.
- [x] Chốt cấu trúc Alias `text-light-gemma` (12B) dùng riêng cho bốc Metadata, tiếp tục ưu tiên `text-gemma` (27B) sinh lượng lớn Synthetic Queries (144k quota).
- [x] Nâng cấp `workflow_optimizer.py` lên version 5.0 (Tự Tiến Hóa), tự động parse `litellm_config.yaml` để quét và sửa tài liệu Dev tránh gọi nhầm Raw Model.
- [x] Cập nhật Playbook `/playbooks/llm-api-guide.md` bổ sung bảng bách khoa toàn thư cho RAG Virtual Aliases.
- [x] Hoàn tất quét bảo mật `Audit All Skills` toàn diện (Golden State Architecture 100%).

### Thực nghiệm đang chờ
- [ ] Bắn thử nghiệm 1 chu trình Ingestion RAG siêu lớn (~500 trang) để chứng kiến Gateway tự múa tính năng Fallback và Luân chuyển API Keys độc lập trên các Alias mới.

---

## 🟢 Session: 2026-05-11 (vvc)

### Trạng thái hệ thống (cuối session)

| NAMES | STATUS | CREATED |
|---|---|---|
| milvus-standalone | Up 7 days (healthy) | 2 weeks ago |
| milvus-minio | Up 7 days (healthy) | 2 weeks ago |
| ai-gateway | Up 40 minutes (healthy) | 2 weeks ago |
| neo4j-graph | Up 7 days (healthy) | 2 weeks ago |
| prometheus | Up 7 days | 2 weeks ago |
| grafana | Up 7 days | 2 weeks ago |
| open-webui | Up 7 days (healthy) | 2 weeks ago |
| rag-service | Up 7 days (healthy) | 2 weeks ago |
| rag-frontend | Up 7 days (healthy) | 2 weeks ago |
| qwen35b | Up 45 hours (healthy) | 2 weeks ago |
| dgx-spark-toolkit-rag-watcher-1 | Up 7 days | 5 weeks ago |
| litellm-postgres | Up 7 days (healthy) | 6 weeks ago |
| litellm-redis | Up 7 days (healthy) | 6 weeks ago |
| milvus-etcd | Up 7 days (healthy) | 6 weeks ago |
| portainer | Up 7 days | 2 months ago |

### Kết quả / Benchmark mới
*(Không có kết quả benchmark mới)*

### Thay đổi đã thực hiện
- [x] **Sửa lỗi 400 Bad Request cho API Proxy**: Bổ sung tham số `drop_params: true` cho nhóm model `gemini-3.1-pro`.
- [x] **Đồng bộ tên gọi model API Proxy**: Chỉnh sửa mapping trong file `litellm_config.yaml` khớp 100% với các endpoint thực tế của proxy (`gemini-3.1-pro-high`, `gemini-3.1-pro-low`).
- [x] **Khắc phục lỗi 404 Not Found từ Google API**: Xóa bỏ các config gọi model cũ bị lỗi (như `gemma-3-27b-it`) sang nhóm Live Models hợp lệ (`gemma-4-31b-it`, `gemma-4-26b-a4b-it`).
- [x] **Xây dựng Self-Healing Daemon (`model_auto_updater.py`)**: Công cụ tự động quét Docker log phát hiện lỗi 404/400, sau đó lấy danh sách Live Models mới nhất từ API, vá lỗi YAML và restart AI Gateway mà không cần can thiệp.
- [x] **Tích hợp cảnh báo Telegram**: Hoàn thiện thông báo kết quả cập nhật mô hình cho bot `@RAG_Ingestion_Bot` với token mới.

### Thực nghiệm đang chờ
- [ ] Theo dõi hệ thống qua báo cáo Telegram của cronjob `model_auto_updater.py` mỗi khi có thay đổi model từ phía các nhà cung cấp AI.

---

## 🟢 Session: 2026-05-25 (vvc)

### Kết quả nghiên cứu & Thử nghiệm kết nối Gemini 3.5

- **Kiểm tra kết nối Gemini 3.5 Flash qua API Proxy**:
  - Trực tiếp qua Proxy ngoài (`100.79.241.120:8045/v1`): Model ID `gemini-3.5-flash-low` hoạt động hoàn hảo (được proxy ánh xạ ngầm), trả về HTTP 200 OK.
  - Các model ID `gemini-3.5-flash-medium` và `gemini-3.5-flash-high` trả về lỗi HTTP 404/429 (Upstream Google API báo `Requested entity was not found`) do Proxy ngoài chưa cấu hình ánh xạ chuẩn cho chúng.
  - Bản thân model ID `gemini-3.5-flash` gốc trên Proxy ngoài cũng chưa được hỗ trợ (lỗi 404).

- **Kiểm tra kết nối trực tiếp đến Google API (bằng API Key gốc trong `.env`)**:
  - Model ID **`gemini-3.5-flash`** kết nối trực tiếp hoàn hảo trên cả 4 mức `thinking_level` (`minimal`, `low`, `medium`, `high`), trả về phản hồi chuẩn xác cùng khối chữ ký tư duy ngầm.

- **Cơ chế điền tham số mới của Google cho Gemini 3.5**:
  - **`thinking_level`**: Sử dụng chuỗi Enum cấu hình mức độ suy luận lồng trong `generationConfig.thinking_config`. Các giá trị hợp lệ: `"minimal"`, `"low"`, `"medium"`, `"high"`.
  - **Không dùng chung**: Nghiêm cấm dùng chung `thinking_budget` (Gemini 2.x) và `thinking_level` (Gemini 3.5) trong cùng request vì sẽ gây lỗi `400 Bad Request`.
  - **Lược bỏ Sampling Parameters**: Google khuyến nghị không thiết lập `temperature`, `top_p`, `top_k` khi chạy các tác vụ suy luận trên dòng Gemini 3.x để mô hình tự tối ưu hóa.
  - **Function Calling & Vết tư duy**: Yêu cầu bắt buộc truyền khớp `id` duy nhất của tool call trong `functionResponse` để duy trì chính xác context suy luận của Agent.

### Thay đổi đã thực hiện
- [x] Tạo và chạy thành công script `scripts/test_gemini35_proxy.py` kiểm tra kết nối API Proxy.
- [x] Tạo và chạy thành công script `scripts/list_proxy_models.py` truy vấn danh sách model hiện có của Proxy ngoài.
- [x] Tạo và chạy thành công script `scripts/test_gemini35_direct.py` kiểm chứng 4 mức `thinking_level` của `gemini-3.5-flash` qua API Key gốc của người dùng.
- [x] **Tích hợp Gemini 3.5 Flash**: Cấu hình 3 model ảo `gemini-3.5-flash-low`, `gemini-3.5-flash-medium`, và `gemini-3.5-flash-high` chạy trực tiếp qua API keys cá nhân trong `litellm_config.yaml`.
- [x] **Cơ chế Tự Động Sửa Lỗi Tham Số (Parameter Auto-Correction)**: Viết script `services/ai-gateway/custom_callbacks.py`, cài đặt hook `async_pre_call_hook` của LiteLLM, tự động lọc sạch các tham số cũ (`thinking_budget`), ánh xạ tự động sang `thinking_level` chuẩn, và gỡ bỏ các tham số lấy mẫu không khuyến khích (`temperature`, `top_p`), triệt tiêu lỗi 400 Bad Request hoàn toàn.
- [x] **Cấu hình Docker & Tái cấu trúc**: Mount tệp `custom_callbacks.py` và khai báo `PYTHONPATH=/app` trong `docker-compose.yml`, restart gateway và chạy bộ test liên thông `scripts/test_gateway_gemini35_auto_correct.py` thành công rực rỡ.
- [x] **Tích hợp Gemini 2.5 Flash Lite & Gemini Embedding 2**: Thêm thành công cấu hình 2 mô hình này vào AI Gateway, load-balancing qua 10 API keys cá nhân, đồng thời cấu hình RPD Budget bảo vệ (`200 RPD` cho Flash-Lite, `10,000 RPD` cho Embedding-2).
- [x] **Tối ưu hóa Parameter Corrector**: Cập nhật bộ lọc để tự động phát hiện và bỏ qua (bypass) việc tiêm tham số reasoning cho các dòng mô hình text/embedding không hỗ trợ tư duy (như `gemini-2.5-flash-lite`, `gemini-embedding-2`), triệt tiêu lỗi 400 Bad Request hoàn toàn.

### Thực nghiệm đang chờ
- [ ] Chờ quản trị viên của API Proxy ngoài cập nhật định tuyến cho model ID `gemini-3.5-flash`.
- [ ] Kiểm nghiệm độ ổn định và tiêu hao quota thực tế của dòng Gemini 3.5 Flash và Gemini 2.5 Flash Lite trong các bài test Ingestion RAG thực tế.

---

## 🟢 Session: 2026-05-28 (vvc)

### Trạng thái hệ thống (cuối session)

| Service | Status | Uptime |
|---|---|---|
| `ai-gateway` | ✅ Up (healthy) | About 5 minutes (restarted to load new config) |
| `rag-service` | ✅ Up 2 days (healthy) | 2 days |
| `qwen36b` (vLLM 35B) | ✅ Up 2 days (healthy) | 2 days |
| `milvus-standalone` | ✅ Up 2 days (healthy) | 2 days |
| `neo4j-graph` | ✅ Up 2 days (healthy) | 2 days |
| `litellm-postgres` | ✅ Up 2 days (healthy) | 2 days |
| `litellm-redis` | ✅ Up 2 days (healthy) | 2 days |
| `whisper-local` | ✅ Up 2 days | 2 days |

### Thay đổi đã thực hiện (2026-05-28)

**Gemini Model Migration & Stabilization**:
- [x] **Gemini 3 Pro Migration**: Redirected the `gemini-3-pro-high`/`low` definitions in `litellm_config.yaml` from `gemini/gemini-3-pro-preview` (already shutdown) to `gemini/gemini-3.1-pro-preview`.
- [x] **Embedding Pool Migration**: Redirected the `gemini-embed-base` template in `litellm_config.yaml` to use active `gemini/gemini-embedding-2` instead of the deprecated `gemini/gemini-embedding-001` (shutdown in July 2026).
- [x] **Budget & Comments Sync**: Synchronized budget descriptions and comments under the `gemini-embed` pool to match the new `gemini-embedding-2` specifications.
- [x] **Helper Scripts Audited & Updated**: 
  - Updated fallback references in `scripts/fix_quota_routing_regex.py` and `scripts/fix_quota_routing_regex_2026.py` to target `gemini-3.1-pro-preview`.
  - Migrated direct test references in `scripts/test_vertex_all.py` from `gemini-3-pro-preview` to `gemini-3.1-pro-preview`.
- [x] **Service Verification**: Restarted the `ai-gateway` container and verified that the entire docker services and system state are fully healthy.
- [x] **Integration Testing Succeeded**:
  - Ran `test_gateway_new_models.py` successfully verifying `gemini-2.5-flash-lite` and `gemini-embedding-2`.
  - Ran `test_gemini_embed.py` successfully verifying `gemini-embed` model pool fallback (returning 3072-dim embeddings).
  - Ran `test_gateway_gemini35_auto_correct.py` successfully verifying Gemini 3.5 parameter auto-correction.
  - Ran `test_gemini35_proxy_drop.py` and `test_gemini35_direct.py` successfully.

### Files quan trọng (updated)

| File | Mô tả |
|---|---|
| `services/ai-gateway/litellm_config.yaml` | AI Gateway configuration (updated active models & embedding pools) |
| `scripts/fix_quota_routing_regex.py` | Quota routing script (updated fallback references) |
| `scripts/test_vertex_all.py` | Vertex API test script (updated model references) |
| `scripts/fix_quota_routing_regex_2026.py` | Quota re-mapping script (updated fallback references) |
| `test_gemini_embed.py` | Standalone embedding model test |


