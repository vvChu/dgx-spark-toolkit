# Ticket [TICK-05]: Triển Khai Module Citation Verifier 3 Tầng (Theo Chuẩn ADR-0006)

**Bản đồ cha:** [Bản đồ Định hướng Phân tách Quyết định System One & System Two](../map.md)  
**Phân loại:** `Task [AFK]`  
**Giai đoạn:** Phase 2 (Citation Verification & Grounding)  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Grok 4.7 (Supervisor: Antigravity)  
**Phụ thuộc:** [TICK-03](TICK-03-noul-citation-verifier-design.md) (Đã hoàn tất ADR-0006)  

---

## 1. Mục tiêu
Lập trình hoàn chỉnh mô-đun **Citation Verifier 3 Tầng** tại [services/rag-service/retrieval/citation_verifier.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/citation_verifier.py) theo đúng đặc tả kiến trúc của [ADR-0006](../../../../docs/adr/0006-three-tier-citation-noul-verifier.md) và phản biện đối kháng của Grok 4.7:
1. **Tầng 0 (Định Danh Regex)**: Đối chiếu số hiệu văn bản (`doc_number`) và điều/khoản (`hierarchy_path`). Câu dẫn chiếu thuần khớp số hiệu được giữ ngay (`VERIFIED_POINTER`, zero latency); câu xung đột số hiệu rõ ràng bị gỡ ngay (`REJECTED_MISMATCH`).
2. **Tầng 1 (Tách Mệnh Đề)**: Bóc tách phần con trỏ dẫn chiếu để trích xuất mệnh đề khẳng định nghĩa vụ kỹ thuật cốt lõi (Core Claim).
3. **Tầng 2 (Mô Hình NLI Entailment)**: Tính toán phân phối 3 nhãn $[P_{\text{entailment}}, P_{\text{neutral}}, P_{\text{contradiction}}]$ với chính sách Tri-state (Gỡ khi mâu thuẫn cao, xác thực khi entailment cao, và giữ kèm cờ `[unverified]` ở vùng biên không chắc chắn).
4. Viết trọn vẹn bộ kiểm thử tại `services/rag-service/tests/test_citation_verifier.py` và đảm bảo 100% tests pass.

---

## 2. Kế Hoạch Triển Khai Chi Tiết

### 2.1. File `services/rag-service/retrieval/citation_verifier.py`:
- Định nghĩa Enum `CitationStatus`:
  - `VERIFIED_POINTER`: Khớp con trỏ dẫn chiếu thuần ở Tầng 0.
  - `VERIFIED_ENTAILMENT`: Khớp suy diễn logic ở Tầng 2 ($P_{\text{entail}} \ge \tau_{\text{entail}}$).
  - `UNVERIFIED`: Vùng biên giữa, giữ trích dẫn để người dùng đối chiếu.
  - `REJECTED_MISMATCH`: Xung đột số hiệu điều khoản rõ ràng ở Tầng 0.
  - `REJECTED_CONTRADICTION`: Mâu thuẫn trực tiếp với nguồn ở Tầng 2 ($P_{\text{contra}} \ge \tau_{\text{contra}}$).
- Lớp `CitationVerifier`:
  - Khởi tạo với ngưỡng $\tau_{\text{entail}} = 0.75$, $\tau_{\text{contra}} = 0.80$, lazy-load / mockable NLI callable.
  - Tầng 0: `check_tier0_identifier` với regex bắt số hiệu văn bản pháp luật VN và Điều/Khoản.
  - Tầng 1: `extract_tier1_proposition` loại bỏ tiền tố dẫn chiếu văn phong pháp luật.
  - Tầng 2: `check_tier2_nli` chính sách Tri-state (entailment, contradiction, unverified).
  - Điều phối: `verify_citation` và `verify_citations_batch`.

### 2.2. File `services/rag-service/tests/test_citation_verifier.py`:
- 26 test cases kiểm tra độc lập từng tầng:
  - Tầng 0 Pointer matching & Mismatch rejection.
  - Tầng 1 Proposition extraction.
  - Tầng 2 NLI Entailment, Contradiction, Unverified fallback.
  - Batch verification và thống kê báo cáo.

---

## 3. Tiêu Chí Nghiệm Thu
- [x] Hoàn thành `CitationVerifier` tại `services/rag-service/retrieval/citation_verifier.py`.
- [x] 100% test cases trong `tests/test_citation_verifier.py` pass (26/26 passed in 0.02s).
- [x] Toàn bộ backend unit tests pass: `pytest services/rag-service/tests/` (604/604 passed in 10.71s).
- [x] Flake8 kiểm tra sạch lỗi.
