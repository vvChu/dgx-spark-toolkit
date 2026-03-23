---
name: autoresearch-runner
description: Vòng lặp tối ưu RAG tự động (Karpathy-style) cho văn bản pháp luật Việt Nam. Agent tự chạy thí nghiệm, đo lường, cải tiến optimize_rag.py.
---

# Autoresearch Runner — RAG Optimization Loop

Skill này hướng dẫn agent chạy vòng lặp autoresearch để tối ưu pipeline RAG cho văn bản pháp luật Việt Nam, theo phương pháp Karpathy.

## Workspace

| Path | Mô tả |
|---|---|
| `/home/vvc/Codebase/RAG_QCTCVN/` | Working directory |
| `program.md` | 📋 Master instructions — **đọc đầu tiên** |
| `optimize_rag.py` | ✏️ **SỬA FILE NÀY** — toàn bộ pipeline |
| `prepare.py` | 🔒 Evaluation harness — **KHÔNG SỬA** |
| `extract_pdf.py` | 📖 PDF→MD extraction module |
| `llm_client.py` | 📖 LLM wrapper (opt-in qua `USE_LLM=1`) |
| `results.tsv` | 📊 Lịch sử thí nghiệm — tự động ghi |
| `exports/` | 📦 Output `.markdown` + `.json` |
| `sample_data/` | 📂 Test data (legal documents) |

## Quick Start

```bash
# 1. Đọc program.md TRƯỚC
cat /home/vvc/Codebase/RAG_QCTCVN/program.md

# 2. Xem trạng thái hiện tại
tail -5 /home/vvc/Codebase/RAG_QCTCVN/results.tsv | column -t -s $'\t'

# 3. Chạy 1 experiment
cd /home/vvc/Codebase/RAG_QCTCVN && uv run optimize_rag.py > run.log 2>&1

# 4. Đọc kết quả
grep "^overall_score:" /home/vvc/Codebase/RAG_QCTCVN/run.log
```

## Experiment Loop (Core Algorithm)

```
LOOP FOREVER:
  1. tail -5 results.tsv → xem score gần nhất
  2. Phân tích metric thấp nhất → chọn chiến lược
  3. Sửa optimize_rag.py — MỘT thay đổi mỗi lần
  4. uv run optimize_rag.py > run.log 2>&1
  5. Đọc kết quả → KEEP nếu cải thiện, REVERT nếu không
  6. Quay lại bước 1
```

## 8 Metrics (Trọng số = 100%)

| # | Metric | Weight | Target |
|---|---|---|---|
| 1 | `chunking_quality` | 20% | ≥ 95 |
| 2 | `child_parent_ratio` | 15% | 100 (1.5–3.0 ratio) |
| 3 | `metadata_accuracy` | 15% | 100 |
| 4 | `noise_ratio` | 10% | 100 |
| 5 | `table_detection` | 10% | ≥ 95 |
| 6 | `hierarchy_coverage` | 10% | ≥ 90 |
| 7 | `avg_chunk_length` | 10% | 100 (200–800 chars) |
| 8 | `export_integrity` | 10% | 100 |

## Nguyên tắc Vàng

1. **Một thay đổi mỗi lần** — Mỗi experiment = 1 biến số
2. **Đọc lỗi trước khi sửa** — Luôn check `run.log`
3. **KHÔNG sửa prepare.py** — Score thấp → sửa pipeline
4. **KHÔNG BAO GIỜ DỪNG** — Agent chạy autonomous, không hỏi user
5. **Export bắt buộc** — Mỗi doc phải có `.markdown` + `.json`

## Convergence Criteria

- **Primary**: `overall_score ≥ 95.0`
- **Convergence**: Đạt ≥ 95 trên 3 lần liên tiếp
- **Floor**: Tất cả 8 metric ≥ 80
- **Timeout**: Sau 50 experiments mà < 95 → thông báo user

## Tối Ưu Theo Metric

| Metric thấp | Chiến lược |
|---|---|
| `chunking_quality` | Cải thiện regex Điều/Khoản/Mục/Chương, La Mã |
| `child_parent_ratio` | Điều chỉnh `MIN_CHILD_LENGTH`, sentence splitting |
| `noise_ratio` | Mở rộng noise patterns (KT., TM., CỘNG HÒA...) |
| `table_detection` | Fix `_detect_inline_table()`, sync `is_table` flag |
| `hierarchy_coverage` | Đảm bảo `hierarchy_path` > 10 chars cho mọi chunk |
| `avg_chunk_length` | Điều chỉnh `MAX_PARENT_DISPLAY`, `MIN_BLOCK_SIZE` |
| `export_integrity` | Verify `export_document()` gọi cho mọi doc |
| `metadata_accuracy` | Đảm bảo `doc_id`, `source`, `page`, `chunk_type` |

## LLM Integration (Optional)

Khi `USE_LLM=1` trong `.env`:
- `repair_table(text)` — sửa bảng markdown bị hỏng
- `resolve_structure(text)` — phân tích cấu trúc mơ hồ
- `summarize_chunk(text)` — tóm tắt cho hierarchy_path
- Max 3 LLM calls/document
