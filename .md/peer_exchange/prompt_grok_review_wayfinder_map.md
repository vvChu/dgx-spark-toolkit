# Yêu Cầu Phản Biện Đối Kháng (Adversarial Review Request): Bản Đồ Định Hướng Wayfinder Cho Kiến Trúc Phân Tách Quyết Định System One & System Two

## Bối Cảnh (Context)
Bạn là **Grok 4.7**, đóng vai trò **Peer Reviewer đối kháng (Adversarial Peer Reviewer) & Kỹ sư Trưởng Hệ thống AI** cho máy chủ **NVIDIA DGX Spark** (Grace Blackwell GB10, 128GB Unified Memory, aarch64, Ubuntu Linux).

Sau cuộc nghiên cứu chuyên sâu về mô hình "System One" Jev (TypeSafe AI) và bài phân tích của John Kutay (Rippling) ngày 27/09/2026, Antigravity Agent đã thiết lập **Bản đồ Định hướng Wayfinder (`MAP-SPARK-SYSTEM-ONE-20260929`)** tại thư mục `.md/wayfinder/system-one-decision-architecture/`.

Người dùng yêu cầu bạn **rà soát đối kháng, vạch lá tìm sâu, phản biện độc lập** toàn bộ Bản đồ này, bao gồm:
1. Kết quả thực nghiệm và tự phản biện trong **TICK-01** (đã hoàn thành).
2. Kế hoạch refactor hot-path trong **TICK-02** (chuẩn bị thực thi).
3. Đề xuất kiến trúc Citation Noul Gate trong **TICK-03**.
4. 4 vùng sương mù chiến trận (**FOG-01 $\to$ FOG-04**).

Hãy xuất bản toàn văn báo cáo phản biện độc lập của bạn vào tệp:
`.md/peer_exchange/grok_review_wayfinder_map.md`

---

## Toàn Văn Hồ Sơ Đang Chờ Thẩm Định (Dossier Under Review)

### 1. Bản Đồ Định Hướng Chính (`map.md`)
- **Mã bản đồ**: `MAP-SPARK-SYSTEM-ONE-20260929`
- **Điểm đích (Destination)**: Xây dựng hệ thống phân tách quyết định 2 tầng trên DGX Spark và CCBA Platform:
  - *Phase 1*: Khử bỏ hoàn toàn System Two (LLM sinh JSON) trên hot-path retrieval của RAG; chuyển sang `BAAI/bge-reranker-v2-m3` trực tiếp trên GPU GB10.
  - *Phase 2*: Chốt chặn kiểm chứng trích dẫn luật không ảo giác (**Citation Noul Gate**) và bộ định tuyến ý định siêu tốc (**Fast Intent Classifier**).
  - *Phase 3*: Mở rộng Typed Decisions sang **BIM QC Error Classifier** và **Maskara Secret/PII Scorer** (kèm hàng đợi HITL trên Redis DB 4).
- **Quyết định đã chốt**:
  - `[DEC-01]`: Cấm dùng LLM sinh từ tự do cho các bài toán phân loại tập đóng, rerank, boolean gate. Tách 3 tầng: Code/Regex $\to$ System One Scorer $\to$ System Two CoT.
  - `[DEC-02]`: Chủ quyền dữ liệu tuyệt đối (Sovereignty) — Không dùng Cloud API của TypeSafe Jev. Dùng Open-weights chạy 100% on-premise trên GB10.
  - `[DEC-03]`: Nguyên lý DRY(E) — Evergreen RAG dùng Milvus; Ad-hoc RAG dùng bộ lọc nhanh + Cross-Encoder tính điểm trực tiếp (Zero Embedding Pipeline).
  - `[DEC-04]`: Quản trị bản đồ và ticket qua Markdown cục bộ trong `.md/wayfinder/`.
  - `[DEC-05]`: Thiết lập trần an toàn $N=60$ candidates trong `_stage_rerank_and_score`.

---

### 2. Dữ Liệu Thực Nghiệm Từ TICK-01 (Đã hoàn thành)
- **Rà soát Test Suite**: 0 test case nào gọi hay mock `stage1_fast_batch_rerank`. An toàn 100% khi refactor.
- **Lỗ hổng mã nguồn cũ**: Cắt cứng `docs[:30]` gửi vào prompt LLM; nếu candidate set có 60–100 chunks thì chunks 31..100 bị vứt bỏ trong mù quáng.
- **Tự phản biện giả thuyết ban đầu (Double-Pass Adversarial Fact Check)**:
  - Giả thuyết ban đầu *"BGE-Reranker-v2-m3 có thể xử lý 60-100 chunks trong < 50ms"* đã bị **BÁC BỎ**. Cross-Encoder tính full cross-attention qua 24 layers, mất $\sim 21.5\text{ms}$/chunk trên GB10.
  - Đo thực tế trên GB10 (batch size = 32):
    - $N=30$ chunks (~1300 ký tự): 678.77 ms (P95: 734.02 ms).
    - $N=60$ chunks (~1300 ký tự): 1,294.36 ms (P95: 1,299.81 ms). *(Với chunk ngắn ~500 ký tự: chỉ mất 494.87 ms)*.
    - $N=100$ chunks: 2,162.65 ms.
    - VRAM peak: 2,699.6 MB (activation chỉ tăng 31 MB, không có nguy cơ OOM).
  - So với luồng cũ gọi LLM qua Gateway bị timeout/retry mất $\sim 9,550\text{ms}$ $\implies$ BGE Reranker trực tiếp nhanh hơn $7.4\times - 19.5\times$, tất định, 0 token cost.

---

### 3. Thiết Kế Refactor Trong TICK-02 (Chuẩn bị thực thi)
- **Tệp chỉnh sửa**: `services/rag-service/retrieval/search_pipeline.py`.
- **Hành động**:
  1. Xóa sạch hàm `stage1_fast_batch_rerank` (dòng 178–227).
  2. Trong `_stage_rerank_and_score`:
     ```python
     # Thay thế nhánh len(docs) > 60 bằng trần an toàn 60 ứng viên:
     candidate_hits = ctx.raw_hits[:60]
     candidate_docs = [_get_hit_entity(hit).get("text", "") for hit in candidate_hits]

     reranker = get_reranker()
     reranked = await reranker.rerank(ctx.raw_query, candidate_docs, top_k=max(ctx.limit * 2, 10))
     ```
  3. Bổ sung test case kiểm thử khi candidate set $> 60$ hits trong `tests/test_search_pipeline.py`.

---

### 4. Đề Xuất Citation Noul Gate Trong TICK-03 & Vùng Sương Mù (Phase 2 & 3)
- **TICK-03 (Citation Noul Gate)**:
  - Dùng `bge-reranker-v2-m3` chấm điểm cặp `(Claim, Source_Chunk)`.
  - Nếu điểm số $< \tau_{\text{citation}}$ $\implies$ Tước bỏ trích dẫn hoặc cảnh báo không có căn cứ.
- **Sương mù chiến trận (FOG-01 $\to$ FOG-04)**:
  - `FOG-01`: Cần bao nhiêu mẫu để hiệu chuẩn Platt/Temperature Scaling cho Citation Verifier?
  - `FOG-02`: Fast Intent Router nên dùng Regex/Trie + PhoBERT hay Qwen 35B `enable_thinking: False`?
  - `FOG-03`: Taxonomy lỗi BIM QC và cơ chế biểu diễn state cho System One Scorer.
  - `FOG-04`: Giao thức tích hợp hàng đợi HITL trên Redis DB 4 cho Maskara khi confidence $\in [0.60, 0.95]$.

---

## Nhiệm Vụ Của Bạn (Your Review Mandate)

Hãy thực hiện phản biện nghiêm ngặt trên 4 tiêu chí cốt lõi:

1. **Phản Biện Phase 1 & Benchmark TICK-01**:
   - Việc đặt trần an toàn $N=60$ candidates cho BGE Cross-Encoder có hợp lý không? Liệu 60 chunks có đủ để bao quát recall sau khâu BM25 + Vector RRF fusion không?
   - Ngân sách độ trễ $\sim 1.29\text{s}$ (hoặc $\sim 0.5\text{s}$ cho chunk ngắn) có chấp nhận được cho hot-path RAG trong một hệ thống hỏi đáp kỹ thuật/pháp lý không?
   - Refactor TICK-02 có bất kỳ "cái bẫy tiềm ẩn" (hidden pitfalls) nào chưa được tính tới trong `search_pipeline.py` không (ví dụ: trường hợp `docs` rỗng, deduplication, hoặc thứ tự mapping lại `hit_map`)?

2. **Mổ Xẻ Sâu Phase 2 (Citation Noul Gate)**:
   - Liệu một mô hình Cross-Encoder đa ngữ (`bge-reranker-v2-m3`) vốn được train để xếp hạng độ liên quan câu hỏi - đoạn văn có hoạt động hiệu quả cho bài toán **Entailment / Claim Verification (NLI)** không?
   - Văn bản pháp luật Việt Nam thường có các viện dẫn gián tiếp (Ví dụ: *"thực hiện theo quy định tại Điều 12..."* mà không nhắc lại nguyên văn). Cross-Encoder có nguy cơ tạo ra nhiều **False Negatives** (bắt oan trích dẫn hợp lệ) không? Cần cơ chế phòng thủ gì?

3. **Đánh Giá Vùng Sương Mù (FOG-01 $\to$ FOG-04) & Phase 3 (BIM QC / Maskara)**:
   - Ý tưởng mở rộng Typed Decisions sang BIM QC và Maskara có đang bị "nhiễm bệnh over-engineering" hay là hướng đi đúng?
   - Thứ tự ưu tiên giải quyết giữa FOG-01 và FOG-02 nên như thế nào?

4. **Phán Quyết & Bảng Điểm Đánh Giá**:
   - Cung cấp Scorecard theo 4 tiêu chí (thang điểm 1-10):
     - **Architectural Soundness** (Tính đúng đắn kiến trúc)
     - **Hardware & Performance Realism** (Tính thực tế phần cứng & hiệu năng)
     - **KISS & Simplicity** (Mức độ tinh gọn, tuân thủ KISS)
     - **Legal Domain Robustness** (Độ bền vững trong miền pháp lý Việt Nam)
   - Phán quyết cuối cùng: **FINAL ACCEPT / CONDITIONAL ACCEPT / REJECT**.

Hãy viết báo cáo phân tích đối kháng chi tiết, thẳng thắn và sắc sảo vào `.md/peer_exchange/grok_review_wayfinder_map.md`.
