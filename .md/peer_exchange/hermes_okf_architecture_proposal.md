# ĐỀ XUẤT CẬP NHẬT KIẾN TRÚC RAG & KHO DỮ LIỆU TRI THỨC (CHUẨN OKF)
*Tác giả: Hermes (Domain Specialist / Legal Engineer)*  
*Thời điểm tiếp nhận: 2026-10-01 ICT*  

---

## 1. TÓM TẮT ĐIỀU CHỈNH
Hệ thống RAG hiện tại đạt ~70% độ hoàn thiện. Kiến trúc mới bổ sung 8 thành phần quan trọng:
- Phân loại lực ràng buộc pháp lý (Normative Force)
- Xác nhận phạm vi áp dụng (Scope Gate)
- Xử lý bảng số liệu bằng phương pháp thần kinh - ký hiệu (Neuro-Symbolic)

---

## 2. CÁC THÀNH PHẦN MỚI CẦN BỔ SUNG

### 2.1. Normative Force Disambiguation
- QCVN = bắt buộc áp dụng
- TCVN = khuyến nghị, chỉ bắt buộc khi được QCVN viện dẫn hoặc hợp đồng dự án yêu cầu
- Cần cơ chế xác định trạng thái pháp lý thực tế cho từng tiêu chuẩn

### 2.2. Scope Gate
- Trước khi tìm kiếm, xác nhận QCVN có áp dụng cho loại dự án này không
- VD: QCVN 06:2022 áp dụng cho nhà ở, công cộng — loại trừ nhà máy nổ, lọc dầu, hạt nhân

### 2.3. Multi-Milestone Temporal Anchoring
Dự án xây dựng có 4 mốc thời gian pháp lý:
1. Phê duyệt quy hoạch 1/500 → áp dụng QCVN 01 (quy hoạch)
2. Thẩm định thiết kế cơ sở → áp dụng QCVN 04 (chăm sóc sức khỏe)
3. Thẩm duyệt PCCC → áp dụng QCVN 06 (chống cháy)
4. Cấp giấy phép xây dựng → áp dụng quy định tại thời điểm nộp hồ sơ

### 2.4. Transitional Provisions Engine
- Khi QCVN mới thay thế QCVN cũ, Thông tư ban hành luôn chứa điều khoản chuyển tiếp
- VD: "Hồ sơ đã thẩm duyệt trước ngày X tiếp tục áp dụng quy chuẩn tại thời điểm thẩm duyệt"
- Cần parser chuyên biệt (không dùng LLM đoán)

### 2.5. Formal Project Profile Schema
```json
{
  "project_type": "Chung cư kết hợp thương mại dịch vụ",
  "building_height_m": 74.5,
  "number_of_stories": 24,
  "number_of_basements": 3,
  "fire_hazard_category": "F1.3",
  "structural_resistance_grade": "Bậc I",
  "sprinkler_coverage": true,
  "milestones": {
    "planning_approval": "2021-04-12",
    "fire_design_submission": "2022-11-01"
  }
}
```

### 2.6. Dynamic Consolidated Text
- Văn bản sửa đổi được ban hành riêng (delta document)
- Cần AST-level patch engine để tổng hợp văn bản hợp nhất có nguồn gốc rõ ràng

### 2.7. Neuro-Symbolic Bridge
- LLM không tốt so sánh bất đẳng thức đa biến (VD: H > 50m AND >100 người KHÔNG sprinkler → REI ≥ 120)
- Cần engine định lượng riêng: RAG lấy bảng, engine tính toán so sánh, LLM chỉ giải thích

### 2.8. Table Footnote Linking
- 50% vi phạm hoặc miễn trừ nằm ở "chú thích chân bảng"
- Khi trích bảng thành JSON/CSV, phải giữ liên kết footnote → cell predicate

---

## 3. CẬP NHẬT KIẾN TRÚC THEO OKF

### 3.1. Schema Tri Thức (Knowledge Entity)
```json
{
  "id": "unique_identifier",
  "type": "qcvn | tcvn | circular | decree | project_doc",
  "title": "Ten van ban",
  "code": "QCVN 06:2022/BXD",
  "normative_force": "mandatory | voluntary | mandatory_by_reference | contract_adopted",
  "status": "in_force | superseded | draft | amended",
  "effective_date": "YYYY-MM-DD",
  "validity_range": {"from": "...", "to": "..."},
  "scope": "pham vi dieu chinh (Dieu 1)",
  "regulated_entities": "doi tuong ap dung (Dieu 2)",
  "amendments": ["thong tu 09/2023 sua doi 1:2023"],
  "parent_code": "QCVN 06:2021/BXD",
  "children_codes": [],
  "cross_references": ["TCVN 3890:2023", "QCVN 01:2021/BXD"],
  "backlinks": ["project_id_123", "project_id_456"]
}
```

### 3.2. Schema Chunk (Legal Atom)
```json
{
  "chunk_id": "QCVN06_2022_Art4_Khoan2",
  "level": "article | paragraph | point | table | footnote",
  "parent_id": "QCVN06_2022_Art4",
  "text": "Noi dung Dieu 4 Khoan 2...",
  "table_data": null,
  "footnotes": ["chu thich 1: ..."],
  "effective_date": "2022-07-01",
  "amendment_tags": [],
  "cross_refs": ["TCVN 5738:2023"]
}
```

### 3.3. Pipeline Xử Lý
```
[1. INGEST] → Parse AST, extract structure, patch amendments
     ↓
[2. INDEX]  → Vector DB (semantic) + BM25 (lexical) + Graph DB (links)
     ↓ (1/2)
[3. ROUTE]  → Lookup | Applicability | Compliance | Change
     ↓
[4. GATE]   → Verify scope + milestone + transitional provisions
     ↓
[5. RETRIEVE] → Hybrid search, structure-aware chunking, expand context
     ↓
[6. VERIFY] → Neuro-symbolic comparison (tables), LLM explains only
     ↓
[7. GENERATE] → JSON schema locked: {claim, citation, result}
     ↓
[8. AUDIT]  → Human review + log corrections (no online learning)
```

---

## 4. THỨ TỰ TRIỂN KHAI (ĐÃ ĐIỀU CHỈNH)

| Bước | Nội dung | Ghi chú |
|------|----------|---------|
| 0 | Cắt gold benchmark (50-100 câu) | Trước khi làm gì khác |
| 1 | Ingest QCVN 06:2022 + Sửa đổi 1:2023 | Vertical slice, không phải toàn bộ |
| 2 | Xây dựng knowledge index schema OKF | Vector + BM25 + Graph |
| 3 | Implement retrieval + task routing | 4 pipelines riêng biệt |
| 4 | Thêm Scope Gate + Transitional Provisions | Không để bước sau |
| 5 | Neuro-Symbolic Compliance Checker | Engine định lượng riêng |
| 6 | Schema-driven generation + Human-in-the-loop | Citation-locked output |
| 7 | Freeze evaluation set | Measure metrics OKF |
| 8 | Scale corpus + Feedback loop | Patch corpus, không online learning |

---

## 5. METRICS ĐÁNH GIÁ (OKF STANDARD)

| Category | Metric | Mô tả |
|----------|--------|-------|
| Retrieval | Clause precision/recall | Có đúng điều khoản không? |
| Retrieval | Edition accuracy | Có đúng phiên bản hiệu lực không? |
| Retrieval | Numeric exact match | Số liệu có khớp chính xác? |
| Generation | Abstention accuracy | Có từ chối khi thiếu căn cứ đúng? |
| Generation | Footnote coverage | Có nắm bắt footnote miễn trừ? |
| End-to-end | Normative force correctness | Phân loại QCVN/TCVN đúng binding status? |
| End-to-end | Scope compliance | Có reject inapplicable results đúng? |

---

## 6. RỦI RO & GIẢM THIỂU

| Rủi ro | Mức độ | Giải pháp |
|--------|--------|-----------|
| Boil the ocean ở ingest | Cao | Chỉ ingest QCVN 06 đầu tiên |
| Human review fatigue | Cao | Validate gold set trước khi expose |
| Table parsing sai format | Trung bình | Validate thủ công 100 bảng đầu tiên |
| Transitional provision missed | Cao | Parser chuyên biệt, không dùng LLM |
| Cross-reference graph incomplete | Trung bình | Seed từ dữ liệu chính thức BXD |

---

## 7. YÊU CẦU LÃNH ĐẠO XEM XÉT
1. Chấp thuận kiến trúc mới không?
2. Cho phép ingest QCVN 06 làm vertical slice đầu tiên?
3. Phê duyệt gold benchmark scope (50-100 questions từ thực tế)?
