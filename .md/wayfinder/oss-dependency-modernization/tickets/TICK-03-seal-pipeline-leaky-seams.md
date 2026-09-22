# Ticket [TICK-03]: Refactor Pipeline Ingestion Bịt kín Leaky Seams Milvus & Neo4j

**Bản đồ cha:** [Bản đồ Định hướng Hiện đại hóa Dependency](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 22/09/2026  
**Phụ thuộc:** Không có (Unblocked)  

---

## 1. Mục tiêu đã hoàn thành
Thực thi triệt để nguyên lý Deep Seams (ADR-0035 / ccba-codebase-design): Chuyển toàn bộ các lệnh gọi trực tiếp SDK `pymilvus` và `neo4j` trong [pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py) về các Adapter chuẩn tại `repositories/`, bảo đảm khi thư viện bên thứ ba nâng cấp API thì chỉ duy nhất 1 file Adapter bị ảnh hưởng.

## 2. Chi tiết Triển khai đã áp dụng
1. Đã mở rộng [services/rag-service/repositories/milvus_repo.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/milvus_repo.py):
   - Bổ sung phương thức `ensure_collection_schema(...)` và `close(...)` vào `MilvusRepository`.
2. Đã mở rộng [services/rag-service/repositories/neo4j_repo.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/neo4j_repo.py):
   - Bổ sung phương thức `init_schema(...)` và `close(...)` vào `Neo4jRepository`.
   - Xóa bỏ `@property def driver(self) -> AsyncDriver:` để chấm dứt hoàn toàn việc để lộ client database gốc ra ngoài.
3. Đã mở rộng [services/rag-service/repositories/document_store.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/document_store.py):
   - Bổ sung factory method `DocumentStore.create_default(...)` và các hàm vòng đời `init_infrastructure_sync()`, `close_sync()`.
   - Bổ sung các phương thức tương ứng cho `InMemoryDocumentStore` bảo đảm tính đa hình hoàn hảo.
4. Đã refactor [services/rag-service/ingestion/pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py):
   - Xóa bỏ hoàn toàn các dòng import direct SDK: `from pymilvus import ...` và `from neo4j import ...`.
   - Chuyển toàn bộ khởi tạo và kết nối database sang `DocumentStore` thông qua Dependency Injection.
   - Chuyển `init_neo4j()`, `setup_collection()` thành các delegate stubs an toàn.

## 3. Nghiệm thu Thực tế
- [x] Lệnh kiểm tra `grep -E "(from pymilvus import|from neo4j import)" services/rag-service/ingestion/pipeline.py` trả về `CLEAN`.
- [x] Toàn bộ test suite chạy thành công 100%: **408 passed, 1 deselected trong 1.96s** (bao gồm các test mới cho `init_schema`, `ensure_collection_schema`, và `close`).
- [x] Linter `flake8` trên tất cả các file sửa đổi đạt chuẩn **0 lỗi**.
