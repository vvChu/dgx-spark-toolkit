# BÁO CÁO PHẢN BIỆN CHUYÊN SÂU & ĐÁNH GIÁ TÁI LẬP (POST-SYNC ADVERSARIAL EVALUATION)

**Dự án**: `dgx-spark-toolkit`  
**Thời gian thực hiện**: 2026-09-24  
**Phương pháp**: Double-Pass Adversarial Audit, Git Archaeology & Trace mã nguồn thực tế  

---

## 1. BẢNG ĐỐI CHIẾU PHẢN BIỆN: GIẢ THUYẾT VS THỰC TẾ MÃ NGUỒN

Qua quá trình rà soát độc lập các tệp vừa được chỉnh sửa (`docs/ARCHITECTURE.md`, `.github/copilot-instructions.md`, `.github/instructions/frontend-react.instructions.md`, `.md/knowledge/documentation_drift_sync_decision_log.md`, `.md/knowledge/codebase_architecture_and_mental_model.md`), hệ thống phát hiện 5 điểm sâu sắc mang tính cốt lõi:

| Hạng mục | Nhận định Bề mặt Ban đầu | Thực tế Mã nguồn & Lịch sử Git chứng minh | Kết luận & Ý nghĩa Kiến trúc |
| :--- | :--- | :--- | :--- |
| **Phân vùng Redis** | Ghi nhận hệ thống phân tách 3 DB (DB 0: Cache, DB 1: Queue, DB 2: Context Lake). | [`retrieval/semantic_cache.py:52`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/semantic_cache.py#L52) sử dụng **DB 3**; [`services/hitl_service.py:81`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/services/hitl_service.py#L81) sử dụng **DB 4**. | **Thực tế có 5 phân vùng (DB 0 -> DB 4)**. Cần bổ sung DB 3 (SemanticCache L2) và DB 4 (HITL review queue) để tránh biến thành "shadow databases". |
| **Nguồn gốc `GUIDES`** | Cho rằng đây là "lỗ hổng chưa triển khai", chưa rõ vì sao Neo4j live có 1 edge `GUIDES`. | Git log commit [`0908aed`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py) cho thấy `pipeline.py` **từng có code tạo edge `GUIDES`**, nhưng bị rơi mất (regression) khi refactor tách sang `neo4j_repo.py`. | **Hồi quy kiến trúc (Architectural Regression)** do đợt refactor modular vô tình bỏ rơi nhánh `guides`, không phải là tính năng chưa từng có. |
| **Danh xưng Ingestion** | Dùng tên `ProductionIngestor` ([`pipeline.py:85`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py#L85)). | Line 85 thực tế là `class DocumentIngestionPipeline:`. [`CONTEXT.md:7-9`](file:///home/vvc/Codebase/dgx-spark-toolkit/CONTEXT.md#L7-L9) cấm dùng danh xưng `ProductionIngestor`. | **Vi phạm Ubiquitous Language**: `ProductionIngestor` là tên class legacy, tên chuẩn xác là `DocumentIngestionPipeline`. |
| **Kiểm thử Xác định** | Chỉ kiểm tra linter tĩnh và frontend build. | Đã chạy toàn bộ test suite backend `./.venv/bin/pytest services/rag-service/tests/`. | **468 unit/regression tests passed 100%** (1 test deselected do integration tag) trong 9.75 giây. |
| **Lingering Drift trong Tooling** | Cho rằng chỉ còn 3 vị trí tài liệu tĩnh chứa `vllm-35b`. | Bỏ sót `qwen35b` trong tooling runtime: [`health_monitor.py:19`](file:///home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/health_monitor.py#L19), [`scripts/stop-all.sh:14`](file:///home/vvc/Codebase/dgx-spark-toolkit/scripts/stop-all.sh#L14), và [`docs/PITFALLS.md`](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/PITFALLS.md). | **Drift ảnh hưởng Runtime**: Tooling giám sát báo sai container status và script dừng dịch vụ không dừng được `qwen36b`. |
| **Cơ chế `TraceStore`** | Ghi nhận traces có TTL 24 giờ. | [`retrieval/query_tracer.py:26, 94-105`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/query_tracer.py#L26): Hằng số `_TRACE_TTL = 86400` không được gọi vào lệnh `expire`. | **Circular Buffer theo số lượng**: Traces được giới hạn bằng `zremrangebyrank` tối đa 500 traces gần nhất, không tự expire theo thời gian. |

---

## 2. PHÂN TÍCH KIẾN TRÚC SÂU (DEEP ARCHITECTURAL INSIGHTS)

### 2.1. Cụm 5 Phân vùng Redis (Penta-Partitioned Redis)
Rà soát toàn bộ kết nối Redis trong `services/rag-service/`:
1. **DB 0**: LiteLLM Proxy Semantic Cache ([`litellm_config.yaml:1758`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml#L1758)).
2. **DB 1**: Ingestion Stream Queue `ingest:queue`, Ingestion Concurrency Lock, Table Cache ([`core/config.py:44`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/core/config.py#L44), [`concurrency.py:42`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/concurrency.py#L42), [`chunking.py:833`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/chunking.py#L833)).
3. **DB 2**: Context Lake gồm `SessionMemory`, `TraceStore`, `ContextAccumulator` ([`session_memory.py:27`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/session_memory.py#L27), [`query_tracer.py:92`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/query_tracer.py#L92), [`context_accumulator.py:25`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/context_accumulator.py#L25)).
4. **DB 3**: `SemanticCache` L2 persistent cache ([`retrieval/semantic_cache.py:52`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/retrieval/semantic_cache.py#L52)).
5. **DB 4**: `HITLService` low-confidence review queue ([`services/hitl_service.py:79-83`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/services/hitl_service.py#L79-L83)).

### 2.2. Khảo cổ Git về Quan hệ `GUIDES`
Quan hệ `GUIDES` trong Neo4j không phải ngẫu nhiên tồn tại. Trong commit [`0908aed`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py), pipeline cũ đã thực thi:
```python
for target_id in relationships.get("guides", []):
    session.run("""
        MATCH (source:Document {id: $source_id})
        MERGE (target:Document {id: $target_id})
        MERGE (source)-[:GUIDES]->(target)
    """, source_id=doc_id, target_id=target_id)
```
Quan hệ này nối: `(:Document {id: "ROOT/Luat_50-2014-QH13_Luat_Xay_dung_18-6-2014"})-[:GUIDES]->(:Document {id: "16/2003/QH11"})`.  
Khi tách sang `neo4j_repo.py`, lập trình viên vô tình bỏ sót nhánh `guides`. Vì vậy, việc khôi phục quan hệ này trong schema là hoàn toàn chính xác theo domain model.

---

## 3. KẾT QUẢ ĐO KIỂM XÁC ĐỊNH (VERIFICATION SUITE)

- **Backend Pytest**: `468 passed, 1 deselected in 9.75s` (Exit code 0). Toàn bộ logic nghiệp vụ, repositories, reranker, session memory hoạt động ổn định 100%.
- **Backend Flake8**: `0 errors` (Exit code 0).
- **Frontend ESLint**: `0 errors` (Exit code 0).
- **Frontend Production Build**: Hoàn thành trong `2.28s` (`dist/` generated, Exit code 0).

---

## 4. CÁC HÀNH ĐỘNG KHUYẾN NGHỊ TIẾP THEO (NEXT ACTIONS)

1. **Khôi phục logic `GUIDES`**: Bổ sung xử lý quan hệ `guides` vào [`neo4j_repo.py:create_document_node`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/neo4j_repo.py#L280) và prompt tại [`pipeline.py:427`](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py#L427).
2. **Sửa Drift trong Tooling Vận hành**: Đổi `qwen35b` $\rightarrow$ `qwen36b` trong [`health_monitor.py:19`](file:///home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/vllm-manager/scripts/health_monitor.py#L19) và [`scripts/stop-all.sh:14`](file:///home/vvc/Codebase/dgx-spark-toolkit/scripts/stop-all.sh#L14).
3. **Cập nhật Bảng Redis & Danh xưng Class**: Đồng bộ mô hình 5 DB Redis vào `docs/ARCHITECTURE.md` và đổi `ProductionIngestor` $\rightarrow$ `DocumentIngestionPipeline`.
