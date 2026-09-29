# Bản đồ Định hướng (Wayfinding Map): Phân Tách Quyết Định System One & System Two Trên DGX Spark RAG Pháp Lý
**Mã bản đồ:** `MAP-SPARK-SYSTEM-ONE-20260929`  
**Trạng thái:** `Completed (100% Tickets Closed — All Phases Merged)`  
**Thẩm định đối kháng:** Grok 4.7 — Phán quyết: **ACCEPTED**  
**Hệ thống liên quan:** 
- RAG Retrieval Service (`services/rag-service/retrieval/`)
- Query Classification & Routing (`services/rag-service/retrieval/query_classifier.py`)
- Evaluation Suite (`benchmarks/legal_qa_evaluator.py`)
**Hạ tầng mục tiêu:** NVIDIA DGX Spark (Grace Blackwell GB10, aarch64, CUDA 13.0, 128GB Unified Memory)  

---

## 1. Điểm đích (Destination)

Xây dựng và hoàn thiện kiến trúc phân tầng quyết định hai cấp (**System One Fast Reflex & System Two Deep Reasoning**) cho hệ thống RAG Pháp lý Việt Nam, đạt chuẩn **Tất định (Deterministic) — Tốc độ cao — Độc lập hạ tầng (100% On-premise DGX Spark GB10) — Chống ảo giác trích dẫn**:

1. **Khử Bỏ LLM Sinh Từ Khỏi Bước Rerank (Phase 1 - Hot-Path Rerank)**:
   - Xóa bỏ hoàn toàn `stage1_fast_batch_rerank` trong [search_pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/search_pipeline.py) (khử 100% cuộc gọi LLM sinh JSON index qua proxy mạng).
   - Chuyển toàn bộ tác vụ xếp hạng ứng viên sang [Reranker](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/reranker.py) sử dụng `BAAI/bge-reranker-v2-m3` thường trực trên GPU Blackwell GB10, có khóa luồng bảo vệ CUDA kernel và trần cấu hình `RERANK_MAX_CANDIDATES`.
   - Giữ nguyên vẹn các ứng viên của Hop 2 trên đường Agentic retrieval, khử trùng theo `chunk_id`, và đo lường MRR trên bộ QA pháp lý thực tế (`legal_qa_evaluator.py`).
   - Phase 1 chỉ gỡ LLM sinh JSON khỏi **bước rerank**. `rewrite_query`, HyDE và lập kế hoạch agentic vẫn là lời gọi mô hình sinh, không thuộc diff này.

2. **Chốt Chặn Kiểm Chứng Trích Dẫn 3 Tầng & Sửa Thứ Tự Phân Loại Ý Định (Phase 2 - Trust & Routing)**:
   - Xây dựng **Citation Verifier 3 Tầng** ([citation_verifier.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/citation_verifier.py)):
     - *Tầng 0 (Định danh)*: Đối chiếu số hiệu văn bản, Điều, Khoản (`doc_number`, `hierarchy_path`). Nếu là câu dẫn chiếu thuần khớp số hiệu $\to$ Giữ nguyên (`VERIFIED_POINTER`), không chuyển sang mô hình.
     - *Tầng 1 (Tách mệnh đề)*: Bóc tách nội dung khẳng định (claim) khỏi cụm từ viện dẫn.
     - *Tầng 2 (NLI Entailment)*: Sử dụng mô hình NLI đa ngữ chuyên dụng (3 nhãn: Entailment, Contradiction, Neutral) với chính sách Tri-state (gỡ mâu thuẫn, giữ entailment, gán nhãn `unverified` ở biên không chắc chắn).
   - Sửa lỗi thứ tự ưu tiên trong [query_classifier.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/query_classifier.py) để nhận diện chính xác các câu hỏi so sánh/mâu thuẫn nhiều văn bản thay vì nuốt nhầm thành `EXACT`.

---

## 2. Ghi chú & Ràng buộc Kỹ thuật (Notes)

- **Hạ tầng máy chủ**: NVIDIA DGX Spark (Grace Blackwell GB10, aarch64, CUDA 13.0, 128GB Unified Memory).
- **Ràng buộc Concurrency**: `get_reranker()` là Singleton phục vụ FastAPI bất đồng bộ (`asyncio.to_thread`). Bắt buộc phải có `threading.Lock` bao bọc hàm `predict` của `CrossEncoder` để ngăn ngừa xung đột kernel CUDA khi có nhiều request đồng thời.
- **Phân tách Rõ Ràng Nhiệm Vụ Mô Hình**:
  - `BAAI/bge-reranker-v2-m3`: Chuyên trách **Xếp hạng độ liên quan (Retrieval Relevance)**. Tuyệt đối không dùng làm bộ kiểm tra suy diễn logic (Entailment).
  - Mô hình NLI (mDeBERTa XNLI / tương đương): Chuyên trách **Kiểm chứng chống đỡ (Claim Verification)**.
- **Quy chuẩn Kiểm thử**: Bổ sung đầy đủ 6 kịch bản kiểm thử biên trong `tests/test_search_pipeline.py` (0 hit, 1 hit, 61 hits, trùng text khác `doc_number`, bảo toàn hop 2 của agentic, và không gọi `complete_json`).
- **Không dùng hệ số 7,4×–19,5× và không dùng cụm “an toàn 100%”.** Bảng latency trong TICK-01 không có script đo trong repo, nên chưa tái lập được từ cây mã này. `RERANK_MAX_CANDIDATES = 60` là mặc định tạm đến khi có MRR theo số hiệu ở trần 30, 60 và 100.

---

## 3. Quyết định đã chốt (Decisions so far)

- [x] **[DEC-01] Nguyên tắc Phân Tách Quyết Định (System One vs System Two)**: Cấm sử dụng Autoregressive Generative LLM để sinh chuỗi văn bản/JSON cho các tác vụ phân loại tập đóng, sắp xếp thứ tự hoặc kiểm tra boolean. Tách rạch ròi 3 tầng: *Tầng 0 (Code/Regex) $\to$ Tầng 1 (System One Scorer/NLI) $\to$ Tầng 2 (System Two CoT Reasoning)*.
- [x] **[DEC-02] Độc Lập Hạ Tầng & Bản Địa Hóa**: Loại bỏ hoàn toàn phương án dùng API đóng của TypeSafe Jev. Triển khai tương đương System One bằng Open-Weights Encoders và Local Models trên DGX Spark Blackwell GB10.
- [x] **[DEC-03] Nguyên Lý DRY(E) cho RAG**:
  - *Evergreen RAG* (QCVN/TCVN ổn định): Nhúng vector 1 lần vào Milvus (`legal_docs_v11`).
  - *Ad-hoc RAG* (Văn bản tạm thời, log trace): Lọc từ khóa $\to$ Đưa thẳng vào Cross-Encoder tính điểm trực tiếp, không dựng vector index tạm bợ.
- [x] **[DEC-04] Quản trị Markdown Cục bộ**: Toàn bộ Map và Ticket được lưu trữ tại `.md/wayfinder/system-one-decision-architecture/`.
- [x] **[DEC-05] Cấu Hình Trần Ứng Viên Rerank (`RERANK_MAX_CANDIDATES`) & Bảo Toàn Hop 2**: 
  - Khởi tạo hằng số `RERANK_MAX_CANDIDATES` trong `Settings` (mặc định 60).
  - Khử trùng ứng viên theo `chunk_id` trước khi cắt trần.
  - Trên luồng Agentic, dành riêng quota (tối thiểu 20 slots) cho Hop 2 để không bị Hop 1 chiếm dụng toàn bộ danh sách.
  - Đo lường và đối soát MRR thực tế qua `legal_qa_evaluator.py` ở các mức trần 30, 60, 100 trước khi đóng cứng cấu hình.
- [x] **[DEC-06] Kiến Trúc Chốt Chặn Trích Dẫn 3 Tầng (Tầng 0 Định Danh + NLI)**: Bác bỏ việc dùng điểm relevance của `bge-reranker-v2-m3` làm cổng xóa footnote. Áp dụng kiến trúc 3 tầng: Tầng 0 (đối chiếu `doc_number` và `hierarchy_path`) $\to$ Tầng 1 (tách mệnh đề) $\to$ Tầng 2 (NLI Entailment chuyên dụng).

---

## 4. Danh sách Ticket & Biên giới (Frontier Tickets)

| Mã Ticket | Tên Ticket | Phân loại | Giai đoạn | Trạng thái | Assignee |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **[TICK-01](tickets/TICK-01-audit-and-benchmark-hotpath-reranker.md)** | [Khảo sát Hiện trạng & Thiết lập Benchmark Baseline cho Hot-Path Reranker](tickets/TICK-01-audit-and-benchmark-hotpath-reranker.md) | `Research [AFK]` | Phase 1 | **Completed (Done)** | Antigravity Agent (`6f26fae5`) |
| **[TICK-02](tickets/TICK-02-refactor-search-pipeline-bge-reranker.md)** | [Refactor search_pipeline.py: Khử bỏ stage1 LLM & Kết nối Trực tiếp BGE-Reranker](tickets/TICK-02-refactor-search-pipeline-bge-reranker.md) | `Task [AFK]` | Phase 1 | **Completed (Done)** | **Grok 4.7** (Supervisor: Antigravity) |
| **[TICK-04](tickets/TICK-04-fix-query-classifier-rule-precedence.md)** | [Tinh Chỉnh Thứ Tự Rule Phân Loại Ý Định trong query_classifier.py](tickets/TICK-04-fix-query-classifier-rule-precedence.md) | `Task [AFK]` | Phase 2 | **Completed (Done)** | **Grok 4.7** (Supervisor: Antigravity) |
| **[TICK-03](tickets/TICK-03-noul-citation-verifier-design.md)** | [Thiết kế Citation Verifier 3 Tầng: Định Danh Kết Hợp NLI Entailment](tickets/TICK-03-noul-citation-verifier-design.md) | `Research [AFK]` | Phase 2 | **Completed (Done)** | Antigravity Agent (Auditor: Grok 4.7) |
| **[TICK-05](tickets/TICK-05-implement-three-tier-citation-verifier.md)** | [Triển Khai Module Citation Verifier 3 Tầng](tickets/TICK-05-implement-three-tier-citation-verifier.md) | `Task [AFK]` | Phase 2 | **Completed (Done)** | **Grok 4.7** (Supervisor: Antigravity) |

---

## 5. Sương mù chiến trận / Chưa xác định rõ (Not yet specified)

- **[FOG-01] Quy Chuẩn Tập Dữ Liệu Gán Nhãn Cho NLI Verifier**: Cần tập gán nhãn gồm $\approx 600$ cặp (200 entailment, 200 không chống đỡ/mâu thuẫn, 200 hard negative cùng văn bản/điều kề bên, cộng lớp con trỏ dẫn chiếu thuần) để hiệu chuẩn Temperature Scaling trên tập giữ lại độc lập.

---

## 6. Ngoài phạm vi của Bản đồ này (Out of scope)

- **Hệ sinh thái BIM QC và Maskara PII**: Tách thành các Bản đồ Định hướng độc lập khi các packages `ccba-bim-qc` và `ccba-maskara` được khởi tạo trong codebase. Tuyệt đối không đẩy secret thô vào hàng đợi `hitl:review_queue` của Redis DB 4 (vốn dành riêng cho RAG Review QA).
- Tích hợp dịch vụ API đám mây thương mại đóng của Jev TypeSafe (vi phạm chủ quyền dữ liệu).
- Thay thế vai trò của Qwen 3.6 35B / Claude trong các tác vụ suy luận pháp lý đa bước hoặc soạn thảo câu trả lời chuyên sâu (System Two CoT là bài toán không thể thay thế).
