# Ticket [TICK-02]: Refactor search_pipeline.py: Khử bỏ stage1 LLM & Kết nối Trực tiếp BGE-Reranker (Kèm 8 Điều Kiện Phản Biện Đối Kháng)

**Bản đồ cha:** [Bản đồ Định hướng Phân tách Quyết định System One & System Two](../map.md)  
**Phân loại:** `Task [AFK]`  
**Giai đoạn:** Phase 1 (Hot-path Retrieval)  
**Trạng thái:** `Completed (Done)`  
**Thẩm định đối kháng:** Grok 4.7 — Phán quyết: **FINAL ACCEPT** (Xem biên bản nghiệm thu tại [.md/peer_exchange/grok_implementation_tick_02.md](../../peer_exchange/grok_implementation_tick_02.md))  
**Assignee (Người thực hiện):** **Grok 4.7**  
**Supervisor & Reviewer (Giám sát & Nghiệm thu):** **Antigravity Agent**  
**Ngày hoàn tất:** 29/09/2026  
**Phụ thuộc:** [TICK-01](TICK-01-audit-and-benchmark-hotpath-reranker.md) (Đã hoàn tất)  

---

## 1. Mục tiêu
Thực hiện refactor mã nguồn [services/rag-service/retrieval/search_pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py) và [services/rag-service/retrieval/reranker.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/reranker.py) nhằm:
1. Xóa bỏ hoàn toàn hàm `stage1_fast_batch_rerank` (khử 100% việc gọi LLM sinh JSON index trong khâu rerank).
2. Tinh giản phương thức `_stage_rerank_and_score`: Áp dụng trần an toàn `RERANK_MAX_CANDIDATES` trong `Settings` (mặc định 60).
3. Đảm bảo toàn bộ 8 điều kiện kỹ thuật phản biện của Grok 4.7 để bảo vệ tính toàn vẹn của đường Agentic hop 2, khóa thread an toàn CUDA, và khóa định danh `chunk_id`.
4. Bổ sung bộ test suite 6 kịch bản biên và đảm bảo 100% tests pass.

---

## 2. Tám Điều Kiện Kỹ Thuật Bắt Buộc (Grok 4.7 Mandates)

1. **Khử bỏ LLM Rerank**: Xóa sạch hàm `stage1_fast_batch_rerank` (dòng 178–227) và mọi cuộc gọi `complete_json` trong khâu rerank.
2. **Cấu hình Trần Linh Hoạt (`RERANK_MAX_CANDIDATES`)**:
   - Thêm `RERANK_MAX_CANDIDATES: int = 60` vào [config.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/core/config.py).
   - Với truy vấn `EXACT`: sử dụng trần hẹp hơn (ví dụ 20 candidates).
3. **Bảo tồn Quota cho Agentic Hop 2**:
   - Khi chạy luồng Agentic, không cắt `raw_hits[:60]` thô bạo khiến hop 2 bị rơi rụng ở cuối danh sách.
   - Cơ chế cắt: Dành riêng hạn mức tối thiểu (ví dụ 20 slots) cho Hop 2, phần còn lại lấp đầy bằng Hop 1 sau khi đã khử trùng.
4. **Khử Trùng (Dedup) & Khóa Định Danh Bằng `chunk_id`**:
   - Khử trùng danh sách ứng viên dựa trên `chunk_id` trước khi cắt trần.
   - Khóa ánh xạ `hit_map` bằng `chunk_id` thay vì chuỗi `text` thô để tránh va chạm khi hai chunk có nội dung giống nhau nhưng khác văn bản/điều khoản.
5. **Khóa Luồng Bảo Vệ CUDA Kernel Trong `Reranker`**:
   - Thêm `threading.Lock` quanh khối `self.model.predict(...)` trong `reranker_sync` để ngăn chặn xung đột tài nguyên GPU khi nhiều request chạy song song.
   - Thêm khối `try/except` bao bọc lệnh `rerank`: nếu xảy ra lỗi CUDA, ghi log cảnh báo và fallback giữ nguyên thứ tự ứng viên Milvus/RRF thay vì làm sập toàn bộ request.
6. **Bổ Sung Metrics Giám Sát Rerank**:
   - Thêm tracer step hoặc Prometheus metrics riêng cho độ trễ rerank và số lượng ứng viên đưa vào chấm điểm.
7. **Bộ Test Suite 6 Ca Kiểm Thử Biên trong `tests/test_search_pipeline.py`**:
   - Ca 1: `raw_hits` rỗng (0 hit) $\to$ trả về rỗng không lỗi.
   - Ca 2: `raw_hits` 1 hit $\to$ xử lý bình thường.
   - Ca 3: `raw_hits` 61 hits $\to$ đối số truyền vào `rerank()` có độ dài chính xác 60, hit thứ 61 không xuất hiện.
   - Ca 4: Hai hit trùng `text` nhưng khác `doc_number` $\to$ giữ đúng metadata của từng chunk nhờ khóa `chunk_id`.
   - Ca 5: Đường agentic với Hop 1 dài (50 hits) và Hop 2 ngắn (15 hits) $\to$ Hop 2 vẫn được bảo toàn slot trong danh sách rerank.
   - Ca 6: Khẳng định `complete_json` không được gọi trong suốt quá trình rerank.
8. **Đo Lường MRR Đối Soát**:
   - Chạy `benchmarks/legal_qa_evaluator.py` để ghi nhận MRR ở các mức trần 30, 60, và 100 trên tập dữ liệu hỏi đáp pháp lý hiện có.

---

## 3. Kế Hoạch Thực Hiện
1. Cập nhật `services/rag-service/core/config.py`: bổ sung `RERANK_MAX_CANDIDATES = 60` và `RERANK_EXACT_CANDIDATES = 20`.
2. Cập nhật `services/rag-service/retrieval/reranker.py`: bổ sung `_predict_lock = threading.Lock()` và bọc `predict()`.
3. Refactor `services/rag-service/retrieval/search_pipeline.py`:
   - Xóa bỏ `stage1_fast_batch_rerank`.
   - Tái cấu trúc `_stage_rerank_and_score`: dedup theo `chunk_id`, phân bổ quota hop 2, khóa `hit_map` bằng `chunk_id`, fallback graceful khi `rerank` gặp lỗi.
4. Cập nhật và bổ sung test cases trong `services/rag-service/tests/test_search_pipeline.py`.
5. Chạy `pytest services/rag-service/tests/` và `flake8`.
6. Chạy đánh giá MRR baseline qua `benchmarks/legal_qa_evaluator.py`.

---

## 4. Tiêu chí Nghiệm thu
- [ ] Xóa sạch hàm `stage1_fast_batch_rerank` khỏi `search_pipeline.py`.
- [ ] Áp dụng cấu hình `RERANK_MAX_CANDIDATES` từ Settings và khóa thread CUDA trong `Reranker`.
- [ ] Bảo tồn Hop 2 của luồng Agentic retrieval và khóa metadata theo `chunk_id`.
- [ ] Đầy đủ 6 test case biên mới được viết và pass 100%.
- [ ] 100% backend unit tests pass: `pytest services/rag-service/tests/`.
- [ ] Flake8 kiểm tra sạch lỗi.
