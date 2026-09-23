# Walkthrough: Gói Tinh Chỉnh Hoàn Thiện (KISS Patch) & Triệt Tiêu Điểm Mù Kiến Trúc

## Tổng Quan

Gói tinh chỉnh hoàn thiện (KISS Patch) được triển khai nhằm bịt kín 4 điểm mù kiến trúc được xác định trong Báo cáo Thẩm định Đối kháng (/boost):

1. **Khắc phục lỗi mất dữ liệu ngầm (Silent Data Loss Domino)** giữa `RemoteSuryaClient` và `vision.py`.
2. **Gia cố an toàn bộ nhớ & concurrency cho `ocr-worker`** (Semaphore concurrency = 1, `torch.inference_mode()`, nâng giới hạn RAM lên 8GB).
3. **Triệt tiêu 100% 7 CVEs LangChain** (gỡ bỏ hoàn toàn `langchain`, `langchain-community`, xóa shims cũ, tái biên dịch cả 2 lockfiles đạt 0 CVEs tuyệt đối).
4. **Gia cố khả năng phục hồi Milvus Hybrid Search** (fallback sang dense search khi thiếu trường sparse_vector).

---

## Chi Tiết Các Thay Đổi

### 1. Khắc Phục Silent Data Loss Domino
- **`services/rag-service/ingestion/ocr_client.py`**:
  - Khi worker gặp sự cố (HTTP error, connection timeout, read timeout, circuit breaker OPEN, exception), `process_page()` trả về `(None, None)` thay vì `([], [])`.
  - Thêm phương thức `RemoteSuryaClient.is_service_failure(result)` phân biệt rõ ràng giữa trang rỗng thật sự `([], [])` và lỗi dịch vụ `(None, None)`.
  - Các wrapper backward-compatible `ocr()` và `extract_layout()` bảo vệ trả về `[]` khi nhận `None`.
- **`services/rag-service/ingestion/vision.py`**:
  - `is_blank_page()` nhận tham số `ocr_raw`, tự động trả về `False` nếu `ocr_raw is None`, đồng thời nâng ngưỡng an toàn `white_ratio` từ `0.85` lên `0.90`.
  - Trong luồng xử lý `process_page()`: nếu `ocr_raw is None`, ghi nhận logger warning, **bỏ qua hoàn toàn việc gọi `is_blank_page()` và `is_toc_page()`**, trực tiếp kích hoạt nhánh fallback Vision LLM (`call_vision_fallback`).

### 2. Gia Cố Concurrency & Bộ Nhớ Cho `ocr-worker`
- **`services/ocr-worker/main.py`**:
  - Thêm `_ocr_semaphore = threading.Semaphore(1)` bọc quanh `extractor.process(file)` nhằm giới hạn tối đa 1 tác vụ tính toán PyTorch CPU tại một thời điểm, loại trừ nguy cơ OOM crash khi có tải song song.
- **`services/ocr-worker/extractor.py`**:
  - Bọc tất cả các lần gọi predictor (Detection, Recognition mini-batches, Layout) với `with _inference_mode():` (`torch.inference_mode()`) để giải phóng ngay lập tức tensor graph bộ nhớ.
- **`docker-compose.yml`**:
  - Nâng giới hạn RAM cho `ocr-worker` từ `memory: 6G` lên `memory: 8G` trên hệ thống DGX Spark (128GB Unified Memory).

### 3. Triệt Tiêu 100% CVEs LangChain (Đạt 0 CVEs Tuyệt Đối)
- **`services/rag-service/ingestion/vision.py`**:
  - Xóa bỏ 18 dòng code shimming LangChain không còn sử dụng cho PaddleOCR.
- **`services/rag-service/requirements-app.in` & `requirements-ci.txt`**:
  - Gỡ bỏ `langchain` và `langchain-community`.
- **Tái biên dịch lockfiles**:
  - `requirements-app.lock`: biên dịch qua `uv pip compile` kèm cờ `--no-emit-package`.
  - `requirements-ci.lock`: biên dịch qua `uv pip compile`.
- **Kiểm tra an ninh**:
  - `uvx pip-audit -r services/rag-service/requirements-app.lock` -> **0 CVEs**.
  - `uvx pip-audit -r services/rag-service/requirements-ci.lock` -> **0 CVEs**.
- **`scripts/check_dependency_updates.sh`**:
  - Xóa chuỗi thông báo lỗi thời `pillow locked by surya-ocr`.

### 4. Khả Năng Tự Phục Hồi Milvus Hybrid Search
- **`services/rag-service/repositories/milvus_repo.py`**:
  - Bọc `hybrid_search()` trong khối `try/except`. Khi Milvus ném lỗi thiếu `sparse_vector` (ví dụ collection khởi tạo dạng dense-only), tự động fallback sang `client.search()` với dense vector thay vì ném lỗi HTTP 500.

---

## Kết Quả Xác Thực (Verification Record)

| Hạng mục kiểm tra | Lệnh thực hiện | Kết quả |
| :--- | :--- | :--- |
| **Pytest Backend** | `pytest services/rag-service/tests/` | **435 passed, 1 deselected, 0 errors** (1.46s) |
| **Flake8 Linting** | `flake8 services/rag-service/ --config=.flake8` | **0 errors, 0 warnings** |
| **Cleanliness Check** | `python3 scripts/check_spoke_cleanliness.py` | **12/15 budget hợp lệ, 0 rò rỉ path** |
| **App Security Audit** | `uvx pip-audit -r requirements-app.lock` | **0 known vulnerabilities found** |
| **CI Security Audit** | `uvx pip-audit -r requirements-ci.lock` | **0 known vulnerabilities found** |
| **Audit Script** | `./scripts/check_dependency_updates.sh --audit` | **Passed (Code 0, All checks clean)** |
| **Docker Build** | `docker compose build ocr-worker rag-service` | **2/2 images built successfully** |
| **Live Smoke Test** | `./scripts/smoke_test_rag_live.sh` | **6/6 tests Green (100% PASS)** |
