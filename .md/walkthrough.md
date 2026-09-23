# Walkthrough: Hoàn Thiện Triệt Để Hệ Thống RAG & Khôi Phục Native Milvus Hybrid Search

## Tổng Quan

Gói triển khai hoàn thiện triệt để theo Báo cáo Đánh giá Đối kháng (/boost) trên máy chủ NVIDIA DGX Spark (Grace Blackwell GB10, aarch64, CUDA 13.0, 128GB Unified Memory):

1. **Khuyến nghị P1: Khôi phục Native Milvus Hybrid Search (`SPARSE_FLOAT_VECTOR`)**
   - Đã nâng cấp schema khởi tạo collection trong `services/rag-service/scripts/reindex_milvus_clean.py` và `services/rag-service/repositories/milvus_repo.py`: khai báo tường minh trường `sparse_vector` kiểu `DataType.SPARSE_FLOAT_VECTOR`, thiết lập `index_params` gồm `vector` (`AUTOINDEX`, `COSINE`) và `sparse_vector` (`SPARSE_INVERTED_INDEX`, `IP`).
   - Tái lập collection `legal_docs_v10` với cấu trúc native hybrid schema, nạp lại 528 chunks sạch với đầy đủ dense & sparse embeddings (BGE-M3 trên CPU).
   - Xác nhận `hybrid_search()` hoạt động hoàn toàn native qua Milvus `RRFRanker`, loại trừ triệt để cảnh báo fallback sang dense-only search.

2. **Khuyến nghị P2: Hoàn thiện Seam Phòng Vệ Mất Dữ Liệu trong `ocr_client.py`**
   - Tại `services/rag-service/ingestion/ocr_client.py:104,107`: thay thế `return [], []` bằng `return None, None` khi gặp unsupported input type hoặc buffer ảnh rỗng.
   - Bảo đảm `RemoteSuryaClient.is_service_failure()` luôn trả về `True`, kích hoạt ngay nhánh fallback Vision LLM (`call_vision_fallback`), ngăn chặn hoàn toàn nguy cơ nuốt trang scan ngầm.
   - Cập nhật test case `test_empty_input` trong `services/rag-service/tests/test_ocr_client.py`.

3. **Khuyến nghị P4: Phòng Vệ Client History Injection trong `chat_service.py`**
   - Tại `services/rag-service/services/chat_service.py:136-137`: bổ sung bộ lọc kiểm tra vai trò `[m for m in history[-6:] if isinstance(m, dict) and m.get("role") in ("user", "assistant")]`.
   - Ngăn chặn triệt để client gửi tin nhắn giả mạo có `role: "system"` hoặc `"developer"`, bảo đảm bất biến Single Leading System Message của vLLM Jinja template.
   - Bổ sung unit test `test_build_messages_filters_client_history_roles` trong `services/rag-service/tests/test_chat_service.py`.

---

## Chi Tiết Các Thay Đổi

### 1. Native Milvus Hybrid Search (`SPARSE_FLOAT_VECTOR`)
- **`services/rag-service/repositories/milvus_repo.py`**:
  - Nhập `DataType` từ `pymilvus`.
  - Trong `ensure_collection_schema()`: xây dựng `CollectionSchema` với `id` (`INT64`), `vector` (`FLOAT_VECTOR`, dim 1024), và `sparse_vector` (`SPARSE_FLOAT_VECTOR`).
  - Cấu hình chỉ mục `vector` (`metric_type: COSINE`) và `sparse_vector` (`metric_type: IP`, `index_type: SPARSE_INVERTED_INDEX`).
- **`services/rag-service/scripts/reindex_milvus_clean.py`**:
  - Bổ sung hàm `create_hybrid_collection()` tạo collection đồng nhất schema native hybrid.
  - Bổ sung cờ CLI `--max-chunks` (hỗ trợ nạp 528 chunks có giới hạn hoặc toàn bộ).
  - Chuẩn hóa sparse weights format `{int(k) if str(k).isdigit() else str(k): float(v)}`.

### 2. Phòng Vệ Mất Dữ Liệu Trong `ocr_client.py`
- **`services/rag-service/ingestion/ocr_client.py`**:
  - Trả về `(None, None)` thay vì `([], [])` khi loại input không hỗ trợ hoặc khi buffer bytes rỗng.
- **`services/rag-service/tests/test_ocr_client.py`**:
  - Cập nhật `test_empty_input` để kiểm chứng cả `(None, None)` và `RemoteSuryaClient.is_service_failure(result) is True`.

### 3. Phòng Vệ Client History Injection Trong `chat_service.py`
- **`services/rag-service/services/chat_service.py`**:
  - Lọc bỏ tất cả tin nhắn trong client history không phải `user` hoặc `assistant`, loại trừ phần tử không phải dict.
- **`services/rag-service/tests/test_chat_service.py`**:
  - Bổ sung test case `test_build_messages_filters_client_history_roles` xác thực phòng thủ thành công trước payload độc hại.

---

## Kết Quả Xác Thực (Deterministic Verification Record)

| Hạng mục kiểm tra | Lệnh thực hiện | Kết quả |
| :--- | :--- | :--- |
| **Pytest Backend** | `uv run --with pytest --with pytest-asyncio --with pytest-mock pytest services/rag-service/tests/` | **441 passed, 1 deselected** (1.66s, 100% PASS) |
| **Root Tests** | `uv run --with pytest --with pytest-asyncio --with pytest-mock pytest tests/` | **27 passed** (5.03s, 100% PASS) |
| **Flake8 Linting** | `flake8 services/rag-service/ services/ocr-worker/ --config=services/rag-service/.flake8` | **0 errors, 0 warnings** |
| **Cleanliness Check** | `python3 scripts/check_spoke_cleanliness.py` | **12/15 budget hợp lệ, 0 rò rỉ path** |
| **Milvus Schema** | `python3 -c "from pymilvus import MilvusClient; ..."` | **id (5), vector (101), sparse_vector (104)** |
| **Milvus Indexes** | `python3 -c "from pymilvus import MilvusClient; ..."` | **vector: AUTOINDEX (COSINE), sparse_vector: SPARSE_INVERTED_INDEX (IP)** |
| **Live Smoke Test** | `./scripts/smoke_test_rag_live.sh` | **6/6 tests Green (100% PASS)** |
| **Hybrid Search Logs** | `docker compose logs --tail=50 rag-service` | **0 sparse_vector warning, 0 fallback to dense** |
