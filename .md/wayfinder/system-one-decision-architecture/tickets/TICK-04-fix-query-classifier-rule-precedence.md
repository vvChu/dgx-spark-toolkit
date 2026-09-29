# Ticket [TICK-04]: Tinh Chỉnh Thứ Tự Rule Phân Loại Ý Định trong query_classifier.py (FOG-02)

**Bản đồ cha:** [Bản đồ Định hướng Phân tách Quyết định System One & System Two](../map.md)  
**Phân loại:** `Task [AFK]`  
**Giai đoạn:** Phase 2 (Intent Routing & Precedence Fix)  
**Trạng thái:** `Completed (Done)`  
**Thẩm định & Nghiệm thu:** Antigravity Agent — Phán quyết: **FINAL ACCEPT** (Xem biên bản nghiệm thu tại [.md/peer_exchange/grok_implementation_tick_04.md](../../peer_exchange/grok_implementation_tick_04.md))  
**Assignee:** Grok 4.7 (Supervisor: Antigravity)  
**Ngày hoàn tất:** 29/09/2026  
**Phụ thuộc:** [TICK-02](TICK-02-refactor-search-pipeline-bge-reranker.md) (Đã hoàn tất)  

---

## 1. Mục tiêu
Thực hiện refactor mô-đun [services/rag-service/retrieval/query_classifier.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/query_classifier.py) để khắc phục 2 lỗi thứ tự rule (precedence bug) đã được Grok 4.7 bóc tách trong báo cáo phản biện đối kháng:
1. **Lỗi Nuốt Câu So Sánh / Mâu Thuẫn**: Mẫu `article_reference` (`Điều \d+`) trong `_EXACT_PATTERNS` hiện đang được duyệt trước toàn bộ `_COMPLEX_PATTERNS`. Do đó, câu hỏi so sánh hai điều luật (ví dụ: *"So sánh Điều 15 Nghị định 87/2023 và Điều 16 Nghị định 88/2023"*) bị trả về nhầm thành `EXACT` thay vì `COMPLEX`.
2. **Lỗi Quét Từ Khóa Thời Gian Quá Rộng**: Mẫu `timeline_keyword` chứa từ đơn `trước|sau` khiến các câu hỏi ngữ nghĩa thông thường (ví dụ: *"biện pháp an toàn trước khi đào móng"*) bị phân loại nhầm thành `COMPLEX`, kích hoạt sai luồng Agentic / HyDE làm tăng độ trễ không cần thiết.

---

## 2. Kế Hoạch Kỹ Thuật

### 2.1. Phân Tách & Sắp Xếp Thứ Tự Đánh Giá (Rule Precedence Pipeline):
1. **Bước 1 — Kiểm tra COMPLEX Ưu Tiên Cao (High-Priority Complex)**:
   - `multiple_doc_refs`: Câu hỏi chứa từ 2 số hiệu văn bản pháp luật trở lên $\to$ `COMPLEX`.
   - `comparison_keyword`: Chứa từ khóa so sánh (`so sánh`, `khác nhau`, `giống nhau`, `phân biệt`, `đối chiếu`) $\to$ `COMPLEX`.
   - `conflict_keyword`: Chứa từ khóa mâu thuẫn (`mâu thuẫn`, `xung đột`, `không nhất quán`, `chồng chéo`) $\to$ `COMPLEX`.
2. **Bước 2 — Kiểm tra EXACT (Exact Lookups)**:
   - Số hiệu văn bản đơn lẻ (`doc_number_with_year`, `doc_number_no_year`).
   - Tiêu chuẩn kỹ thuật (`technical_standard_code`: `QCVN ...`, `TCVN ...`).
   - Viện dẫn điều khoản đơn lẻ (`article_reference`: `Điều 15`, `khoản 3`).
   - Cụm từ đóng mở ngoặc kép (`quoted_exact_term`).
   $\to$ Trả về `EXACT`.
3. **Bước 3 — Kiểm tra COMPLEX Còn Lại (Timeline & Amendments)**:
   - `amendment_keyword`: `thay thế`, `sửa đổi`, `bổ sung`, `ban hành mới`, `hết hiệu lực`, `còn hiệu lực`.
   - `timeline_keyword` (đã tinh chỉnh): Chỉ bắt các cụm thời gian pháp lý rõ ràng:
     `r'\b(?:trước|sau)\s+(?:ngày|tháng|năm\s+\d{4}|thời điểm|khi có hiệu lực)\b'`, `\b(?:từ năm|đến năm)\s+\d{4}\b'`, `\b(?:lịch sử|tiến trình|timeline)\b`.
   $\to$ Trả về `COMPLEX`.
4. **Bước 4 — Mặc định (Default)**:
   $\to$ Trả về `SEMANTIC`.

### 2.2. Kiểm Thử Độc Lập Chuyên Sâu:
Tạo mới file test `services/rag-service/tests/test_query_classifier.py` bao quát 15+ test cases:
- So sánh 2 điều luật $\to$ `COMPLEX`.
- Mâu thuẫn giữa 2 thông tư $\to$ `COMPLEX`.
- Câu hỏi có "trước khi đào móng" $\to$ `SEMANTIC` (không bị gán nhầm thành COMPLEX).
- Tra cứu Điều 15 đơn lẻ $\to$ `EXACT`.
- Tra cứu số hiệu QCVN $\to$ `EXACT`.
- Câu hỏi lý thuyết PCCC $\to$ `SEMANTIC`.
- Truy vấn rỗng $\to$ `SEMANTIC`.

---

## 3. Tiêu Chí Nghiệm Thu
- [ ] Câu hỏi so sánh / mâu thuẫn chứa Điều/Khoản được phân loại chính xác thành `COMPLEX`.
- [ ] Câu hỏi chứa từ "trước", "sau" trong ngữ cảnh thi công xây dựng thông thường không bị gán thành `COMPLEX`.
- [ ] Tạo file test `tests/test_query_classifier.py` với đầy đủ các assertions cho các trường hợp trên.
- [ ] 100% backend unit tests pass: `pytest services/rag-service/tests/`.
- [ ] Flake8 kiểm tra sạch lỗi.
