---
name: md-quality-auditor
description: Đánh giá chất lượng Markdown sau extraction, so sánh với PDF source — phát hiện OCR errors, broken tables, structural issues.
---

# Markdown Quality Auditor

Skill này hướng dẫn agent đánh giá chất lượng file Markdown được tạo từ PDF extraction, đặc biệt cho tài liệu pháp luật Việt Nam.

## Khi Nào Dùng

- Sau khi chạy PDF → Markdown extraction
- Khi user yêu cầu kiểm tra chất lượng export
- Trước khi ingest vào Milvus / RAG database
- Khi audit score thấp ở dimension A (Markdown)

## Checklist Đánh Giá (6 tiêu chí)

### 1. OCR Spacing — Lỗi dính/thiếu dấu cách

```bash
# Phát hiện từ dính bất thường (>15 chars liên tục không dấu cách)
grep -Pn '\b\w{16,}\b' /path/to/file.md | head -20
```

**Dấu hiệu**: `quyđịnh`, `tiêuchuẩn`, `theoquy` → thiếu space
**Ngưỡng**: > 5% tổng dòng có lỗi → FAIL

### 2. Broken Tables — Bảng markdown không hợp lệ

```
# Bảng HỢP LỆ phải có:
| Header 1 | Header 2 |
|----------|----------|
| Data 1   | Data 2   |

# Bảng HỎNG: có pipe | nhưng thiếu separator |---|
| Header 1 | Header 2 |
| Data 1   | Data 2   |     ← Thiếu separator row
```

**Check**: Tìm pipe-delimited lines → verify có `|---|` row kế tiếp
**Ngưỡng**: > 30% bảng bị hỏng → FAIL

### 3. AI Monologue Leakage — Nội dung AI lẫn vào extraction

**Patterns cần tìm:**
- `Dưới đây là`, `Xin lỗi`, `Tôi xin`
- `Nội dung chính`, `Here is the`, `Certainly`, `I'll`

```bash
grep -cEi "Dưới đây là|Xin lỗi|Tôi xin|Here is the|Certainly|I'll " /path/to/*.md
```

**Ngưỡng**: > 10% files bị lẫn AI text → FAIL

### 4. Structural Integrity — Cấu trúc heading

**Kiểm tra:**
- Heading hierarchy: h1 → h2 → h3 (không nhảy cấp)
- Mỗi file có đúng 1 `# h1` (document title)
- `## Nội dung` hoặc `## Content` section tồn tại

```bash
# Đếm headings
grep -c "^#" /path/to/file.md
# Kiểm tra h1 duy nhất
grep -c "^# " /path/to/file.md  # Phải = 1
```

### 5. Footnote/Boilerplate Noise — Nhiễu chưa lọc

**Patterns cần lọc:**
- `CỘNG HÒA XÃ HỘI` (header quốc hiệu)
- `Nơi nhận:`, `Lưu: VT` (distribution list)
- `KT.`, `TM.` (signature prefixes)

**Ngưỡng**: > 5% nội dung là boilerplate → FAIL

### 6. Text Accuracy — So sánh với PDF gốc

Chọn ngẫu nhiên 3 đoạn từ PDF → tìm trong MD:
- Tên Điều, số khoản có khớp?
- Số liệu trong bảng có đúng?
- Dấu tiếng Việt có đầy đủ? (ă, ơ, ư, đ)

## Scoring Formula

Tương thích với `comprehensive_audit.py` Dim A:

```
Score A = 100
If broken_table > 30%: Score -= 15
If ai_leakage > 10%:   Score -= 20
If boilerplate > 5%:   Score -= 10
If ocr_spacing > 5%:   Score -=  5
```

**Target: Score A ≥ 90**

## Quick Audit Command

```bash
# Audit toàn bộ thư mục exports
EXPORT_DIR="/home/vvc/Codebase/RAG_QCTCVN/exports"

echo "📊 MD Quality Audit"
echo "Files: $(ls $EXPORT_DIR/*.markdown 2>/dev/null | wc -l)"
echo "AI Leakage: $(grep -rl 'Dưới đây là\|Xin lỗi\|Tôi xin' $EXPORT_DIR/*.markdown 2>/dev/null | wc -l) files"
echo "Broken tables: $(grep -rL '\-\-\-|' $EXPORT_DIR/*.markdown 2>/dev/null | xargs grep -l '|.*|' 2>/dev/null | wc -l) files"
echo "Boilerplate: $(grep -rl 'CỘNG HÒA XÃ HỘI\|Nơi nhận:\|Lưu: VT' $EXPORT_DIR/*.markdown 2>/dev/null | wc -l) files"
```

## Integration

Skill này bổ sung cho:
- **`rag-audit-runner`** — chạy full audit P1-P6, skill này focus riêng Dim A (Markdown)
- **`autoresearch-runner`** — khi `table_detection` hoặc `noise_ratio` thấp, dùng skill này để debug
- **`legal-doc-processor`** — sau khi extract, dùng skill này để verify chất lượng
