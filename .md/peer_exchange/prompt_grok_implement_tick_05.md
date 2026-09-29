# Nhiệm Vụ Thi Công Kỹ Thuật: TICK-05 — Triển Khai Module Citation Verifier 3 Tầng

**Người giao việc & Giám sát:** Antigravity Agent (Supervisor)  
**Người nhận việc & Thi công:** Grok 4.7 (Assignee)  
**Nhánh Git:** `feat/three-tier-citation-verifier` (đã checkout sẵn sàng)  
**Hồ sơ tham chiếu:**
- Ticket: `.md/wayfinder/system-one-decision-architecture/tickets/TICK-05-implement-three-tier-citation-verifier.md`
- Đặc tả kiến trúc chính thức: `docs/adr/0006-three-tier-citation-noul-verifier.md`

---

## 1. Yêu Cầu Cốt Lõi (Core Mandate)
Bạn hãy trực tiếp lập trình mô-đun **`CitationVerifier`** tại:
`services/rag-service/retrieval/citation_verifier.py`
và viết bộ kiểm thử tại:
`services/rag-service/tests/test_citation_verifier.py`
theo đúng chuẩn kiến trúc 3 tầng trong **ADR-0006** đã được đồng thuận:
1. **Tầng 0 (Định Danh Regex)**:
   - Tách số hiệu văn bản (`doc_number`), Điều (`Điều \d+`), Khoản (`khoản \d+`).
   - Đối chiếu với `chunk.get("doc_number")` và `chunk.get("hierarchy_path")`.
   - Nếu là câu dẫn chiếu thuần (pointer clause) và khớp số hiệu $\to$ trả về `VERIFIED_POINTER` ngay (0 latency, không gọi NLI).
   - Nếu xung đột số hiệu rõ ràng (ví dụ câu viện dẫn "Điều 15" nhưng chunk là "Điều 4" cùng văn bản) $\to$ trả về `REJECTED_MISMATCH` ngay.
2. **Tầng 1 (Tách Mệnh Đề)**:
   - Bóc tách cụm từ dẫn chiếu ("Theo quy định tại Điều 12...", "Căn cứ khoản 3...") để trích xuất mệnh đề khẳng định nghĩa vụ kỹ thuật cốt lõi (Core Proposition).
3. **Tầng 2 (Mô Hình NLI Entailment)**:
   - Hỗ trợ giao diện nhận callable/model `nli_scorer(premise, hypothesis) -> tuple[float, float, float]` (trả về xác suất `[p_entail, p_neutral, p_contra]`).
   - Nếu chưa nạp checkpoint GPU nặng, cung cấp fallback heuristic thông minh (token overlap + negation detection) để phục vụ test hermetic.
   - Áp dụng chính sách Tri-state:
     - $P_{\text{contra}} \ge \tau_{\text{contra}}$ (0.80) $\to$ `REJECTED_CONTRADICTION`.
     - $P_{\text{entail}} \ge \tau_{\text{entail}}$ (0.75) $\to$ `VERIFIED_ENTAILMENT`.
     - Vùng giữa $\to$ `UNVERIFIED` (vẫn giữ trích dẫn để kỹ sư kiểm tra).

*(LƯU Ý CẢI TIẾN QUY TRÌNH: Tuyệt đối KHÔNG chạy benchmark sweep lớn trong turn coding này. Chỉ chạy unit tests và flake8 để hoàn tất việc sửa code và ghi báo cáo).*

---

## 2. Chi Tiết Thực Hiện

### 1. `services/rag-service/retrieval/citation_verifier.py`:
- Khai báo `CitationStatus(str, Enum)`:
  - `VERIFIED_POINTER = "verified_pointer"`
  - `VERIFIED_ENTAILMENT = "verified_entailment"`
  - `UNVERIFIED = "unverified"`
  - `REJECTED_MISMATCH = "rejected_mismatch"`
  - `REJECTED_CONTRADICTION = "rejected_contradiction"`
- Khai báo dataclass hoặc Pydantic model `CitationVerificationResult`:
  - `status: CitationStatus`
  - `confidence: float`
  - `tier: int` (0, 1, hoặc 2)
  - `reason: str`
  - `claim: str`
  - `extracted_proposition: str`
- Lớp `CitationVerifier`:
  - `__init__(self, nli_scorer=None, tau_entail: float = 0.75, tau_contra: float = 0.80)`
  - `check_tier0(self, claim: str, chunk: dict) -> Optional[CitationVerificationResult]`
  - `extract_tier1_proposition(self, claim: str) -> str`
  - `check_tier2_nli(self, proposition: str, chunk_text: str) -> CitationVerificationResult`
  - `verify_citation(self, claim: str, chunk: dict) -> CitationVerificationResult`
  - `verify_citations_batch(self, citations: list[tuple[str, dict]]) -> list[CitationVerificationResult]`

### 2. `services/rag-service/tests/test_citation_verifier.py`:
Viết các test cases bao quát:
1. `test_tier0_pure_pointer_matches_doc_and_article`: *"thực hiện theo quy định tại Điều 12 QCVN 06:2022/BXD"* đối chiếu với chunk Điều 12 QCVN 06:2022 $\to$ `VERIFIED_POINTER`, tier 0.
2. `test_tier0_article_mismatch_rejected`: *"Theo Điều 15 QCVN 06:2022"* đối chiếu với chunk Điều 4 QCVN 06:2022 $\to$ `REJECTED_MISMATCH`, tier 0.
3. `test_tier1_proposition_extraction`: Bóc tách cụm *"Theo Điều 5 Thông tư 01/2024, chiều cao công trình tối đa là 50m"* $\to$ trích xuất được *"chiều cao công trình tối đa là 50m"*.
4. `test_tier2_entailment_verified`: Với NLI scorer trả về entailment cao $\to$ `VERIFIED_ENTAILMENT`, tier 2.
5. `test_tier2_contradiction_rejected`: Với NLI scorer trả về contradiction cao $\to$ `REJECTED_CONTRADICTION`, tier 2.
6. `test_tier2_uncertain_keeps_unverified`: Với NLI scorer trả về neutral $\to$ `UNVERIFIED`, tier 2.
7. `test_batch_verification_mixed`: Kiểm tra danh sách hỗn hợp gồm cả pointer, mismatch, entailment, và unverified.

---

## 3. Tiêu Chí Nghiệm Thu (Quality Gate)
1. Chạy pass toàn bộ test suite:
   ```bash
   services/rag-service/venv/bin/pytest services/rag-service/tests/test_citation_verifier.py
   services/rag-service/venv/bin/pytest services/rag-service/tests/
   ```
2. Flake8 kiểm tra sạch lỗi:
   ```bash
   services/rag-service/venv/bin/flake8 services/rag-service/ --config=services/rag-service/.flake8
   ```
3. Ghi báo cáo nghiệm thu vào `.md/peer_exchange/grok_implementation_tick_05.md`.
