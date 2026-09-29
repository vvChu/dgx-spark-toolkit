# Báo Cáo Nghiệm Thu Thi Công Kỹ Thuật (Supervisory Sign-off Report): TICK-02

**Đơn vị thực hiện (Assignee):** Grok 4.7  
**Đơn vị giám sát & nghiệm thu (Supervisor):** Antigravity Agent  
**Thời điểm nghiệm thu:** 2026-09-29 06:40 ICT  
**Nhánh Git:** `refactor/search-pipeline-bge-reranker`  
**Hồ sơ liên quan:** 
- Ticket: `.md/wayfinder/system-one-decision-architecture/tickets/TICK-02-refactor-search-pipeline-bge-reranker.md`
- Phản biện đối kháng Grok 4.7: `.md/peer_exchange/grok_review_wayfinder_map.md`

---

## 1. Kết Quả Giám Sát Đối Soát Mã Nguồn (Code Inspection)

Antigravity đã thực hiện rà soát chi tiết toàn bộ các tệp mã nguồn do Grok 4.7 sửa đổi và đối chiếu với 8 điều kiện phản biện đối kháng:

### [Điều kiện 1] Khử bỏ hoàn toàn LLM Rerank
- **Mã nguồn**: Hàm `stage1_fast_batch_rerank` (vốn gửi 30 chunks sang `claude-haiku-4` qua proxy) đã bị **xóa sạch 100%** khỏi `services/rag-service/retrieval/search_pipeline.py`.
- **Kiểm thử**: `test_rerank_does_not_call_complete_json` xác nhận `complete_json` không được gọi hay await trong suốt quá trình rerank.
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 2] Cấu hình trần linh hoạt trong `Settings`
- **Mã nguồn**: Đã thêm 3 hằng số vào `services/rag-service/core/config.py`:
  - `RERANK_MAX_CANDIDATES: int = 60`
  - `RERANK_EXACT_CANDIDATES: int = 20`
  - `RERANK_AGENTIC_HOP2_MIN_QUOTA: int = 20`
- **Logic**: Khi `ctx.intent == QueryIntent.EXACT`, tự động dùng trần hẹp 20 chunks; ngược lại dùng trần 60 chunks.
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 3] Bảo tồn Quota cho Agentic Hop 2
- **Mã nguồn**:
  - Gắn nhãn hop cho các hits ở Hop 2: `_mark_hit_hop(hit, 2)`.
  - Hàm `_select_rerank_candidates` tách riêng danh sách Hop 2 và Hop 1. Dành riêng tối thiểu `RERANK_AGENTIC_HOP2_MIN_QUOTA` (20 slots) cho Hop 2, phần còn lại lấp đầy bằng Hop 1.
- **Kiểm thử**: `test_rerank_preserves_agentic_hop2` kiểm thử tập 50 hits Hop 1 + 15 hits Hop 2 $\to$ toàn bộ 15 hits Hop 2 được bảo toàn nguyên vẹn trong danh sách rerank.
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 4] Khử trùng & Khóa định danh `chunk_id`
- **Mã nguồn**:
  - `_dedup_hits`: Khử trùng các hits theo `chunk_id` (fallback bằng hash sha1 của text).
  - `reranker.py`: `rerank_sync` trả về tuple 3 phần tử `(text, score, original_idx)`.
  - `search_pipeline.py`: Sử dụng `_resolve_candidate_hit` truy xuất trực tiếp `candidate_hits[original_idx]`. Giải quyết triệt để lỗi va chạm metadata khi 2 chunk có text trùng nhau.
- **Kiểm thử**: `test_rerank_duplicate_text_different_metadata` và `test_rerank_dedup_same_chunk_id` pass 100%.
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 5] Khóa luồng bảo vệ CUDA Kernel trong Singleton Reranker
- **Mã nguồn**:
  - Khởi tạo `self._predict_lock = threading.Lock()` trong `Reranker.__init__`.
  - Bao bọc `with self._predict_lock: scores = self.model.predict(...)`.
  - Bổ sung `try/except Exception as e`: khi gặp lỗi OOM hoặc CUDA runtime, ghi log warning và fallback giữ nguyên thứ tự ứng viên với điểm 0.0 (`preserve_order = True`).
- **Kiểm thử**: `test_predict_is_locked_and_truncates_input`, `test_predict_error_returns_original_order`, và `test_rerank_exception_keeps_candidate_order` pass 100%.
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 6] Bổ sung Metrics giám sát Rerank
- **Mã nguồn**: Đã khai báo và quan sát 2 Prometheus metrics:
  - `RERANK_CANDIDATES = Histogram("rag_rerank_candidates", ...)`
  - `RERANK_LATENCY = Histogram("rag_rerank_latency_seconds", ...)`
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 7] Bộ Test Suite 6 Ca Kiểm Thử Biên
- Đã bổ sung 9 test cases chuyên sâu trong `tests/test_search_pipeline.py` và 3 test cases trong `tests/test_reranker.py`.
- **Đánh giá**: **ĐẠT (PASS)**.

### [Điều kiện 8] Đo lường & Tính năng Evaluator
- `benchmarks/legal_qa_evaluator.py` đã được mở rộng tham số `--candidate-cap` và `--retrieval-only` để sẵn sàng cho các vòng sweep benchmarking.
- **Đánh giá**: **ĐẠT (PASS)**.

---

## 2. Kết Quả Kiểm Định Chất Lượng Toàn Diện (Full Suite Verification)

- **Backend Pytest Suite**:
  ```bash
  services/rag-service/venv/bin/pytest services/rag-service/tests/
  # KẾT QUẢ: 540 passed, 1 deselected, 1 warning in 10.78s
  ```
- **Flake8 Lint**:
  ```bash
  services/rag-service/venv/bin/flake8 services/rag-service/ --config=services/rag-service/.flake8
  # KẾT QUẢ: 0 exit code, clean 100%
  ```

---

## 3. Phán Quyết Nghiệm Thu (Final Acceptance Decision)

> **KẾT LUẬN NGHIỆM THU:** **FINAL ACCEPT (CHẤP THUẬN NGHIỆM THU HOÀN TOÀN)**.  
> Grok 4.7 đã hoàn thành xuất sắc nhiệm vụ thi công `TICK-02`, thỏa mãn 100% tất cả 8 điều kiện phản biện đối kháng đã đề ra mà không gây ra bất kỳ hồi quy nào trên 540 unit tests của hệ thống.
> 
> **Thao tác tiếp theo**:
> 1. Đóng `TICK-02` trên Bản đồ Wayfinder (`map.md`).
> 2. Mở khóa `TICK-03` (`Citation Verifier 3 Tầng`) tại Biên giới (Frontier).
