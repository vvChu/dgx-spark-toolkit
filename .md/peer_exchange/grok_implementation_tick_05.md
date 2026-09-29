# Báo Cáo Thi Công: TICK-05 — Citation Verifier 3 Tầng

**Người thi công:** Grok 4.7
**Người giám sát:** Antigravity Agent
**Thời điểm:** 2026-09-29 07:40 +07
**Nhánh:** `feat/three-tier-citation-verifier`
**Hồ sơ:** [TICK-05](../wayfinder/system-one-decision-architecture/tickets/TICK-05-implement-three-tier-citation-verifier.md), [ADR-0006](../../docs/adr/0006-three-tier-citation-noul-verifier.md)

Diff của ticket này nằm ở working tree, chưa commit. Hai file mã:

- `services/rag-service/retrieval/citation_verifier.py`
- `services/rag-service/tests/test_citation_verifier.py`

Module là một seam thư viện. `generator.py` và `search_pipeline.py` chưa gọi `CitationVerifier`. Checkpoint `mDeBERTa` không được tải trong turn này. Không chạy benchmark sweep và không hiệu chuẩn FOG-01.

---

## 1. Hợp đồng API

Phiếu giao việc chi tiết chữ ký hàm và model kết quả. Bản phác trong ticket (tuple `check_tier0_identifier` / `nli_model`) được hiện thực hóa thành các tên đó.

`CitationStatus(str, Enum)`:

| Thành viên | Giá trị |
| --- | --- |
| `VERIFIED_POINTER` | `verified_pointer` |
| `VERIFIED_ENTAILMENT` | `verified_entailment` |
| `UNVERIFIED` | `unverified` |
| `REJECTED_MISMATCH` | `rejected_mismatch` |
| `REJECTED_CONTRADICTION` | `rejected_contradiction` |

`CitationVerificationResult` là Pydantic v2, `frozen=True`, đúng quy ước data model của RAG service. Trường: `status`, `confidence`, `tier` (0, 1 hoặc 2), `reason`, `claim`, `extracted_proposition`.

```python
CitationVerifier(nli_scorer=None, tau_entail=0.75, tau_contra=0.80)
check_tier0(claim, chunk) -> CitationVerificationResult | None
extract_tier1_proposition(claim) -> str
check_tier2_nli(proposition, chunk_text) -> CitationVerificationResult
verify_citation(claim, chunk) -> CitationVerificationResult
verify_citations_batch(citations) -> list[CitationVerificationResult]
```

`verify_citation` chạy Tầng 0. `None` nghĩa là câu có mệnh đề kỹ thuật và không có xung đột số hiệu, nên Tầng 1 tách mệnh đề rồi Tầng 2 chấm. Batch giữ nguyên thứ tự từng cặp `(claim, chunk)`.

Scorer nhận `(premise, hypothesis)` và trả `(p_entail, p_neutral, p_contra)`. `premise` là `chunk["text"]` (fallback `content`, rồi `chunk_text`). `hypothesis` là mệnh đề đã tách. Ngưỡng áp lên đúng ba số scorer trả về, không chuẩn hóa lại tổng. `P_contra >= 0.80` được xét trước `P_entail >= 0.75`, nên một bộ ba chạm cả hai ngưỡng ra `REJECTED_CONTRADICTION`.

Hằng `DEFAULT_NLI_CHECKPOINT` trỏ tới `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`. `nli_probs_from_logits` softmax logit 3 chiều về đúng thứ tự `(p_entail, p_neutral, p_contra)`. Thứ tự mặc định của checkpoint này là entailment, neutral, contradiction. Hàm nhận `label_order` khi `id2label` đảo chiều.

Reranker `bge-reranker-v2-m3` không nằm trên đường này.

---

## 2. Tầng 0 — định danh

Số hiệu được tách từ câu viện dẫn:

| Loại | Mẫu |
| --- | --- |
| Tiêu chuẩn | `QCVN` / `TCVN` / `TCCS` / `QCĐP` + số + `:` hoặc `/` + năm, hậu tố cơ quan tùy chọn (`/BXD`) |
| Văn bản đủ số | `01/2024/TT-BXD`, `15/2021/NĐ-CP` |
| Văn bản gọi tên | `Thông tư 01/2024`, `Nghị định 15/2021` |
| Điều | `Điều` / `Dieu` + số |
| Khoản | `khoản` / `khoan` + số |
| Điểm | `điểm` + một chữ |

So khớp số hiệu dùng `chunk["doc_number"]`. `hierarchy_path` chỉ được đọc làm số hiệu khi `doc_number` không parse được. Một tiêu đề đường dẫn có thể nhắc văn bản liên quan; gộp cả hai nguồn sẽ che mất xung đột thật.

Điều, khoản, điểm của chunk là lần xuất hiện **cuối** trong `hierarchy_path` (đúng đoạn lá mà exporter dùng làm heading, ví dụ `[Chương II] -> [Điều 12] -> [Khoản 3]`).

Xung đột rõ khi hai phía đều có cùng loại định danh mà không gặp nhau:

- Không có `DocRef` nào của câu khớp chunk. Khớp khi họ, số và năm trùng. Số `06` và `6` là một. Hậu tố cơ quan chỉ so khi **cả hai** phía có hậu tố: `QCVN 06:2022` khớp `QCVN 06:2022/BXD`; `QCVN 06:2022/BCA` lệch `QCVN 06:2022/BXD`. `Thông tư 01/2024` khớp `01/2024/TT-BXD`.
- Chunk có một Điều và Điều đó không nằm trong tập Điều của câu.
- Cùng quy tắc cho khoản và điểm.

Câu dẫn chiếu thuần là câu còn định danh pháp lý sau khi bóc mã số, và không còn token nội dung. Các từ cửa (`thực hiện`, `theo quy định tại`, `căn cứ`, `nghiệm thu`, tên loại văn bản, viết tắt cơ quan) bị loại. `thực hiện theo quy định tại Điều 12 QCVN 06:2022/BXD` hết token nội dung. `Theo Điều 5 Thông tư 01/2024, chiều cao công trình tối đa là 50m` còn `chiều`, `cao`, `công`, `trình`.

| Tình huống | Kết quả | Gọi NLI |
| --- | --- | --- |
| Pointer, mọi định danh câu nêu đều được chunk xác nhận | `VERIFIED_POINTER`, tier 0, confidence `1.0` | Không |
| Hai phía nêu cùng loại định danh và lệch nhau | `REJECTED_MISMATCH`, tier 0, confidence `1.0` | Không |
| Pointer nhưng chunk thiếu khoản/điều/số hiệu mà câu đã nêu | `UNVERIFIED`, tier 0, confidence `0.5` | Không |
| Câu có mệnh đề kỹ thuật, không xung đột | `check_tier0` trả `None`, xuống Tầng 2 | Có |

Pointer không bao giờ xuống Tầng 2. Mệnh đề rỗng sẽ khiến đầu NLI chấm nhãn trích dẫn thay vì nghĩa vụ kỹ thuật. Trường hợp metadata chưa đủ (`khoản 3` trong câu, `hierarchy_path` chỉ có `Điều 12`) giữ trích dẫn ở `UNVERIFIED` để kỹ sư xem, vẫn 0 lần gọi scorer.

Một câu nêu hai Điều vẫn khớp chunk nếu Điều của chunk nằm trong tập đó. Xung đột chỉ khi Điều của chunk không được câu viện dẫn.

---

## 3. Tầng 1 — tách mệnh đề

`extract_tier1_proposition` bỏ cụm mở đầu `Theo quy định tại` / `Căn cứ` / `thực hiện theo` / `áp dụng` / `tuân thủ` / `Theo`, và cụm trích dẫn cuối câu, rồi bỏ ngoặc đơn chỉ chứa số hiệu.

Dấu phẩy và chấm phẩy là ranh giới. Dấu hai chấm cũng là ranh giới, trừ dấu hai chấm trong số tiêu chuẩn `\d:\d{4}` (`QCVN 06:2022`). Pointer thuần trả về chuỗi rỗng.

| Câu | Mệnh đề |
| --- | --- |
| Theo Điều 5 Thông tư 01/2024, chiều cao công trình tối đa là 50m | chiều cao công trình tối đa là 50m |
| Căn cứ khoản 3 Điều 4, chiều cao công trình tối đa là 50m | chiều cao công trình tối đa là 50m |
| chiều cao công trình tối đa là 50m theo Điều 5 Thông tư 01/2024 | chiều cao công trình tối đa là 50m |
| thực hiện theo quy định tại Điều 12 QCVN 06:2022/BXD | `""` |

---

## 4. Tầng 2 — NLI và heuristic

Chính sách ba trạng thái, ngưỡng mặc định đúng ADR-0006:

| Điều kiện | Trạng thái | `confidence` |
| --- | --- | --- |
| `P_contra >= 0.80` | `REJECTED_CONTRADICTION` | `P_contra` |
| `P_entail >= 0.75` | `VERIFIED_ENTAILMENT` | `P_entail` |
| Còn lại | `UNVERIFIED` | `P_neutral` |

`0.75` và `0.80` đều inclusive. `(0.90, 0.0, 0.80)` ra mâu thuẫn. `(0.749, 0.251, 0.0)` ở lại `UNVERIFIED`. `reason` ghi `nli` khi có scorer và `heuristic` khi không.

`nli_scorer is None` dùng `heuristic_nli_scores`. Hàm này hermetic, không import torch. Ba lối tắt đã khóa bằng test:

- Cùng đơn vị, tập số rời nhau (`50 m` và `75m`) → `(0.04, 0.08, 0.88)`.
- Cấm / không được / nghiêm cấm đối `được phép` / `cho phép`, recall nội dung `>= 0.50` → cùng bộ ba mâu thuẫn. `không quá` và `không vượt quá` là hạn mức, không phải cấm.
- Recall nội dung `>= 0.80` với ít nhất 4 token, hoặc câu ngắn có độ dài sát premise → entailment khoảng `0.78–0.95`.

Số có đơn vị mà premise không hề nêu, hoặc overlap thấp, nằm dưới cả hai ngưỡng và ra `UNVERIFIED`. Heuristic phục vụ test và chạy CPU. Nó không phải mô hình đã hiệu chuẩn, và không thay temperature scaling của FOG-01.

---

## 5. Kiểm thử

`services/rag-service/tests/test_citation_verifier.py` có 26 test. Bảy test đúng tên trong phiếu giao việc:

| Test | Kỳ vọng đã khóa |
| --- | --- |
| `test_tier0_pure_pointer_matches_doc_and_article` | Câu nghiệm thu theo Điều 12 QCVN 06:2022/BXD, chunk Điều 12 cùng số hiệu → `VERIFIED_POINTER`, tier 0. Scorer ném lỗi nếu bị gọi. |
| `test_tier0_article_mismatch_rejected` | Điều 15 đối chunk Điều 4, cùng QCVN 06:2022 → `REJECTED_MISMATCH`, tier 0, không gọi NLI. |
| `test_tier1_proposition_extraction` | Tách đúng `chiều cao công trình tối đa là 50m`. |
| `test_tier2_entailment_verified` | Scorer `(0.91, 0.05, 0.04)`, premise là text chunk, hypothesis là mệnh đề đã tách → `VERIFIED_ENTAILMENT`, tier 2. |
| `test_tier2_contradiction_rejected` | `P_contra = 0.90` → `REJECTED_CONTRADICTION`, tier 2. |
| `test_tier2_uncertain_keeps_unverified` | Neutral `0.70` → `UNVERIFIED`, tier 2. |
| `test_batch_verification_mixed` | Pointer, mismatch, entailment, unverified đúng thứ tự. Scorer chỉ thấy hai mệnh đề Tầng 2. |

Phần còn lại khóa: mệnh đề kỹ thuật gắn nhầm Điều vẫn chết ở Tầng 0; lệch số QCVN; khớp và lệch khoản; hậu tố `/BXD` một phía vẫn khớp, hai hậu tố khác nhau thì lệch; `QCVN 6` khớp `QCVN 06`; pointer thiếu khoản không gọi NLI; mệnh đề có căn cứ vẫn rơi xuống Tầng 2; `Căn cứ khoản` và trích dẫn cuối câu; mâu thuẫn ưu tiên khi cả hai ngưỡng cùng chạm; biên `0.75` / `0.80`; heuristic 75 m, overlap 50 m, overlap thấp, cấm đối được phép; thứ tự logit; batch rỗng; scorer sai shape; `tau` ngoài `[0, 1]`.

---

## 6. Cổng chất lượng

```text
services/rag-service/venv/bin/pytest services/rag-service/tests/test_citation_verifier.py
# 26 passed, 1 warning in 0.03s

services/rag-service/venv/bin/pytest services/rag-service/tests/
# 604 passed, 1 deselected, 1 warning in 10.71s

services/rag-service/venv/bin/flake8 services/rag-service/ --config=services/rag-service/.flake8
# exit 0
```

Warning duy nhất là `StarletteDeprecationWarning` sẵn có trong `tests/conftest.py`. Một test bị deselect bởi marker `integration` hoặc `gpu` trong `pytest.ini`. File mới góp 26 test trong tổng 604. Không có test cũ nào đỏ.

---

## 7. Giới hạn để nghiệm thu thấy trước

- Ngưỡng `0.75` / `0.80` là mặc định ADR, chưa khóa lại trên tập FOG-01. Turn này không sinh 600 cặp và không chạy temperature scaling.
- Heuristic chỉ bắt đối cực định lượng cùng đơn vị và cặp cấm/cho phép. Một câu bịa không đụng số liệu nguồn rơi vào `UNVERIFIED`, đúng vùng giữ cho kỹ sư, cho đến khi checkpoint NLI được gắn vào `nli_scorer`.
- `Điều 15a` và số hiệu `Luật .../QH` chưa có parser. Spec Tầng 0 của phiếu là `Điều \d+`.
- `Chương` / `Mục` / `Phần` bị gỡ khỏi token pointer và không tham gia so lệch.
- Hai Điều trong một câu không làm chunk của một trong hai Điều thành mismatch.
- Gắn verifier vào câu trả lời LLM, và nạp mDeBERTa fp16, là bước nối sau seam này.
