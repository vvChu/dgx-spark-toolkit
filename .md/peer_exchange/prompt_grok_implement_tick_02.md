# Nhiệm Vụ Thi Công Kỹ Thuật (Implementation Assignment): TICK-02

**Người giao việc & Giám sát:** Antigravity Agent (Supervisor & Quality Gatekeeper)  
**Người nhận việc & Thi công:** Grok 4.7 (Assignee)  
**Nhánh Git:** `refactor/search-pipeline-bge-reranker` (đã checkout từ `master` mới nhất)  
**Hồ sơ tham chiếu:**
- Ticket: `.md/wayfinder/system-one-decision-architecture/tickets/TICK-02-refactor-search-pipeline-bge-reranker.md`
- Phản biện đối kháng của chính bạn: `.md/peer_exchange/grok_review_wayfinder_map.md` (mục 3 và mục 6)

---

## 1. Yêu Cầu Cốt Lõi (Core Mandate)
Bạn hãy trực tiếp sửa code, chạy test và hoàn tất việc refactor loại bỏ hoàn toàn `stage1_fast_batch_rerank`, chuyển sang `bge-reranker-v2-m3` trực tiếp, thỏa mãn 100% 8 điều kiện kỹ thuật mà bạn đã nêu trong báo cáo phản biện.

---

## 2. Chi Tiết Các File Cần Chỉnh Sửa

### 1. `services/rag-service/core/config.py`:
- Thêm cấu hình trong `Settings`:
  ```python
  RERANK_MAX_CANDIDATES: int = 60
  RERANK_EXACT_CANDIDATES: int = 20
  RERANK_AGENTIC_HOP2_MIN_QUOTA: int = 20
  ```

### 2. `services/rag-service/retrieval/reranker.py`:
- Thêm `self._predict_lock = threading.Lock()` trong `Reranker.__init__`.
- Trong `rerank_sync`:
  - Khóa thread quanh lệnh `self.model.predict(...)`:
    ```python
    with self._predict_lock:
        scores = self.model.predict(pairs, batch_size=32)
    ```
  - Bao bọc `try/except Exception as e:` quanh quá trình dự đoán: nếu gặp lỗi CUDA hoặc OOM, ghi log warning và fallback trả về danh sách ứng viên với điểm gốc (hoặc điểm 0.0) thay vì làm sập toàn bộ request.
  - Hỗ trợ trả về chỉ số gốc hoặc map index để tránh lỗi va chạm khi hai chunk có cùng `text` (xem gợi ý mục 3).

### 3. `services/rag-service/retrieval/search_pipeline.py`:
- **Xóa bỏ hoàn toàn** hàm `stage1_fast_batch_rerank` (dòng 178–227).
- Trong `_stage_rerank_and_score`:
  - **Khử trùng (Dedup)**: Khử trùng các hits trong `ctx.raw_hits` theo `chunk_id` (nếu không có `chunk_id` thì fallback theo hash text).
  - **Xác định trần `max_candidates`**:
    - Nếu `ctx.intent == QueryIntent.EXACT`: dùng `settings.RERANK_EXACT_CANDIDATES` (20).
    - Ngược lại: dùng `settings.RERANK_MAX_CANDIDATES` (60).
  - **Bảo tồn Quota cho Hop 2**:
    - Nếu trong `ctx.raw_hits` có cả hit từ hop 1 và hop 2 (kiểm tra qua metadata hoặc tách danh sách): Đảm bảo các hit của hop 2 được giữ lại tối thiểu `RERANK_AGENTIC_HOP2_MIN_QUOTA` (20 slots), phần còn lại lấp bằng hop 1 cho đến khi đủ `max_candidates`.
  - **Tránh va chạm Text trùng nhau (Text Collision Fix)**:
    - Thay vì dùng `dict` với key là `doc_text`, hãy dùng index song song giữa `candidate_hits` và kết quả trả về của reranker. (Ví dụ: `rerank` trả về kèm chỉ số `original_idx`, hoặc `indexed_scores = [(idx, score)]` để lookup trực tiếp `candidate_hits[idx]`). Điều này giải quyết triệt để lỗi va chạm text mà bạn đã cảnh báo ở mục 3.2.
  - **Bảo toàn công thức Hybrid Score**:
    `hybrid_score = (float(score) * settings.RERANK_WEIGHT) + (_get_hit_score(hit) * settings.MILVUS_WEIGHT) + table_boost + validity_boost`
    và sắp xếp giảm dần theo `hybrid_score`.

### 4. `services/rag-service/tests/test_search_pipeline.py`:
- Viết thêm bộ test cases bao quát 6 ca kiểm thử biên:
  1. `test_rerank_empty_hits`: 0 hit $\to$ trả về rỗng, không lỗi.
  2. `test_rerank_single_hit`: 1 hit $\to$ xử lý bình thường.
  3. `test_rerank_safety_cap_60`: 65 hits $\to$ `mock_reranker.rerank` chỉ nhận đúng 60 docs, hit thứ 61..65 không được gửi vào.
  4. `test_rerank_duplicate_text_different_metadata`: 2 hits có cùng nội dung `text` nhưng khác `doc_number` $\to$ cả 2 đều giữ đúng metadata của mình, không bị đè metadata.
  5. `test_rerank_preserves_agentic_hop2`: Candidate set gồm 50 hits hop 1 và 15 hits hop 2 $\to$ danh sách đưa vào rerank vẫn chứa đầy đủ các hits của hop 2.
  6. `test_rerank_does_not_call_complete_json`: Khẳng định `complete_json` của `ai_client` không hề được gọi trong suốt quá trình rerank.

---

## 3. Tiêu Chí Nghiệm Thu (Quality Gate Để Antigravity Ký Duyệt)
1. Chạy pass 100% toàn bộ unit tests:
   ```bash
   pytest services/rag-service/tests/
   ```
2. Chạy kiểm tra lint sạch lỗi:
   ```bash
   flake8 services/rag-service/ --config=services/rag-service/.flake8
   ```
3. Sau khi hoàn thành, hãy cập nhật báo cáo nghiệm thu vào `.md/peer_exchange/grok_implementation_tick_02.md` và thông báo tóm tắt các thay đổi.
