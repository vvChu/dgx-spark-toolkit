# LỘ TRÌNH TRIỂN KHAI & PHÂN NHÁNH ISSUES (ISSUES ROADMAP)

**Dự án**: `dgx-spark-toolkit`  
**Repository**: `vvChu/dgx-spark-toolkit`  
**Khởi tạo ngày**: 2026-09-24  

---

## 1. DANH SÁCH ISSUES ĐÃ KHỞI TẠO TRÊN GITHUB

| Issue # | Tiêu đề | Phân loại | Nhánh Git dự kiến | Trạng thái |
| :---: | :--- | :---: | :--- | :---: |
| **[#56](https://github.com/vvChu/dgx-spark-toolkit/issues/56)** | `chore(git): Atomic packaging and commit of recent architectural sync and GUIDES fixes` | `chore`, `docs` | `chore/package-architectural-sync` | Open |
| **[#57](https://github.com/vvChu/dgx-spark-toolkit/issues/57)** | `perf(frontend): Optimize bundle size with dynamic code-splitting for GraphPanel` | `perf`, `frontend` | `feat/frontend-bundle-codesplit` | Open |
| **[#58](https://github.com/vvChu/dgx-spark-toolkit/issues/58)** | `feat(ingestion): Backlog ingestion acceleration toward target 8,870 chunks` | `feat`, `ingestion` | `feat/ingestion-backlog-acceleration` | Open |
| **[#59](https://github.com/vvChu/dgx-spark-toolkit/issues/59)** | `feat(autoresearch): Autonomous RAG optimization loop for Vietnamese legal corpus` | `feat`, `research` | `feat/autoresearch-tuning-loop` | Open |

---

## 2. CHI TIẾT TỪNG NHÁNH TRIỂN KHAI

### Issue #56 — Đóng gói và Commit các Thay đổi Kiến trúc & Fix GUIDES
*   **Mục tiêu**: Làm sạch working tree hiện tại (13 modified files, 3 docs) thành các atomic commit logic tuân thủ Git Conventions.
*   **Trọng tâm**:
    1. `fix(neo4j)`: Khôi phục quan hệ GUIDES trong Cypher traversal và ghi nhận cạnh vào database.
    2. `test(ingestion)`: Bổ sung 6 unit test bao phủ GUIDES và LLM relationship schema normalization.
    3. `chore(tooling)`: Đồng bộ container name `qwen36b` trong các script vận hành.
    4. `docs(arch)`: Đồng bộ mô hình Penta-Partitioned Redis (DB 0 -> DB 4) và class `DocumentIngestionPipeline`.

### Issue #57 — Tối ưu Bundle Size Frontend (Code Splitting)
*   **Mục tiêu**: Giảm kích thước file `index-*.js` từ **738 kB** xuống **< 250 kB**.
*   **Trọng tâm**:
    - Dùng `React.lazy()` và `Suspense` cho component `GraphPanel` để tách thư viện đồ họa 2D Canvas khỏi initial load.
    - Kiểm chứng qua `npm run build` không còn warning vượt ngưỡng 500 kB của Vite.

### Issue #58 — Đẩy tiếp Tiến độ Ingestion Đạt 8,870 Chunks
*   **Mục tiêu**: Nâng tỷ lệ bao phủ của Milvus `legal_docs_v11` từ 4,051 entities (45.7%) lên mục tiêu baseline 8,870 entities.
*   **Trọng tâm**:
    - Kiểm tra bảng `ingestion_state` trên PostgreSQL để giải phóng các job bị kẹt (nếu có).
    - Quét kho tài liệu PDF nguồn `/app/data/legal_docs_source` và nạp thêm jobs vào Redis stream `ingest:queue`.
    - Giám sát tiến độ xử lý của worker `rag-watcher` và kiểm tra tính nhất quán trên Neo4j.

### Issue #59 — Vòng lặp Tối ưu hóa RAG Tự trị (Autoresearch)
*   **Mục tiêu**: Thực thi vòng lặp tối ưu hóa kiểu Andrej Karpathy cho văn bản pháp luật Việt Nam.
*   **Trọng tâm**:
    - Đánh giá chất lượng 5 chiều (Markdown, JSON, Chunking, Milvus, PDF-MD Fidelity) tại `services/rag-service/autoresearch/`.
    - Tự động chạy các vòng thí nghiệm cải tiến trên `optimize_rag.py` và lưu log vào `results.tsv`.
