# 0005. AI-Native Codebase Modularization & Agent Protocol

Chuyển dịch cấu trúc codebase `dgx-spark-toolkit` sang kiến trúc AI-Native thông qua việc phân tách các module monolithic theo Deep Seams, bổ sung Scoped Progressive Disclosure (`AGENTS.md`), cô lập Redis DB 3 cho Table Cache, và cung cấp Fast MCP Server cho các AI Coding Agents.

## Status
Accepted

## Context
Khi quy mô hệ thống tăng trưởng (18 Docker containers, Milvus `legal_docs_v11`, Neo4j Graph, 520+ tests), các tệp mã nguồn xử lý chính (`chunking.py` 893 dòng, `search_pipeline.py` 723 dòng) trở nên quá khổ:
1. Gây bùng nổ token budget (OpEx cao) và làm tăng nguy cơ attention drift / hallucination của các LLM coding agents.
2. Thiếu Scoped `AGENTS.md` tại các thư mục dịch vụ con (`services/rag-service`, `services/ai-gateway`, `services/frontend`), buộc tác nhân phải tìm kiếm trên toàn bộ repository.
3. Cache tóm tắt bảng trong `chunking.py` vô tình ghi vào Redis DB 1, vi phạm quy tắc phân vùng hạ tầng (DB 1 dành riêng cho `ingest:queue`).
4. Các AI Agents (Claude Code, Cursor, Antigravity, Grok) thiếu giao thức chuẩn hoá (Model Context Protocol - MCP) để tra cứu dữ liệu và trạng thái hệ thống.

## Decision
1. **Deep Seams Modularization**: Phân rã `chunking.py` thành package `ingestion.chunkers` (`base.py`, `legal.py`, `layout.py`, `table.py`, `fallback.py`) với các file độc lập có tính gắn kết cao (tất cả <= 240 dòng, trung bình ~150 dòng); duy trì Facade `chunking.py` (148 dòng) bảo đảm 100% tương thích ngược và zero-regression.
2. **KISS Refactoring trong Search Pipeline**: Tái cấu trúc các hàm phức tạp trong `search_pipeline.py` (`execute`, `_stage_agentic_multihop`, `_stage_intent_and_cache`, `_stage_graph_enrichment`) thành các sub-functions nội bộ tuân thủ nguyên tắc KISS (< 50 dòng), bảo đảm tính tất định và hiệu năng phản hồi cao khi trúng cache.
3. **Sửa Chữa Phân Vùng Redis**: Chuyển toàn bộ cache tóm tắt bảng về Redis DB 3 (SemanticCache L2 & Tier 0), giải phóng hoàn toàn Redis DB 1 cho hàng đợi nạp tài liệu.
4. **Scoped Progressive Disclosure**: Thiết lập các tệp `AGENTS.md` chuyên biệt (< 40 dòng/tệp) cho `services/rag-service/`, `services/ai-gateway/`, và `services/frontend/`.
5. **Lightweight MCP Server**: Xây dựng `scripts/mcp_server.py` theo mô hình HTTP Bridge kết nối cổng `:8005`, cho phép AI Agents tra cứu văn bản, kiểm tra số liệu vector và phả hệ pháp luật mà không tiêu tốn thêm VRAM hay kích hoạt cold model warmup.
6. **Schema Introspection**: Cung cấp script xuất tự động OpenAPI JSON Schema và tài liệu markdown ra `.md/schemas/`.

## Consequences
- **Tối ưu hóa Token Budget**: AI Agent có thể truy cập trực tiếp các sub-chunkers nhỏ gọn (100–240 dòng) thay vì nạp cả tệp 900 dòng vào ngữ cảnh.
- **An toàn Hạ tầng**: Loại bỏ hoàn toàn nguy cơ tranh chấp eviction trên Redis DB 1.
- **Tương tác Đa Tác nhân (Peer Agents)**: Tạo tiền đề cho các AI Agents (Antigravity, Grok, Claude Code) cộng tác trực tiếp và chính xác thông qua MCP chuẩn hoá.
