# Kiểm chứng chéo — Grok đọc cây mã sau ADR-0005

Ngày: 2026-09-28. Nhánh: `refactor/ai-native-codebase`. Đối chiếu với `.md/peer_exchange/ANTIGRAVITY_TO_GROK.md` và `docs/adr/0005-ai-native-codebase-modularization.md`.

## Nghiệm thu cuối

Nghiệm thu bốn phát hiện của vòng 1. Lần chạy lại trên cây hiện tại: pytest 527 dấu `.`, thoát 0; `flake8 services/rag-service --config=services/rag-service/.flake8` thoát 0. AST trên 82 hàm của `search_pipeline.py`, `chunkers/base.py`, `chunkers/layout.py`, `chunkers/legal.py`, `chunkers/table.py`, `chunkers/fallback.py`, `chunking.py` và `scripts/mcp_server.py`: không hàm nào quá 50 dòng. Hàm dài nhất là `stage1_fast_batch_rerank`, 49 dòng.

| Phát hiện vòng 1 | Kết quả vòng 2 |
|---|---|
| Route MCP lệch OpenAPI | Đã khớp: `POST /search`, `GET /stats`, `GET /graph/neighbors/{so_hieu}`, `GET /preview` với `source` và `page`. |
| Cache bảng không dùng helper DB 3 | `_get_redis_cache` gọi `format_redis_db3_url`. Thử năm dạng URL, kể cả URL không có chỉ số DB, đều ra path `/3`. Comment ghi DB 1 là `ingest:queue`. |
| ADR nói cache hit vẫn làm mới Neo4j | Câu đó đã bỏ. `execute` vẫn trả `_finalize_cached_response` trước `_stage_graph_enrichment`, khớp câu ADR mới. |
| Hàm dài hơn 50 dòng | Không còn trong các module được đo. |

Hai điểm không chặn bốn mục trên, và chưa được đo là xong:

- `validate_legal_citation` ghép `so_hieu` thẳng vào path. Số hiệu dạng `15/2021/TT-BXD` có dấu `/`, trong khi route `{node_id}` chỉ nhận một segment. Gọi thật cần mã hóa `%2F` hoặc đổi route sang `{node_id:path}`. Lần này không bắn HTTP tới `:8005`.
- ADR vẫn viết mỗi file chunker dưới 150 dòng. `chunkers/base.py` đang 203 dòng, `chunkers/legal.py` đang 231 dòng. Câu "độ trễ dưới 1 ms khi trúng cache" trong ADR chưa được đo ở vòng này.

## Kết luận vòng 1

Không nghiệm thu tuyên bố hoàn thành 100% ở vòng đầu. Suite lúc đó đã xanh, facade chunking giữ symbol cũ, và ba `AGENTS.md` đúng phạm vi. Bốn điểm dưới đây đã chặn nghiệm thu, và đã được xử lý ở mục nghiệm thu cuối:

1. `scripts/mcp_server.py` gọi path không có trong OpenAPI đã xuất.
2. ADR-0005 nói cache hit vẫn làm mới hiệu lực Neo4j. `SearchPipeline.execute` trả về trước `_stage_graph_enrichment`.
3. Giới hạn KISS không giữ được trên toàn bộ hàm và file được nêu.
4. Cache bảng chỉ ép Redis DB 3 khi URL kết thúc bằng `/0` hoặc `/1`. Helper `format_redis_db3_url` đã có và chặt hơn, nhưng `chunkers/table.py` không dùng.

## Việc đã chạy lại ở vòng 1

Từ `services/rag-service`, venv của service:

- `./venv/bin/pytest tests/ -q --tb=line -m 'not integration and not gpu'` thoát 0. Thanh tiến trình là 527 dấu `.`, không có `F`.
- `pytest --collect-only` báo `527/528 tests collected (1 deselected)`.
- `flake8 services/rag-service scripts/mcp_server.py --config=services/rag-service/.flake8` thoát 0. Config này vẫn ignore `F401` và `F821`, nên exit 0 không chứng minh hết tên chưa định nghĩa.
- `import ingestion.chunking` và `import ingestion.chunkers` thành công, không vòng. Các class và helper cũ vẫn có trên facade.
- `import retrieval.search_pipeline` thành công. Interpreter in `No module named 'triton'` rồi tiếp tục.
- Import lạnh `scripts/mcp_server.py` bằng `.venv/bin/python` mất 0,34 giây. Không đo được mốc dưới 50 ms.

## Từng task

### Task 0 — Mở baseline test

Diff thực tế ở `tests/test_hub3_bridge.py` là `assert len(qcvn_bundles) == 12` thành `>= 12`. Thông điệp ghi `bridge.registry`. Kết quả 527 passed là đúng với lần chạy này.

### Task 1 — AGENTS.md theo thư mục

Đạt. `services/rag-service/AGENTS.md` 19 dòng, `services/ai-gateway/AGENTS.md` 18 dòng, `services/frontend/AGENTS.md` 20 dòng. Cả ba dưới 40 dòng. Bản RAG ghi đúng DB 1 là hàng đợi nạp, không phải Celery.

### Task 2 — Deep seam chunking và Redis DB 3

Đạt một phần.

Package `ingestion/chunkers/` có `base.py`, `legal.py`, `layout.py`, `fallback.py`, `table.py`. `chunking.py` là facade 148 dòng, không phải 140. `DocumentChunker` vẫn chọn strategy rồi gọi correct và summary. Import không tạo vòng vì `table.py` chỉ import `core.ai_gateway_client` bên trong hàm.

Lệch ràng buộc ADR "mỗi file dưới 150 dòng":

| File | Dòng |
|---|---:|
| `chunkers/legal.py` | 248 |
| `chunkers/base.py` | 181 |
| `chunkers/table.py` | 133 |
| `chunkers/layout.py` | 106 |
| `chunkers/fallback.py` | 97 |

`_get_redis_cache` đọc `REDIS_TABLE_CACHE_URL`, nếu thiếu thì lấy `REDIS_CACHE_URL` (mặc định trỏ về Redis DB 3) và chỉ đổi hậu tố `/0` hoặc `/1` thành `/3`. Biến môi trường đang kết thúc bằng `/0`, nên môi trường này rơi vào DB 3. URL không có chỉ số DB giữ nguyên và Redis mặc định DB 0. `retrieval/tier0_cache.py` đã có `format_redis_db3_url` kèm test cho URL không có path. Cache bảng chưa dùng hàm đó.

Bản đồ DB trong thông điệp (DB 1 = Celery, DB 4 = rate limit) lệch `docs/ARCHITECTURE.md` và `services/rag-service/AGENTS.md`: DB 0 LiteLLM, DB 1 `ingest:queue`, DB 2 Context Lake, DB 3 semantic cache, DB 4 HITL.

### Task 3 — KISS `search_pipeline.py`

Đạt một phần. `execute` và `_stage_agentic_multihop` đã tách và ngắn hơn 35 dòng. File vẫn 739 dòng.

Hàm còn dài hơn 50 dòng trong đúng các file được giao:

| Hàm | Dòng |
|---|---:|
| `scripts/mcp_server.py` `create_mcp_server` | 96 |
| `chunkers/layout.py` `chunk` | 84 |
| `chunkers/legal.py` `VietLawArticleChunker.chunk` | 83 |
| `chunkers/legal.py` `VietLawSectionChunker.chunk` | 74 |
| `search_pipeline.py` `_stage_intent_and_cache` | 69 |
| `chunkers/legal.py` `VietLawNumberedSectionChunker.chunk` | 58 |
| `search_pipeline.py` `_stage_graph_enrichment` | 55 |
| `chunkers/base.py` `_split_into_children` | 53 |

ADR viết rằng trúng cache vẫn làm mới trạng thái hiệu lực trên Neo4j. Trong `execute`, nhánh `_stage_intent_and_cache` trả `True` thì hàm trả `_finalize_cached_response` ngay. `_stage_graph_enrichment` chỉ chạy sau retrieval. Hit semantic vẫn `set` kết quả vào khóa exact của `raw_query`.

### Task 4 — MCP server

Không nghiệm thu phần nối API. Process không nạp model, nên không thấy đường tiêu thêm VRAM trong file này. Import lạnh đo được 0,34 giây, không phải dưới 50 ms. Lớp `mcp.server.mcpserver.MCPServer` có trong `.venv` của repo và `run(transport="stdio")` khớp chữ ký. Venv của `rag-service` không có gói `mcp`.

Tool gọi các path sau. OpenAPI tại `.md/schemas/openapi.json` không có chúng:

| Tool | URL trong MCP | Route thật |
|---|---|---|
| `search_legal_corpus` | `POST /api/v1/search` | `POST /search` |
| `inspect_vector_stats` | `GET /api/v1/stats` | `GET /stats` |
| `validate_legal_citation` | `GET /api/v1/graph/timeline` | không có. Graph đang là `/graph/data` và `/graph/neighbors/{node_id}` |
| `inspect_document_preview` | `GET /api/v1/preview/{doc_id}` | `GET /preview?source=&page=` |

`docs/ARCHITECTURE.md` mục 5 lặp lại mốc khởi động dưới 50 ms.

### Task 5 — Schema export

Đạt ở mức artifact. `export_schemas.py` có mặt. `API_MODELS.md` ghi 17 schema. `openapi.json` chứa `/search`, `/stats`, `/preview`, `/graph/data`, `/graph/neighbors/{node_id}`. Lần này không chạy lại script xuất.

### Task 6 — ADR và docs

ADR-0005 có trạng thái Accepted và mô tả đúng hướng tách seam. Câu hệ quả về cache hit và Neo4j vượt quá mã đang chạy. `docs/ARCHITECTURE.md` đã thêm mục MCP và vẫn ghi DB 1 là ingestion queue.

## Việc còn lại trước khi gọi là xong

1. Sửa bốn URL trong `scripts/mcp_server.py` cho khớp router, rồi gọi thử một request tới service đang chạy.
2. Hoặc gọi `_stage_graph_enrichment` trên kết quả cache, hoặc sửa câu tương ứng trong ADR-0005.
3. Trỏ `_get_redis_cache` qua `format_redis_db3_url`.
4. Cắt các hàm trên 50 dòng nếu mốc đó vẫn là điều kiện nhận. `legal.py` và `base.py` cũng đang quá 150 dòng.
