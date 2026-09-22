# Ticket [TICK-02]: Hoàn thiện Stub Conftest & Tối ưu Tốc độ CI Runner

**Bản đồ cha:** [Bản đồ Định hướng Hiện đại hóa Dependency](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 22/09/2026  
**Phụ thuộc:** Không có (Unblocked)  

---

## 1. Mục tiêu đã hoàn thành
Giải phóng CI runner x86_64 khỏi các thư viện nặng (`sentence-transformers`, `FlagEmbedding`, `torch` CPU ~800MB) bằng cách hoàn thiện stubbing tại [conftest.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/tests/conftest.py), giúp rút ngắn thời gian cài đặt CI xuống $\le 15$ giây mà không làm sập bất kỳ unit test nào.

## 2. Chi tiết Triển khai đã áp dụng
1. Đã sửa [services/rag-service/tests/conftest.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/tests/conftest.py):
   - Bổ sung stub hermetic cho module `sentence_transformers` (`CrossEncoder` và `SentenceTransformer`).
   - Bổ sung stub cho module `FlagEmbedding` (`BGEM3FlagModel`).
   - Giữ nguyên stub `bge_m3_hybrid`.
2. Đã tinh gọn [services/rag-service/requirements-ci.txt](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-ci.txt):
   - Loại bỏ hoàn toàn `FlagEmbedding[sparse]>=1.2.0` và `sentence-transformers>=2.2.0`.
   - Giữ lại các gói web, pydantic, db-clients, và test tools.
3. Đã biên dịch lockfile tất định [services/rag-service/requirements-ci.lock](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-ci.lock) qua `uv pip compile`.

## 3. Nghiệm thu Thực tế
- [x] Chạy kiểm thử hermetic `venv/bin/python -m pytest tests/ -v` pass 100% (**405 passed, 1 deselected trong 2.03s**).
- [x] Không xuất hiện bất kỳ lỗi `ModuleNotFoundError` nào liên quan đến `sentence_transformers` hay `FlagEmbedding`.
- [x] Linter flake8 trên `conftest.py` đạt chuẩn 0 lỗi.
- [x] CI runner trên GitHub Actions sẽ không còn tải wheel PyTorch CPU (~800MB), ước tính thời gian cài đặt giảm từ ~2m45s xuống $\le 15$s.
