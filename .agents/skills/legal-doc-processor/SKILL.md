---
name: legal-doc-processor
description: Xử lý tài liệu pháp luật Việt Nam (QCVN/TCVN/Nghị định/Thông tư) — PDF extraction, doc boundary detection, OCR quality, chunking theo cấu trúc pháp lý.
---

# Legal Document Processor — Vietnamese Legal RAG Pipeline

Skill này cung cấp kiến thức và hướng dẫn xử lý tài liệu pháp luật Việt Nam trong RAG pipeline.

## Cấu Trúc Pháp Luật Việt Nam

```
Văn bản pháp luật
├── Phần (Part)
│   └── Chương (Chapter)
│       └── Mục (Section)
│           └── Điều (Article)
│               └── Khoản (Clause) — 1, 2, 3...
│                   └── Điểm (Point) — a, b, c...
```

## Loại Văn Bản

| Loại | Prefix | Đặc điểm |
|---|---|---|
| QCVN | `QCVN XX:YYYY/BỘ` | Quy chuẩn kỹ thuật quốc gia, thường đi kèm Thông tư ban hành |
| TCVN | `TCVN XXXX:YYYY` | Tiêu chuẩn quốc gia |
| Nghị định | `NĐ-CP` | Chính phủ ban hành |
| Thông tư | `TT-BỘ` | Bộ ban hành, có thể chứa QCVN/TCVN bên trong |
| Quyết định | `QĐ-xxx` | Cơ quan ban hành |

## Core Modules

### 1. Doc Boundary — `doc_boundary.py`

**Path:** `services/rag-service/ingestion/doc_boundary.py`

Tách phần nội dung kỹ thuật (QCVN/TCVN) khỏi văn bản ban hành (Thông tư/QĐ).

```python
from ingestion.doc_boundary import strip_issuing_document
# Tự động phát hiện và strip trang Thông tư, chỉ giữ nội dung tiêu chuẩn
doc.raw_pages = strip_issuing_document(doc.raw_pages, doc_type="QCVN")
```

**Detection patterns:**
- `_STANDARD_HEADER_PATTERNS` — nhận diện QCVN/TCVN/TCCS
- `_ISSUING_DOC_PATTERNS` — nhận diện trang Thông tư/QĐ (Điều 1. Ban hành...)
- `_CONTENT_START_PATTERNS` — tìm điểm bắt đầu nội dung (Lời nói đầu, Chương I...)
- `_is_toc_page()` — bỏ qua trang mục lục

### 2. Article Chunking — `chunking.py`

**Path:** `services/rag-service/ingestion/chunking.py`

**VietLawArticleChunker** (Tier 1): Split theo `Điều X` với Context Inheritance.

```python
# Regex nhận diện Điều
dieu_pattern = r'(?m)^\s*([ĐĐD]i[eề]u\s*\d+[\.:\s])'
# Context inheritance: Chương/Phần/Mục trước Điều
context_pattern = r'(?m)^\s*(?:Phần|Chương|Mục)\s+[IVX\d]+.*$'
```

**Parent-Child model:**
- **Parent**: Toàn bộ Điều (capped tại `MAX_PARENT_DISPLAY` chars)
- **Children**: Sentences/paragraphs bên trong Điều
- Target ratio: `child/parent = 1.5–3.0`

### 3. Table Extraction — `table_extraction.py`

**Path:** `services/rag-service/ingestion/table_extraction.py`

- Phát hiện bảng inline bằng pipe `|` delimiters
- Cross-validate với evaluator pattern: `|---|` hoặc `Stt...Đơn vị`
- Sync `is_table` flag giữa parent và child chunks

### 4. OCR Quality — `stages/s02_ocr.py`

**Path:** `services/rag-service/ingestion/stages/s02_ocr.py`

- OCR spacing detection: phát hiện lỗi dính chữ trong scanned PDF
- Concurrency: `MAX_OCR_CONCURRENCY` (env, default 1)
- Timeout: `VLLM_VISION_TIMEOUT` (recommended 300s)

### 5. Cross-Surface Audit

**Path:** `services/rag-service/scripts/comprehensive_audit.py`

5 dimensions:
- **A (Markdown)**: broken tables, AI leakage, boilerplate, OCR spacing
- **B (JSON)**: missing doc_number, meta fields
- **C (Chunking)**: article strategy rate, child/parent ratio, noise
- **D (Milvus)**: vector store integrity
- **E (Fidelity)**: coverage

## Common Patterns & Gotchas

1. **QCVN trong Thông tư**: Luôn chạy `strip_issuing_document()` trước chunking
2. **Scanned PDF**: OCR quality thấp → tăng `MAX_OCR_CONCURRENCY=4`, timeout=300s
3. **Bảng lớn trong Điều**: Cap parent text nhưng giữ full table trong child
4. **False positive `broken_table`**: Audit script có thể báo sai → check `|---|` separator
5. **La Mã numbering**: I, II, III... cần regex riêng bên cạnh Arabic
6. **Context Inheritance**: Chương/Mục phải propagate xuống Điều trong hierarchy_path

## Useful Commands

```bash
# Kiểm tra export quality
ls /home/vvc/Codebase/RAG_QCTCVN/exports/ | wc -l

# Chạy comprehensive audit
cd /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service && \
  python3 scripts/comprehensive_audit.py

# Kiểm tra doc_boundary detection
grep -r "doc_boundary" services/rag-service/ingestion/ --include="*.py"
```
