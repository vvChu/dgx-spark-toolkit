# Báo cáo kiểm toán kiến trúc dgx-spark-toolkit

Ngày khảo sát: 2026-09-28. Phạm vi: ingestion, retrieval, AI Gateway, agent workflow, Compose/Helm. Không restart dịch vụ. Không ghi Redis, Milvus, Postgres, Neo4j hay hàng đợi. Không in giá trị bí mật.

## Tóm tắt điều hành

Cây mã không khớp North Star trong `.agents/ARCHITECTURE.md`. Chín stage vẫn là method trong `services/rag-service/ingestion/pipeline.py`. Mục 3 và mục 6 đánh dấu xong, nhưng không có `ingestion/stages/` và không có import `asyncpg`.

Rủi ro production đã thấy trên mã:

- Worker luôn `acknowledge` vì `safe_process` nuốt exception và trả `None`. Index trả `status: failed` vẫn bị coi là xong.
- Cache exact theo câu gốc nhận kết quả của câu đã rewrite hoặc HyDE, rồi trả về trước khi Neo4j làm mới hiệu lực.
- `litellm-redis` publish `16379` với AOF, không `requirepass`. DB 3 giữ nguyên văn đoạn văn.
- Bearer gateway và mật khẩu chart nằm dạng literal trong cây làm việc.
- Workflow bật sẵn chạy `docker compose down` và `model_auto_updater.py --force`.

North Star: NS1, NS4, NS8 là Chưa đạt. NS2, NS3, NS5, NS6, NS7 là Một phần. Không có hàng Đạt. NS4 và NS8 có chi phí L nên không nằm trong đề xuất tuần này.

Pytest thoát 1 với một test fail, không có dòng tổng passed. Flake8 thoát 0 vì ignore `F401` và `F821`. Import ba module thoát 0. `pip check` báo xung đột, không cài thêm gói.

## Phương pháp

Bốn khảo sát đọc cây mã. Ma trận tám nguyên tắc lấy từ `.agents/ARCHITECTURE.md` và đối chiếu `docs/ARCHITECTURE.md`. Người viết mở lại các file lệch giữa khảo sát và ma trận trước khi chốt câu chữ.

Lệnh live lấy nguyên từ biên bản ngày 2026-09-28. Không bịa số passed, số finding flake8, hay số conflict ngoài danh sách đó. Biên bản ghi `compileall` làm mới bytecode dưới các package được chỉ định. Pha viết báo cáo không chạy lại lệnh đó.

Chuỗi bằng chứng trong đề xuất giữ ngắn. Đường đi chưa mở file thì không dùng làm chứng cứ sửa mã.

## Tầng A — Ingestion Pipeline

`docs/ARCHITECTURE.md` mô tả đúng cây: chín stage nằm trong `DocumentIngestionPipeline.run_pipeline`. Tên lần lượt là `_stage_intake`, `_stage_ocr`, `_stage_metadata`, `_stage_identity`, `_stage_chunking`, `_stage_enrichment`, `_stage_embedding`, `_stage_indexing`, `_stage_export`. OCR đi qua `DocumentReader.extract`. Chunk đi qua `DocumentChunker.chunk_document`. Index đi qua `DocumentStore.index_document_sync`. Export đi qua `DataExporter.export_document` nếu có exporter.

`safe_process` bắt mọi exception, ghi `FAILED` theo `rel_path`, rồi kết thúc không trả document. `run` vẫn gọi `acknowledge` trên `file_path` của message. Nhánh `nack` chỉ chạy khi `safe_process` ném ra ngoài, tức là không chạy cho lỗi stage. `doc_id` đưa vào `acknowledge` luôn rỗng vì kết quả là `None`.

`_stage_indexing` bỏ qua dict `{"status": "failed"}` trả về từ `index_document_sync` và không ghi log cho dict đó. `logger.warning` chỉ chạy khi `index_document_sync` ném exception hoặc khi không gắn `document_store`. Method vẫn trả document và worker vẫn `acknowledge`. `index_document` cập nhật status theo `rel_path`. Queue lại đánh `COMPLETED` theo `file_path` của message. Hai chuỗi khác nhau thì thành hai dòng `ingestion_state`.

`_stage_intake` thấy `COMPLETED` trên `rel_path` thì trả `None`, không gọi `get_existing_doc_hash`. Hàm hash file dùng SHA-256. Comment `DocumentIdentity.content_hash` vẫn nói MD5. `claim_file` SQL chỉ nhận `PENDING`, `FAILED` khi `retry_count < 3`, hoặc `CLAIMED` quá hạn. Không nhận lại `PROCESSING` hay `COMPLETED`.

`IngestionQueue.claim_next` đã `xreadgroup` id `>` rồi bỏ message nếu `claim_file` trả false. Không `ack`, không `nack`. Không có `XAUTOCLAIM` trong `services/rag-service`.

`_stage_identity` chỉ gán `namespace = "VBPL"`. `chunk_document` trả `list[dict]` và không gán `chunk_id`. Insert Milvus dùng `chunk_id` rỗng khi key vắng. `hub3_bridge.py` có gán `chunk_id` trên đường khác, không phải chín stage này. `_stage_embedding` nuốt lỗi embedding rồi vẫn đi tiếp.

`insert_chunks` chỉ insert. `index_document` không xóa `doc_id` cũ trước insert. `reset_all` có `TRUNCATE` `ingestion_state` và `system_checkpoints`, không thấy trên vòng `run`.

## Tầng B — Retrieval và AI Gateway

`SearchPipeline.execute` trả ngay khi tier-0 hoặc semantic cache trúng, trước `_stage_graph_enrichment`. Bước graph mới gọi `neo4j.find_document_status` và gắn cảnh báo văn bản hết hiệu lực. Hit cache không đi qua bước đó.

Sau tìm kiếm, semantic cache lưu vector của `search_query` (rewrite hoặc HyDE) nhưng tier-0 ghi `top_results` dưới khóa SHA-256 của `raw_query`. Khóa không gồm `use_hyde` hay `use_agentic`. Hit semantic cũng `set` chính kết quả đó vào khóa exact của câu hiện tại. Câu khác có thể nhận đoạn văn của câu trước.

`SemanticCache._get_from_redis` không đọc field `timestamp`. `set` gọi `expire` trên cả list key, nên một lần ghi làm mới TTL cả danh sách. Ngưỡng cosine không đo trên câu pháp lý thật trong pha này.

`Tier0ExactCache` dùng `redis.Redis.from_url` tới DB 3, không `socket_timeout`. `get`/`set` chạy trong coroutine search. `get_embedding_model()` được gọi trên event loop trước `run_in_executor`. `LazyInit.get` giữ `threading.Lock` suốt factory.

Intent `COMPLEX` gán `use_hyde = True`. Schema chat mặc định `use_agentic` là `False`, nên nhánh agentic không chạy và HyDE vẫn chạy. `AIGatewayClient.complete` mặc định chain `[model, "rag-core", "rag-light"]`, ba lần thử, timeout POST 300 giây. Compose đặt `VLLM_MODEL` mặc định `rag-core`, nên chain có thể lặp `rag-core` rồi tới `rag-light`. `rag-light` trong `litellm_config.yaml` fallback về `rag-core`. `rag-core` có fallback rỗng. Khi HyDE lỗi, hàm trả lại query đầu vào và caller vẫn nối chuỗi nếu không rỗng.

`claude-haiku-4` có model riêng nhưng không có mục fallback riêng. `default_fallbacks` là `["ocr-fallback"]`. Hành vi LiteLLM 1.83.3 không được gọi thật. `background_health_checks` là `false`. Cache LiteLLM trỏ `litellm-redis:6379`, không chỉ số DB, tức DB 0.

Điểm dưới 0.65 chỉ bật `search_grounding_triggered`. Pipeline vẫn trả và cache các hit đó.

## Tầng C — Hạ tầng agent

`AI_GATEWAY_KEY` và `OPENAI_API_KEY` trong `.agents/skills/ccba-ai-gateway-sdk/.env.ai-gateway` là literal. Workflow `.agents/workflows/ccba-update-models.md` nhúng bearer trong lệnh `curl`. Không chép lại giá trị. Không chạy `git ls-files`, nên không kết luận trạng thái commit của file dot.

`helm/dgx-spark-toolkit/values.yaml` để literal ở `neo4j.password` và `database.postgresUrl`. `docker-compose.yml` có fallback literal cho `ADMIN_SECRET` và cho mật khẩu MinIO.

`.agents/workflows/stop-all.md` đang `enabled: true` và chạy `docker compose down`. Mô tả `ccba-update-models` nói patch gateway rồi restart. Bước 2 chạy `scripts/model_auto_updater.py --force`. Script Python không được mở, nên không khẳng định lệnh restart nằm trong file đó.

`catalog.yaml` đặt `hub_path: .` và `hub_repo` ngoài repo này. Khảo sát đếm 90 thư mục skill, 74 tên trong catalog, 57 trùng, 17 tên thiếu trên đĩa, 33 thư mục không được liệt kê. Người viết không đếm lại từng thư mục. Khóa `workflows` có mặt trong `catalog.yaml` và giá trị là `[]`, danh sách rỗng. `.agents/rules` theo khảo sát chỉ có một file. `ccba_identity.md` được báo là thiếu. Không mở orchestrator `progress.md`. Khảo sát nói lần cuối 2026-08-09 và `victory_auditor_1` không nằm roster.

## Tầng D — Vận hành

`/health` trả 503 trừ khi Milvus và Neo4j là `ok` hoặc `reconnected` (nên `not initialized` cũng fail) và warmup là `ready`, `skipped` hoặc `disabled` (nên `pending` và `in_progress` fail). Redis và Postgres chỉ được kiểm tra ở `/health/pipeline`, nơi `async_state_manager` chính là `StateManager` đồng bộ. Healthcheck Compose của `rag-service` gọi `/health`. `ocr-worker` là `service_started`, không phải `service_healthy`. `rag-watcher` có `healthcheck.disable: true`, profile `ingest`, limit bộ nhớ 14G.

`ai-gateway` probe `/health/liveliness`. `depends_on` có `litellm-db` và `litellm-redis` lúc khởi động. Không chứng minh handler liveliness bỏ qua Postgres.

`milvus-standalone` phụ thuộc `milvus-etcd` và `milvus-minio` không kèm `service_healthy`. Prometheus chỉ mount `prometheus.yml`. `monitoring/prometheus.yml` trỏ `rule_files` tới `alerts.yml`, file đó không được mount. Grafana mount dashboard và provisioning, không có volume `/var/lib/grafana`.

`.env` đặt `REDIS_CACHE_URL` DB 0 và `REDIS_QUEUE_URL` DB 1, không có mật khẩu trong URL. `rag-service` nhận queue URL. `smart-watchdog` nhận cache URL rồi `SET rag:ingestion:paused`. `is_paused` đọc client của queue, tức DB 1. Cờ pause và người đọc không cùng DB. `chunking.py` cache tóm tắt bảng trên `REDIS_URL`, mặc định DB 1.

Helm `service.port` là 8000. Compose publish `8005:8000`. Ảnh LiteLLM Compose là `v1.83.3-stable`. Helm là `main-latest`. Limit RAG Helm 16Gi, Compose 12G. Watcher Helm 8Gi, Compose 14G. Cả hai giữ Milvus `19530`. Không thấy override collection trong `values.yaml`. `docs/ARCHITECTURE.md` nói collection `legal_docs_v11`.

`HF_HOME` trong Compose là `/home/appuser/.cache/huggingface`. Volume `model_cache` mount tại `/app/model_cache`. `docs/PITFALLS.md` và `docs/DEVELOPMENT.md` yêu cầu `HF_HOME=/app/models`.

`requirements-app.lock` ghim `neo4j==5.26.0` và `opencv-python-headless==4.11.0.86`. `requirements-ci.lock` ghim `neo4j==5.23.1` và `opencv-python-headless==5.0.0.93`. `requirements.txt` chặn opencv dưới 5 và có `surya-ocr==0.17.1`. `asyncpg==0.31.0` có trong app lock, không thấy import trong mã đã tìm.

Watchdog đặt `CHATOPS_GATEWAY_URL` tới `172.21.0.1:8095`. Các khối Compose đã đọc không khai báo service cho cổng đó.

## Ma trận North Star

Nguồn nguyên tắc: `.agents/ARCHITECTURE.md`. Mức độ map từ `not_met`, `partial`, `met`. Không hàng nào `met`.

| ID | Nguyên tắc | Mức độ | Gap cụ thể | Bằng chứng | Chi phí |
|---|---|---|---|---|---|
| NS1 | Pipeline thành các stage | Chưa đạt | Mục 3 đánh dấu tách file xong. Chín `_stage_*` vẫn trong monolith. | `run_pipeline` gọi chín method. Không có `ingestion/stages/01_intake.py` tới `09_export.py`. | M — vài ngày để tách method và sửa handoff dict |
| NS2 | Model Pydantic | Một phần | `DocumentIdentity`, `Chunk`, `ProcessedDocument` là dataclass. OCR và chunk vẫn là dict. | `ingestion/models.py` dùng dataclass. `chunk_document` trả `list[dict]`. | M — đổi model rồi hết dict trên đường nóng |
| NS3 | Redis Streams | Một phần | Có `xadd` và `xreadgroup`, chưa claim nguyên tử, không reclaim pending. | `claim_next` chỉ đọc `>`. `claim_file` false thì bỏ message. Không có `xautoclaim`. | M — nack khi claim hỏng và thêm reclaim |
| NS4 | Async toàn phần | Chưa đạt | Mục 6 ghi `asyncpg` xong. Alias async là `StateManager` đồng bộ. | `database.py` gán `async_state_manager = state.state_manager`. `ingest_file` gọi `run_pipeline` đồng bộ. | L — hơn năm ngày nếu bỏ chặn event loop |
| NS5 | Volume cache model | Một phần | Có volume tên `model_cache` nhưng không phải mount `/app/models`. | Compose đặt `HF_HOME` tại cache home và mount volume ở `/app/model_cache`. | S — dưới hai ngày, sửa mount rồi sửa docs |
| NS6 | Nạp lại bất biến | Một phần | Bỏ qua theo status `COMPLETED`, không so hash. Insert không upsert. | Intake trả `None` khi đã `COMPLETED`. `get_existing_doc_hash` không có caller. `insert_chunks` chỉ insert. | M — so hash, upsert `doc_id`, cấm ACK mù |
| NS7 | Pipeline quan sát được | Một phần | Có histogram stage, không có kiểu `PipelineEvent`. | `STAGE_DURATION` ghi `rag_stage_duration_seconds`. Không thấy symbol `PipelineEvent`. | S — phát event cạnh counter hiện có |
| NS8 | Migration schema | Chưa đạt | Không có lịch sử phiên bản kiểu Alembic cho Milvus. | `ensure_collection_schema` tạo collection còn thiếu. `reindex_milvus_clean.py` gọi `drop_collection`. | L — thay drop-and-recreate bằng migrator có phiên bản |

`docs/ARCHITECTURE.md` vẫn nói intake khử trùng bằng hash và identity chuẩn hóa `chunk_id`. Hai câu đó không đúng với `_stage_intake` và `_stage_identity` đã đọc. `docs/CONVENTIONS.md` mô tả dạng `chunk_id` mà stage pipeline không gán.

## Xác minh thực tế

Không có số passed. Không có số lỗi flake8 ngoài exit 0. Lệnh phụ thuộc gây ra danh sách conflict là bản `python -m pip check`, không phải script `pip` có shebang gãy.

### pytest

Lệnh: `cd services/rag-service && timeout 420 ./venv/bin/pytest tests/ -q --tb=line -m 'not integration and not gpu'`

Tóm tắt: `FAILED tests/test_hub3_bridge.py::TestCatalogDiscovery::test_load_master_catalog_category_filter`

Exit code 1. Biên bản nói không có footer N-failed/M-passed vì `pytest.ini` đã có `-q`, lệnh thêm `-q`, verbosity thành -2. Glyph trước FAILURES là 526 dấu `.` và 1 `F`. Tiến trình thoát 1, không phải 124. Thời gian tường khoảng 12.23s. Không có traceback trong tóm tắt, nên không kết luận nguyên nhân assert.

### flake8

Lệnh: `timeout 180 services/rag-service/venv/bin/flake8 services/rag-service --config=services/rag-service/.flake8`

Tóm tắt: Exit 0 with no reported findings. This is not a clean bill: `services/rag-service/.flake8` ignore includes `F401` and `F821`, so unused imports and undefined names are hidden globally; per-file-ignores repeat `F401` and `F821` for tests.

`flake8_exit_code` là 0. File `.flake8` đã mở và đúng là ignore `F401`, `F821` cùng nhiều mã style khác.

### imports

Lệnh: `cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service && timeout 180 ./venv/bin/python -m compileall -q -x 'venv|__pycache__|autoresearch/exports' ingestion retrieval core api repositories models; timeout 30 ./venv/bin/python -c 'import ingestion.models, ingestion.queue, retrieval.search_pipeline'`

Tóm tắt: `import_ok` true, `import_failures` rỗng, cả `compileall` và ba import thoát 0. Import `retrieval.search_pipeline` kéo `torchao` ở user-site và in `No module named 'triton'`, rồi tiếp tục. Không import `main.py`. Không mở server. Không treo. `compileall` chỉ làm mới bytecode dưới các package được chỉ định.

### dependency conflicts

Lệnh đã in conflict: `cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service && timeout 120 ./venv/bin/python -m pip check`

Lệnh đó thoát 1. `timeout 120 ./venv/bin/pip check` thoát 127 vì shebang trỏ interpreter không còn tại đường dẫn cũ. Không cài gói.

Tóm tắt conflict:

- `proto-plus` 1.27.0 cần `protobuf<7`, đang có `protobuf` 7.34.1.
- `google-api-core` 2.29.0 cần `protobuf<7`, đang có 7.34.1.
- `googleapis-common-protos` 1.72.0 cần `protobuf<7`, đang có 7.34.1.
- `grpcio-reflection` 1.78.0 cần `protobuf<7`, đang có 7.34.1.
- `grpcio-status` 1.71.2 cần `protobuf<6`, đang có 7.34.1.
- `opentelemetry-proto` 1.40.0 cần `protobuf<7`, đang có 7.34.1.
- `google-ai-generativelanguage` 0.6.15 cần `protobuf<6`, đang có 7.34.1.
- `grpcio-health-checking` 1.78.0 cần `protobuf<7`, đang có 7.34.1.
- `sglang` 0.5.9 cần `openai==2.6.1`, đang có `openai` 2.26.0.
- `sglang` 0.5.9 cần `transformers==4.57.1`, đang có `transformers` 4.57.5.
- `moviepy` 2.2.1 cần `pillow<12`, đang có `pillow` 12.1.1.
- `yt-dlp` 2024.4.9 cần `websockets>=12`, đang có `websockets` 10.4.

Biên bản còn nói pillow cài 12.1.1 trong khi `requirements-app.lock` ghim `pillow==12.3.0`, và liệt kê thêm lệch constraint giữa `requirements.txt`, app lock và CI. Người viết chỉ mở các pin neo4j, opencv, asyncpg và surya-ocr.

## Đề xuất cải tiến

Mỗi mục có một file bắt đầu. NS4 và NS8 không có mục riêng vì chi phí L.

### P1 — Làm ngay

#### Không báo COMPLETED khi stage hoặc index lỗi

**Vấn đề:** Hàng đợi mất việc thất bại và trạng thái Postgres có thể nói tài liệu đã xong dù Milvus không nhận, hoặc nhận với `chunk_id` rỗng.
**Bằng chứng:** `safe_process` nuốt exception. `run` vẫn `acknowledge`. `_stage_indexing` không xét dict `status`.
**Giải pháp:** Sửa trước `services/rag-service/ingestion/pipeline.py`: trả document hoặc ném lại lỗi. Chỉ `acknowledge` khi index trả success. Coi embedding rỗng là lỗi. Ghi status bằng cùng một khóa `rel_path`.
**Effort:** S — một ngày trong `pipeline.py`, chưa tách file stage.
**Rủi ro:** Worker sẽ `nack` nhiều hơn và có thể đẩy file hỏng vào dead letter sau `MAX_RETRIES`.

#### Không biến kết quả HyDE thành cache nguyên văn

**Vấn đề:** Câu hỏi pháp lý sau có thể nhận đoạn của câu khác, và bỏ qua hiệu lực mới trên Neo4j.
**Bằng chứng:** Tier-0 ghi `raw_query` trong khi vector là câu đã đổi. Hit cache return trước `find_document_status`.
**Giải pháp:** Sửa trước `services/rag-service/retrieval/search_pipeline.py`: không `set` exact từ hit semantic. Đưa `use_hyde` và `use_agentic` vào khóa. Sau hit vẫn gọi làm mới status.
**Effort:** S — sửa khóa và thứ tự gọi, không đổi model.
**Rủi ro:** Tỉ lệ trúng cache giảm. Cần xóa key cũ trên DB 3 sau khi đổi công thức khóa.

#### Chặn Redis 16379 không mật khẩu

**Vấn đề:** Ai tới được cổng host có thể sửa đoạn văn cache và cache LiteLLM.
**Bằng chứng:** Service `litellm-redis` map `16379:6379`, lệnh chỉ `--appendonly yes`, không `requirepass`.
**Giải pháp:** Sửa trước `docker-compose.yml`: bật `requirepass` bằng biến môi trường, không ghi mật khẩu vào file. Rồi trỏ client DB 0 và DB 3. Firewall chưa được kiểm tra.
**Effort:** S — đổi command Redis và URL client trong cùng ngày.
**Rủi ro:** Gateway và RAG mất cache nếu một phía còn URL không mật khẩu. Lên kế hoạch restart có chủ đích, ngoài pha này.

#### Gỡ bearer và mật khẩu literal khỏi cây làm việc

**Vấn đề:** Khóa gateway, mật khẩu Neo4j chart, URL Postgres chart, và fallback `ADMIN_SECRET` nằm trong file có thể bị copy.
**Bằng chứng:** Literal ở `.env.ai-gateway` (`AI_GATEWAY_KEY`, `OPENAI_API_KEY`), curl trong `ccba-update-models.md`, và `values.yaml`.
**Giải pháp:** Sửa trước `.agents/skills/ccba-ai-gateway-sdk/.env.ai-gateway`: xóa giá trị, chuyển sang biến môi trường. Sau đó gỡ curl trong `.agents/workflows/ccba-update-models.md` và literal `neo4j.password`, `database.postgresUrl`. Rotate phía gateway. Không dán lại chuỗi cũ.
**Effort:** S — gỡ file và rotate, không đổi giao thức gọi.
**Rủi ro:** Skill và chart đang trỏ key cũ sẽ fail cho tới khi secret được cấp lại ngoài git.

#### Chặn workflow agent hạ stack

**Vấn đề:** Workflow đang bật có thể tắt cả Compose production hoặc ép sửa `litellm_config.yaml`.
**Bằng chứng:** `.agents/workflows/stop-all.md` chạy `docker compose down`. `ccba-update-models.md` chạy updater `--force`.
**Giải pháp:** Sửa trước `.agents/workflows/stop-all.md`: tắt `enabled` hoặc bỏ `docker compose down` khỏi workflow agent. Làm cùng với bước `--force` trong `ccba-update-models.md`.
**Effort:** S — sửa frontmatter và khối lệnh, không đụng container trong pha này.
**Rủi ro:** Runbook vận hành thật phải chuyển ra tài liệu thao tác người, nếu không người trực mất lệnh tắt khẩn.

### P2 — North Star và độ tin cậy

#### Tách pipeline thành file stage

**Vấn đề:** NS1 chưa đạt. Current State vẫn gọi `pipeline.py` là monolith trong khi mục 3 đã tick.
**Bằng chứng:** Chín `_stage_*` nằm trong một file. Thư mục `ingestion/stages` không tồn tại.
**Giải pháp:** Sau P1, tách từ `services/rag-service/ingestion/pipeline.py` thành `01_intake.py` tới `09_export.py`, mỗi stage nhận và trả `ProcessedDocument`.
**Effort:** M — vài ngày vì chunk và index còn trao dict.
**Rủi ro:** Tách cơ học trước khi sửa ACK sẽ nhân bản lối nuốt lỗi sang nhiều file.

#### Đưa model ingestion sang Pydantic

**Vấn đề:** NS2 mới một phần. Key tùy chọn trên dict làm `chunk_id` và metadata biến mất mà không báo.
**Bằng chứng:** `DocumentIdentity`, `Chunk`, `ProcessedDocument` là dataclass. `chunk_document` trả dict.
**Giải pháp:** Sửa trước `services/rag-service/ingestion/models.py`, chuyển ba kiểu sang Pydantic, rồi siết `chunking.py` không trả dict trần.
**Effort:** M — đổi kiểu trên đường OCR, chunk và index.
**Rủi ro:** Test đang dựng dict sẽ vỡ cho tới khi fixture khớp schema.

#### Claim Redis phải nguyên tử và được reclaim

**Vấn đề:** NS3 mới một phần. Message đã đọc có thể nằm pending mãi nếu claim Postgres thất bại.
**Bằng chứng:** `IngestionQueue.claim_next` không `nack` khi `claim_file` false. `queue.py` không gọi `xautoclaim`.
**Giải pháp:** Sửa trước `services/rag-service/ingestion/queue.py`: thêm reclaim pending. Trong `ingestion_queue.py`, `nack` ngay khi claim state thất bại.
**Effort:** M — cần thử hai worker và một message kẹt, không đụng Redis production trong pha thiết kế.
**Rủi ro:** Reclaim quá ngắn có thể xử lý trùng nếu worker còn sống. Giữ hạn `stale_minutes` hiện có làm mốc.

#### Trỏ cache model đúng volume

**Vấn đề:** NS5 mới một phần. Process không dùng mount `/app/models` mà tài liệu yêu cầu.
**Bằng chứng:** Compose để `HF_HOME` tại home cache và mount `model_cache` ở `/app/model_cache`.
**Giải pháp:** Sửa trước `docker-compose.yml` cho `HF_HOME=/app/models` và mount `model_cache` đúng path đó, trên cả `rag-service` và `rag-watcher`. Rồi sửa `docs/PITFALLS.md`.
**Effort:** S — dưới hai ngày, gồm chỉnh docs cho khớp runtime.
**Rủi ro:** Container mới có thể tải lại model nếu volume cũ không được copy sang path mới.

#### So hash và upsert theo doc_id

**Vấn đề:** NS6 mới một phần. File đã `COMPLETED` không được so nội dung. Index lại có thể nhân vector.
**Bằng chứng:** Intake không gọi `get_existing_doc_hash`. `insert_chunks` không xóa `doc_id` cũ. `reset_all` vẫn `TRUNCATE`.
**Giải pháp:** Sửa trước `services/rag-service/ingestion/pipeline.py` để so hash trước khi skip. Trong `repositories/document_store.py`, xóa hoặc upsert theo `doc_id` trước insert. Không gọi `reset_all` trên đường worker.
**Effort:** M — đụng Postgres và Milvus. Cần bản sao collection trước khi chạy thật.
**Rủi ro:** Upsert sai khóa có thể xóa chunk còn hiệu lực. Chạy thử trên một `doc_id` trước.

#### Thêm sự kiện stage có cấu trúc

**Vấn đề:** NS7 mới một phần. Có histogram, chưa có `PipelineEvent` để Grafana và log dùng chung một kiểu.
**Bằng chứng:** `pipeline.py` ghi `STAGE_DURATION`. Không thấy symbol `PipelineEvent` trong mã đã tìm.
**Giải pháp:** Sửa trước `services/rag-service/ingestion/pipeline.py`: định nghĩa `PipelineEvent` và emit cạnh counter hiện có. Dashboard JSON đã được mount. Không cần metric mới nếu label giữ nguyên.
**Effort:** S — thêm kiểu dữ liệu và một điểm ghi, không đổi queue.
**Rủi ro:** Label mới sẽ làm series Prometheus gãy nếu đổi tên metric đang có.

#### Gỡ Redis đồng bộ và khóa tải model khỏi event loop

**Vấn đề:** Một Redis DB 3 treo hoặc lần tải BGE-M3 đầu tiên có thể chặn vòng lặp search.
**Bằng chứng:** `Tier0ExactCache` dùng `redis.Redis` không timeout ngay trong `execute`. `LazyInit` giữ lock suốt factory. `get_embedding_model()` chạy trước executor.
**Giải pháp:** Sửa trước `services/rag-service/retrieval/tier0_cache.py`: thêm `socket_timeout` và gọi Redis ngoài event loop. Trong `core/singleton.py`, không giữ lock trong lúc load model.
**Effort:** S — bọc lệnh gọi. Chưa đổi toàn bộ stack sang `asyncpg`.
**Rủi ro:** Timeout ngắn làm cache miss hàng loạt khi Redis chậm, không được nuốt thành kết quả rỗng.

### P3 — Dọn cấu trúc

#### Bỏ dấu hoàn thành sai trên North Star

**Vấn đề:** Agent đọc mục 3 và mục 6 sẽ tưởng stage file và `asyncpg` đã xong.
**Bằng chứng:** `.agents/ARCHITECTURE.md` tick hai mục đó. Cùng file vẫn ghi monolith. `docs/ARCHITECTURE.md` nói hash và `chunk_id` đã có trên stage.
**Giải pháp:** Sửa trước `.agents/ARCHITECTURE.md`: bỏ tick mục 3 và 6, trỏ lại `pipeline.py`. Sửa câu intake và identity trong `docs/ARCHITECTURE.md` và dạng `chunk_id` trong `docs/CONVENTIONS.md` cho khớp mã.
**Effort:** S — chỉ sửa tài liệu sau khi mã P1 được chốt.
**Rủi ro:** Sửa docs trước mã sẽ thành một lớp mô tả thứ ba.

#### Khớp Helm với Compose đang chạy

**Vấn đề:** Cùng chart và Compose không cùng cổng xuất, ảnh LiteLLM, hay limit bộ nhớ.
**Bằng chứng:** Helm port 8000, ảnh `main-latest`, RAG 16Gi, watcher 8Gi. Compose publish `8005:8000`, ảnh `v1.83.3-stable`, RAG 12G, watcher 14G.
**Giải pháp:** Sửa trước `helm/dgx-spark-toolkit/values.yaml` để ảnh gateway và limit theo đúng Compose đang vận hành, hoặc ghi rõ profile nào là nguồn. Không nhân bản mật khẩu. Collection để mặc định `legal_docs_v11` nếu không có override có chủ đích.
**Effort:** S — chỉnh values. Chưa cài cluster.
**Rủi ro:** Đổi port Service làm ingress `rag.dgxspark.local` gãy nếu manifest khác còn trỏ 8000 bên trong pod. Giữ container port 8000.

#### Khớp khóa phụ thuộc CI và app

**Vấn đề:** CI không cài cùng neo4j và opencv với ảnh app. `pip check` trên venv hiện tại đang vỡ vì protobuf 7.
**Bằng chứng:** App lock `neo4j==5.26.0`, opencv `4.11.0.86`. CI lock neo4j `5.23.1`, opencv `5.0.0.93`, ngoài trần `<5` của `requirements.txt`.
**Giải pháp:** Sửa trước `services/rag-service/requirements-ci.lock`: đưa neo4j và opencv về đúng pin app lock. Tách việc hạ `protobuf` 7.34.1 thành một diff riêng vì nó kéo grpc và OpenTelemetry.
**Effort:** M — giải conflict protobuf không phải chỉ sửa một số pin.
**Rủi ro:** Hạ protobuf có thể vỡ gói đã biên dịch sẵn trong venv. Không chạy `pip install` trên máy production trong pha này.

#### Biên dịch lại catalog skill cho khớp đĩa

**Vấn đề:** Loader có thể gọi skill không tồn tại hoặc bỏ qua skill local không có trong catalog.
**Bằng chứng:** `catalog.yaml` là catalog CCBA với `hub_path: .`. Khảo sát báo 74 tên so với 90 thư mục. Người viết không đếm lại.
**Giải pháp:** Sửa trước `.agents/skills/platform-loader/catalog.yaml` bằng `scripts/governance/compile_catalog.py` như header file đã ghi, rồi xóa tên không có thư mục. Không bật workflow mutate trong lúc biên dịch.
**Effort:** S — regenerate manifest. Không sửa từng `SKILL.md`.
**Rủi ro:** Compile có thể đưa runbook nguy hiểm vào catalog nếu frontmatter `enabled` chưa tắt ở P1.

#### Khớp cờ backpressure và giữ đĩa metrics

**Vấn đề:** Watchdog ghi pause ở DB 0 trong khi worker đọc DB 1. Prometheus và Grafana mất dữ liệu khi container bị thay.
**Bằng chứng:** `smart-watchdog` lấy `REDIS_CACHE_URL`. `is_paused` đọc client queue. Prometheus không mount `alerts.yml` và không có volume dữ liệu.
**Giải pháp:** Sửa trước `docker-compose.yml`: đặt `REDIS_URL` của `smart-watchdog` bằng `REDIS_QUEUE_URL`. Thêm volume cho `/prometheus` và `/var/lib/grafana`. Mount `monitoring` sao cho `alerts.yml` nằm cạnh file cấu hình trong container.
**Effort:** S — sửa wiring Compose. Không xóa volume đang có.
**Rủi ro:** Đổi DB của watchdog mà không xóa key cũ trên DB 0 để lại cờ pause mồ côi. Volume mới không mang dữ liệu cũ vì dữ liệu cũ không được mount.

## Final Gate

Trạng thái phiếu gốc: Chưa đạt, vì Challenger trả `revise`. Lượt đọc lại sau khi sửa chữ xác nhận các sửa đó đã nằm trong báo cáo.

Reviewer: pass. Challenger: revise. Forensic: pass. Ba chỗ Challenger chỉ ra đã được viết lại trong tầng A, C và D: `_stage_indexing` không log khi nhận dict `status: failed`; `catalog.yaml` có khóa `workflows` với giá trị `[]`; `/health` trả 503 theo đúng tập trạng thái Milvus, Neo4j và warmup. Reviewer và forensic không có yêu cầu sửa. Không nâng hàng North Star. Không bịa số test. P1 vẫn mở trên cây mã ngày 2026-09-28. Không chạy lại pytest hay flake8, vì pha này không sửa mã dịch vụ.
