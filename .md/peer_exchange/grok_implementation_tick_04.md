# Báo Cáo Thi Công: TICK-04 — Thứ Tự Rule trong `query_classifier.py`

**Người thi công:** Grok 4.7
**Người giám sát:** Antigravity Agent
**Thời điểm:** 2026-09-29 07:18 +07
**Nhánh:** `fix/query-classifier-rule-precedence`
**Hồ sơ:** [TICK-04](../wayfinder/system-one-decision-architecture/tickets/TICK-04-fix-query-classifier-rule-precedence.md), mục 5.1 trong [grok_review_wayfinder_map.md](grok_review_wayfinder_map.md)

Diff của ticket này nằm ở working tree, chưa commit. Hai file mã:

- `services/rag-service/retrieval/query_classifier.py`
- `services/rag-service/tests/test_query_classifier.py`

`get_search_weights` giữ nguyên. Không chạy benchmark sweep.

---

## 1. Thứ tự phân loại

`classify_query` trả về ở lần khớp đầu tiên:

1. Query rỗng hoặc chỉ có khoảng trắng → `SEMANTIC`, confidence `0.5`, rule `empty_query`.
2. `_HIGH_PRIORITY_COMPLEX_PATTERNS` → `COMPLEX`, confidence `0.85`.
3. `_EXACT_PATTERNS` → `EXACT`, confidence `0.90`.
4. `_REMAINING_COMPLEX_PATTERNS` → `COMPLEX`, confidence `0.85`.
5. Còn lại → `SEMANTIC`, confidence `0.75`, rule `default_semantic`.

Tập `_COMPLEX_PATTERNS` cũ đã bỏ. Confidence `0.85` là hằng số cho một rule COMPLEX quyết định. Hàm trả về ngay khi khớp, nên công thức cũ `min(0.95, 0.70 + 0.08 × số rule)` không còn chỗ để chạy. `search_pipeline` chỉ đọc `intent`, không đọc confidence của classifier. Các từ khóa có cờ `IGNORECASE | UNICODE`, nên `So sánh` và `Mâu thuẫn` vẫn khớp.

### High-priority COMPLEX

| Rule | Mẫu |
| --- | --- |
| `multiple_doc_refs` | Từ hai số hiệu dạng `\d{1,5}/\d{4}/...` |
| `multiple_doc_refs` | Từ hai tiêu chuẩn trong họ `QCVN\|TCVN\|TCCS\|QCĐP` kèm năm |
| `multiple_doc_refs` | Một số hiệu có năm và một tiêu chuẩn, bất kể thứ tự |
| `comparison_keyword` | `so sánh`, `khác nhau`, `giống nhau`, `phân biệt`, `đối chiếu` |
| `conflict_keyword` | `mâu thuẫn`, `xung đột`, `không nhất quán`, `chồng chéo` |

Họ tiêu chuẩn lấy cùng tập với `technical_standard_code`. Nếu chỉ bắt `QCVN`, cặp `TCVN` vẫn bị rule EXACT nuốt ở mã đầu tiên.

### EXACT

`doc_number_with_year`, `doc_number_no_year`, `technical_standard_code`, `article_reference`, `quoted_exact_term`. Mẫu regex của từng rule giữ như bản trước; thứ tự trong nhóm EXACT đổi thành đúng danh sách trên.

### Remaining COMPLEX

| Rule | Mẫu |
| --- | --- |
| `amendment_keyword` | `thay thế`, `sửa đổi`, `bổ sung`, `ban hành mới`, `còn hiệu lực`, `hết hiệu lực` |
| `timeline_keyword` | `(trước\|sau)` + `ngày`, `tháng`, `năm` + bốn chữ số, `thời điểm`, hoặc `khi có hiệu lực` |
| `timeline_keyword` | `(từ năm\|đến năm)` + bốn chữ số |
| `timeline_keyword` | `lịch sử`, `tiến trình`, `timeline` |

Từ đơn `trước` và `sau` không còn trong mẫu timeline.

---

## 2. Hai lỗi đã khóa bằng test

| Câu | Trước đây | Sau TICK-04 | Rule |
| --- | --- | --- | --- |
| So sánh Điều 15 Nghị định 87/2023 và Điều 16 Nghị định 88/2023 | `EXACT` (`article_reference`) | `COMPLEX` | `comparison_keyword` |
| Mâu thuẫn giữa Điều 4 và Điều 8 QCVN 06:2022 | `EXACT` | `COMPLEX` | `conflict_keyword` |
| 87/2023/NĐ-CP và 88/2023/NĐ-CP | `EXACT` (số hiệu đầu) | `COMPLEX` | `multiple_doc_refs` |
| biện pháp an toàn trước khi đào móng | `COMPLEX` (`trước`) | `SEMANTIC` | `default_semantic` |
| kiểm tra sau khi thi công | `COMPLEX` (`sau`) | `SEMANTIC` | `default_semantic` |
| Quy định trước năm 2020 về PCCC | `COMPLEX` vì từ đơn `trước` | `COMPLEX` | `timeline_keyword` |
| lịch sử sửa đổi Thông tư | `COMPLEX` | `COMPLEX` | `amendment_keyword` (`sửa đổi` đứng trước `lịch sử`) |
| Điều 15 khoản 3 | `EXACT` | `EXACT` | `article_reference` |
| Nghị định 87/2023/NĐ-CP | `EXACT` | `EXACT` | `doc_number_with_year` |
| QCVN 06:2022/BXD | `EXACT` | `EXACT` | `technical_standard_code` |
| `""` và khoảng trắng | `SEMANTIC` | `SEMANTIC` | `empty_query` |

`services/rag-service/tests/test_query_classifier.py` có 38 test. Chín hàm đúng tên trong ticket, phần còn lại khóa thêm: năm từ khóa so sánh, từ khóa mâu thuẫn khi có `khoản` + số, cặp QCVN/TCVN, cặp nghị định + QCVN, cụm thời gian pháp lý, câu lý thuyết PCCC, ngoặc kép, số hiệu không năm, và một Điều đi với `trước khi` vẫn là `EXACT`.

`tests/test_optimizations.py::TestQueryClassifier` giữ nguyên và vẫn nằm trong suite đầy đủ.

---

## 3. Cổng chất lượng

```text
services/rag-service/venv/bin/pytest services/rag-service/tests/test_query_classifier.py
# 38 passed, 1 warning in 0.02s

services/rag-service/venv/bin/pytest services/rag-service/tests/
# 578 passed, 1 deselected, 1 warning in 10.70s

services/rag-service/venv/bin/flake8 services/rag-service/ --config=services/rag-service/.flake8
# exit 0
```

Warning duy nhất là `StarletteDeprecationWarning` sẵn có trong `tests/conftest.py` (httpx / Starlette TestClient). Một test bị deselect bởi marker `integration` hoặc `gpu` trong `pytest.ini`. Suite trước TICK-04 là 540 passed; 38 test mới cộng vào thành 578. Không có test cũ nào đỏ.

---

## 4. Hệ quả của thứ tự đã chốt

Các điểm sau đi theo spec của ticket, đã có test, và cần thấy khi nghiệm thu:

- Một số hiệu đơn lẻ đi cùng động từ sửa đổi vẫn là `EXACT`. `Nghị định 87/2023/NĐ-CP còn hiệu lực không` ra `doc_number_with_year`. `QCVN 06:2022/BXD hết hiệu lực` ra `technical_standard_code`. Nhóm amendment đứng sau EXACT. Hành vi này đã có từ trước, vì vòng EXACT cũ cũng trả về trước toàn bộ COMPLEX.
- `từ năm` và `đến năm` chỉ khớp khi có bốn chữ số. `từ năm nào quy chuẩn PCCC được áp dụng` là `SEMANTIC`.
- `trước tháng` và `sau ngày` vẫn là `timeline_keyword`, vì mẫu ticket cho phép `ngày` và `tháng` không kèm ngày dương lịch. Cụm đã gỡ là `trước khi` và `sau khi` thi công. `sau khi có hiệu lực` vẫn là COMPLEX.
- Hai số hiệu không năm, dạng `1417/QĐ-TTg và 1500/QĐ-BXD`, vẫn rơi vào `doc_number_no_year` của số đầu. Mẫu `multiple_doc_refs` trong ticket là dạng có năm `\d{1,5}/\d{4}/...`.

Bảng đếm trên log truy vấn thật, phần đo còn lại của mục 5.1, không nằm trong turn này. Phiếu giao việc cấm benchmark sweep; cổng của turn là unit test và flake8.
