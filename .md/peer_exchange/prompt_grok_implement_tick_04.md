# Nhiệm Vụ Thi Công Kỹ Thuật: TICK-04 — Tinh Chỉnh Thứ Tự Rule Phân Loại Ý Định trong `query_classifier.py`

**Người giao việc & Giám sát:** Antigravity Agent (Supervisor)  
**Người nhận việc & Thi công:** Grok 4.7 (Assignee)  
**Nhánh Git:** `fix/query-classifier-rule-precedence` (đã checkout sẵn sàng)  
**Hồ sơ tham chiếu:**
- Ticket: `.md/wayfinder/system-one-decision-architecture/tickets/TICK-04-fix-query-classifier-rule-precedence.md`
- Phát hiện của chính bạn tại mục 5.1 trong `.md/peer_exchange/grok_review_wayfinder_map.md`

---

## 1. Yêu Cầu Cốt Lõi (Core Mandate)
Bạn hãy trực tiếp sửa code tại `services/rag-service/retrieval/query_classifier.py` và viết file test `services/rag-service/tests/test_query_classifier.py` để khắc phục triệt để 2 lỗi thứ tự rule (precedence bug):
1. **Lỗi nuốt câu so sánh**: Câu hỏi chứa từ khóa so sánh / mâu thuẫn nhưng có nhắc đến Điều/Khoản (ví dụ: *"So sánh Điều 15 Nghị định 87/2023 và Điều 16 Nghị định 88/2023"*) hiện đang bị gán nhầm thành `EXACT` do rule `article_reference` duyệt trước.
2. **Lỗi quét từ khóa thời gian quá rộng**: Mẫu `timeline_keyword` chứa từ đơn `trước|sau` khiến câu ngữ nghĩa thông thường (ví dụ: *"biện pháp an toàn trước khi đào móng"*) bị gán nhầm thành `COMPLEX`.

*(LƯU Ý CẢI TIẾN QUY TRÌNH: Tuyệt đối KHÔNG chạy benchmark sweep lớn trong turn coding này. Chỉ chạy unit tests và flake8 để hoàn tất việc sửa code và ghi báo cáo).*

---

## 2. Chi Tiết Thực Hiện

### 1. `services/rag-service/retrieval/query_classifier.py`:
- Phân chia các tập mẫu thành 3 nhóm:
  - `_HIGH_PRIORITY_COMPLEX_PATTERNS`:
    - `multiple_doc_refs`: Chứa $\ge 2$ số hiệu văn bản (ví dụ 2 mẫu `\d{1,5}/\d{4}/...` hoặc 2 tiêu chuẩn QCVN).
    - `comparison_keyword`: `\b(?:so sánh|khác nhau|giống nhau|phân biệt|đối chiếu)\b`
    - `conflict_keyword`: `\b(?:mâu thuẫn|xung đột|không nhất quán|chồng chéo)\b`
  - `_EXACT_PATTERNS`:
    - `doc_number_with_year`
    - `doc_number_no_year`
    - `technical_standard_code`
    - `article_reference`
    - `quoted_exact_term`
  - `_REMAINING_COMPLEX_PATTERNS`:
    - `amendment_keyword`: `\b(?:thay thế|sửa đổi|bổ sung|ban hành mới|còn hiệu lực|hết hiệu lực)\b`
    - `timeline_keyword` (đã tinh chỉnh): **Tuyệt đối không dùng từ đơn `trước|sau`**. Dùng cụm thời gian pháp lý:
      `r'\b(?:trước|sau)\s+(?:ngày|tháng|năm\s+\d{4}|thời điểm|khi có hiệu lực)\b'`, `\b(?:từ năm|đến năm)\s+\d{4}\b'`, `\b(?:lịch sử|tiến trình|timeline)\b`.
- Trong hàm `classify_query(query: str) -> ClassificationResult`:
  1. Kiểm tra query rỗng $\to$ `SEMANTIC` (confidence 0.5, rule `empty_query`).
  2. Duyệt `_HIGH_PRIORITY_COMPLEX_PATTERNS`: Nếu khớp bất kỳ rule nào $\to$ trả về `COMPLEX` ngay.
  3. Duyệt `_EXACT_PATTERNS`: Nếu khớp $\to$ trả về `EXACT` (confidence 0.90).
  4. Duyệt `_REMAINING_COMPLEX_PATTERNS`: Nếu khớp $\to$ trả về `COMPLEX`.
  5. Mặc định $\to$ trả về `SEMANTIC` (confidence 0.75, rule `default_semantic`).

### 2. `services/rag-service/tests/test_query_classifier.py`:
Viết file test chuyên sâu bao quát các ca:
- `test_comparison_with_articles_is_complex`: *"So sánh Điều 15 Nghị định 87/2023 và Điều 16 Nghị định 88/2023"* $\to$ `COMPLEX`.
- `test_conflict_with_articles_is_complex`: *"Mâu thuẫn giữa Điều 4 và Điều 8 QCVN 06:2022"* $\to$ `COMPLEX`.
- `test_multiple_doc_numbers_is_complex`: *"87/2023/NĐ-CP và 88/2023/NĐ-CP"* $\to$ `COMPLEX`.
- `test_before_after_preposition_is_semantic`: *"biện pháp an toàn trước khi đào móng"*, *"kiểm tra sau khi thi công"* $\to$ `SEMANTIC` (không bị dính COMPLEX).
- `test_timeline_legal_is_complex`: *"Quy định trước năm 2020 về PCCC"*, *"lịch sử sửa đổi Thông tư"* $\to$ `COMPLEX`.
- `test_single_article_is_exact`: *"Điều 15 khoản 3"* $\to$ `EXACT`.
- `test_single_doc_number_is_exact`: *"Nghị định 87/2023/NĐ-CP"* $\to$ `EXACT`.
- `test_technical_standard_is_exact`: *"QCVN 06:2022/BXD"* $\to$ `EXACT`.
- `test_empty_and_whitespace_is_semantic`: `""` và `"   "` $\to$ `SEMANTIC`.

---

## 3. Tiêu Chí Nghiệm Thu (Quality Gate)
1. Chạy pass toàn bộ test suite:
   ```bash
   services/rag-service/venv/bin/pytest services/rag-service/tests/test_query_classifier.py
   services/rag-service/venv/bin/pytest services/rag-service/tests/
   ```
2. Flake8 kiểm tra sạch lỗi:
   ```bash
   services/rag-service/venv/bin/flake8 services/rag-service/ --config=services/rag-service/.flake8
   ```
3. Ghi báo cáo nghiệm thu vào `.md/peer_exchange/grok_implementation_tick_04.md`.
