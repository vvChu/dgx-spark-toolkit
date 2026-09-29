# Ticket [TICK-03]: Thiết Kế Citation Verifier 3 Tầng: Định Danh Kết Hợp NLI Entailment (Tiếp Thu Phản Biện Grok 4.7)

**Bản đồ cha:** [Bản đồ Định hướng Phân tách Quyết định System One & System Two](../map.md)  
**Phân loại:** `Research [AFK]`  
**Giai đoạn:** Phase 2 (Citation Verification & Grounding)  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Auditor & Reviewer:** Grok 4.7  
**Ngày hoàn tất:** 29/09/2026  
**Thành phẩm bàn giao:** [ADR-0006](../../../../docs/adr/0006-three-tier-citation-noul-verifier.md)  
**Phụ thuộc:** [TICK-02](TICK-02-refactor-search-pipeline-bge-reranker.md) (Đã hoàn tất)  

---

## 1. Mục tiêu
Thiết kế kiến trúc kỹ thuật cho module **Citation Verifier 3 Tầng** nhằm kiểm chứng tính chống đỡ thực tế giữa câu khẳng định do LLM sinh ra và đoạn văn bản quy chuẩn gốc (source chunk), giải quyết triệt để 2 lỗi chí mạng trong pháp lý (False Positive: giữ nhầm câu bịa nghĩa vụ nhưng chép đúng số điều; và False Negative: gỡ oan câu viện dẫn gián tiếp).

---

## 2. Bối Cảnh & Bài Học Phản Biện Đối Kháng Từ Grok 4.7
- **BÁC BỎ việc dùng `bge-reranker-v2-m3` làm bộ kiểm chứng trích dẫn**:
  - `bge-reranker-v2-m3` được huấn luyện để xếp hạng độ liên quan truy vấn–đoạn (Retrieval Relevance), đầu ra là 1 logit qua Sigmoid $\in (0, 1)$.
  - **Lỗi Giữ Nhầm (False Positive)**: Nếu LLM bịa sai nội dung nghĩa vụ nhưng chép đúng số hiệu "Điều 12" và danh từ kỹ thuật, điểm relevance vẫn rất cao $\to$ Reranker để lọt trích dẫn ảo nguy hiểm!
  - **Lỗi Gỡ Nhầm (False Negative)**: Với câu viện dẫn gián tiếp dạng *"thực hiện theo quy định tại Điều 12..."* (rất phổ biến trong luật xây dựng Việt Nam), câu không nhắc lại chỉ tiêu kỹ thuật $\to$ Điểm relevance tụt thấp $\to$ Reranker gỡ oan trích dẫn hợp lệ!
- **Xóa bỏ chỉ tiêu lý thuyết `< 30ms cho 5 trích dẫn`**: Tránh lặp lại sai lầm ước lượng duy ý chí đã bị bác bỏ ở TICK-01.

---

## 3. Kiến Trúc Citation Verifier 3 Tầng Đề Xuất

```
[CÂU TRẢ LỜI CỦA LLM KÈM FOOTNOTES]
                │
                ▼
   [TẦNG 0: ĐỊNH DANH (Code / Regex)]
   ├── Tách số hiệu: QCVN/TCVN, Nghị định, "Điều \d+", "Khoản \d+"
   ├── Đối chiếu trực tiếp với doc_number & hierarchy_path của chunk
   └── Nếu là câu dẫn chiếu thuần ("thực hiện theo Điều X...") và khớp định danh:
       └──► GIỮ TRÍCH DẪN NGAY LẬP TỨC (Không gọi bất kỳ mô hình nào)
                │ (Nếu là câu có nội dung khẳng định nghĩa vụ kỹ thuật)
                ▼
   [TẦNG 1: TÁCH MỆNH ĐỀ (Claim Extraction)]
   ├── Tách bỏ phần con trỏ dẫn chiếu
   └── Giữ lại mệnh đề khẳng định cốt lõi (Core Claim)
                │
                ▼
   [TẦNG 2: MÔ HÌNH NLI ENTAILMENT (3 Nhãn)]
   ├── Mô hình: mDeBERTa-v3-base-xnli (hoặc tương đương, ~300M params, fp16 < 1GB)
   ├── Dự đoán 3 xác suất: [P_entailment, P_neutral, P_contradiction]
   └── Cơ chế quyết định:
       ├── P_contradiction > τ_contradiction (đã hiệu chuẩn) ──► GỠ TRÍCH DẪN & CẢNH BÁO
       ├── P_entailment > τ_entailment                     ──► XÁC THỰC THÀNH CÔNG (Verified)
       └── Vùng giữa (Biên mơ hồ)                         ──► ĐÁNH DẤU [Unverified] (Vẫn giữ để kỹ sư kiểm tra)
```

---

## 4. Kế Hoạch Nghiên Cứu & Thiết Kế
1. **Thiết kế Tầng 0 (Định Danh)**: Tận dụng các regex chuẩn đã có trong `query_classifier.py` để trích xuất `(doc_number, article, clause)`.
2. **Lựa chọn Mô hình NLI Đa Ngữ**: Khảo sát các checkpoint NLI đa ngữ hỗ trợ tốt tiếng Việt (mDeBERTa XNLI), kiểm tra tương thích VRAM (< 1GB) trên DGX Spark Blackwell GB10.
3. **Quy Chuẩn Tập Dữ Liệu Hiệu Chuẩn (FOG-01)**:
   - Xây dựng tập chuẩn gồm $\approx 600$ cặp mẫu có chuyên môn gán nhãn:
     - 200 cặp Entailment.
     - 200 cặp Contradiction / Unsupported.
     - 200 cặp Hard Negatives (cùng văn bản, Điều kề bên, mâu thuẫn số liệu bảng tra).
     - Tập mẫu dẫn chiếu thuần để kiểm chứng Tầng 0.
   - Chia 50/50 thành tập khóa ngưỡng và tập giữ lại (Held-out Set) để hiệu chuẩn Temperature Scaling.
4. **Báo cáo Kết quả**: Xuất bản tài liệu ADR thiết kế tại `.md/knowledge/design_records/adr_citation_noul_verifier.md`.

---

## 5. Tiêu chí Nghiệm thu
- [ ] Đặc tả chi tiết kiến trúc 3 tầng: Định danh $\to$ Tách mệnh đề $\to$ NLI Entailment.
- [ ] Loại bỏ hoàn toàn sự phụ thuộc vào điểm relevance của `bge-reranker-v2-m3` cho bài toán trích dẫn.
- [ ] Phương án bảo vệ trích dẫn dẫn chiếu gián tiếp qua Tầng 0 không gọi mô hình.
- [ ] Tiêu chuẩn gán nhãn 600 cặp hard negatives cho FOG-01.
