# ADR-0006: Kiến Trúc Chốt Chặn Xác Thực Trích Dẫn Pháp Lý 3 Tầng (Three-Tier Citation Noul Verifier)

- **Trạng thái:** Accepted / Supervised
- **Ngày:** 2026-09-29
- **Tác giả:** Antigravity Agent (Supervisor) & Grok 4.7 (Adversarial Auditor)
- **Hồ sơ tham chiếu:** [TICK-03](file:///home/vvc/Codebase/dgx-spark-toolkit/.md/wayfinder/system-one-decision-architecture/tickets/TICK-03-noul-citation-verifier-design.md), [grok_review_wayfinder_map.md](file:///home/vvc/Codebase/dgx-spark-toolkit/.md/peer_exchange/grok_review_wayfinder_map.md)
- **Bản đồ cha:** [MAP-SPARK-SYSTEM-ONE-20260929](file:///home/vvc/Codebase/dgx-spark-toolkit/.md/wayfinder/system-one-decision-architecture/map.md)

---

## 1. Bối Cảnh (Context)

Trong hệ thống RAG pháp luật xây dựng Việt Nam, câu trả lời do LLM sinh ra (`generator.py`) luôn đính kèm các trích dẫn nguồn luật (ví dụ: `[1]`, `[Điều 4 QCVN 06:2022/BXD]`). Hai rủi ro nghiêm trọng thường gặp:
1. **Ảo giác gán nhãn sai (False Positive - Giữ nhầm)**: LLM sinh ra nội dung nghĩa vụ kỹ thuật sai sự thật (hallucination) nhưng sao chép đúng tên văn bản và số hiệu điều khoản. Nếu dùng mô hình đo độ tương quan từ vựng hoặc relevance score, điểm số sẽ cao $\to$ để lọt trích dẫn sai luật.
2. **Ảo giác gỡ oan trích dẫn (False Negative - Gỡ nhầm)**: LLM viện dẫn gián tiếp dạng *"thực hiện nghiệm thu theo quy định tại Điều 12 QCVN 06:2022/BXD"* mà không lặp lại các chỉ tiêu định lượng trong nguồn. Mô hình relevance cho điểm thấp $\to$ gỡ oan trích dẫn hoàn toàn chuẩn mực của kỹ sư.

### Phản biện đối kháng từ Grok 4.7:
- Mô hình Cross-Encoder `BAAI/bge-reranker-v2-m3` được huấn luyện cho bài toán xếp hạng liên quan (Query-Passage Relevance), **không phải bài toán suy luận logic tự nhiên (NLI / Entailment)**.
- Điểm relevance qua Sigmoid chỉ phản ánh mức độ trùng khớp chủ đề, không thể tạo ra nhãn *mâu thuẫn (contradiction)* hay phân định được viện dẫn gián tiếp.

---

## 2. Quyết Định Kiến Trúc (Decision)

Thiết lập cơ chế **Xác thực Trích dẫn 3 Tầng (Three-Tier Citation Verifier)** theo đúng nguyên tắc *Code/Regex $\to$ System One Scorer $\to$ System Two Reasoning*:

```
[CÂU TRẢ LỜI CỦA LLM KÈM FOOTNOTES]
                │
                ▼
   [TẦNG 0: ĐỊNH DANH ĐỐI CHIẾU (Code / Regex)]
   ├── Tách: doc_number, article ("Điều \d+"), clause ("khoản \d+")
   ├── Đối chiếu với doc_number & hierarchy_path trong metadata của chunk
   ├── Trùng khớp con trỏ thuần ("thực hiện theo...") ──► GIỮ [VERIFIED_POINTER] (Zero ML latency)
   └── Xung đột số hiệu rõ ràng (Claim: Điều 15 vs Chunk: Điều 4) ──► GỠ [REJECTED_MISMATCH]
                │ (Nếu là câu khẳng định nghĩa vụ kỹ thuật phức tạp)
                ▼
   [TẦNG 1: TÁCH MỆNH ĐỀ KHẲNG ĐỊNH (Claim Extraction)]
   ├── Bóc tách phần con trỏ viện dẫn
   └── Trích xuất mệnh đề khẳng định cốt lõi (Core Assertion)
                │
                ▼
   [TẦNG 2: MÔ HÌNH NLI ĐA NGỮ (System One Noul Gate)]
   ├── Checkpoint: mDeBERTa-v3-base-xnli (~300M params, fp16 < 1GB VRAM)
   ├── Dự đoán phân phối 3 nhãn: [P_entailment, P_neutral, P_contradiction]
   └── Chính sách 3 trạng thái (Tri-state Policy):
       ├── P_contradiction >= τ_contradiction (calibrated >= 0.80) ──► GỠ & CẢNH BÁO [CONTRADICTION]
       ├── P_entailment >= τ_entailment (calibrated >= 0.75)       ──► XÁC THỰC [VERIFIED]
       └── Vùng giữa (Không chắc chắn / Neutral)                   ──► GIỮ KÈM DẤU [UNVERIFIED]
```

---

## 3. Quy Chuẩn Hiệu Chuẩn Dữ Liệu (FOG-01 Protocol)

Để khóa các ngưỡng $\tau_{\text{contradiction}}$ và $\tau_{\text{entailment}}$, hệ thống áp dụng quy chuẩn kiểm thử trên tập dữ liệu gán nhãn $\approx 600$ cặp mẫu pháp lý:
1. **200 cặp Entailment**: Câu khẳng định diễn giải đúng nội dung điều khoản.
2. **200 cặp Contradiction / Unsupported**: Câu khẳng định bịa sai số liệu (ví dụ: đổi 50m thành 75m, đổi cấm thành cho phép).
3. **200 cặp Hard Negatives**: Cùng một văn bản quy chuẩn, Điều kề bên, hoặc các bảng tra cứu có cấu trúc gần giống nhau.
4. **50 cặp Con trỏ Thuần**: Để kiểm chứng Tầng 0 hoạt động chính xác 100% mà không bị đẩy xuống Tầng 2.
5. **Hiệu chuẩn Xác suất**: Áp dụng Temperature Scaling trên tập giữ lại (Held-out set 50/50), không dùng lại tập đã chọn ngưỡng.

---

## 4. Ngân Sách Phần Cứng & Hiệu Năng Trên DGX Spark GB10

- **VRAM**: `mDeBERTa-v3-base` chiếm $< 1\text{GB}$ VRAM ở chế độ FP16, hoàn toàn nằm trong ngân sách bộ nhớ hợp nhất (không vi phạm lệnh cấm nạp model 8B/14B decoder).
- **Độ trễ (Latency)**:
  - Tầng 0 (Regex): Xử lý 60–70% trích dẫn gián tiếp trong $< 1\text{ms}$.
  - Tầng 2 (NLI Encoder): Chạy batch 5–10 trích dẫn còn lại trong $\approx 35 - 50\text{ms}$ trên GPU GB10.
- **Tính Tất Định**: Hoàn toàn cục bộ, 0 chi phí token API bên ngoài, độc lập hạ tầng 100%.

---

## 5. Kế Hoạch Triển Khai (Consequences & Action Plan)

1. **Ticket TICK-03**: Hoàn tất hồ sơ thiết kế kiến trúc và quy chuẩn kiểm định (Done).
2. **Ticket TICK-05**: Lập trình mô-đun `CitationVerifier` tại `services/rag-service/retrieval/citation_verifier.py` tích hợp Tầng 0 và Tầng 1, kèm stub NLI sẵn sàng nạp checkpoint.
