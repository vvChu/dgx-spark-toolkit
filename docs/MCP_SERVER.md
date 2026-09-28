# DGX Spark Toolkit — Model Context Protocol (MCP) Server

Giao thức MCP Server cung cấp cho các AI Coding Agents (Claude Code, Cursor, Antigravity, Grok) các công cụ chuẩn hoá để tra cứu văn bản pháp luật, kiểm toán thực thể Milvus và đồ thị hiệu lực Neo4j trực tiếp từ môi trường IDE hoặc command line.

---

## 1. Cấu Trúc Công Cụ (Tools)

| Tên Tool | Endpoint RAG Service | Đầu Vào Chính | Đầu Ra |
| :--- | :--- | :--- | :--- |
| `search_legal_corpus` | `POST /search` | `query: str`, `limit: int = 5`, `use_reranker: bool = True` | JSON kết quả Điều/Khoản, scores |
| `inspect_vector_stats` | `GET /stats` | Không | JSON thống kê collections Milvus & Neo4j |
| `validate_legal_citation` | `GET /graph/neighbors/{so_hieu}` | `so_hieu: str` (ví dụ: `15/2021/TT-BXD`) | Trạng thái nút văn bản, liên kết sửa đổi/thay thế |
| `inspect_document_preview` | `GET /preview?source={doc_id}&page={page}` | `doc_id: str`, `page: int = 1` | JSON metadata & base64 PNG trang tài liệu |

---

## 2. Đặc Tính Hiệu Năng & Tài Nguyên

- **0 MB Additional VRAM**: Chạy dưới dạng HTTP Bridge tới daemon `:8005`, không nạp nhúng PyTorch model, tránh hoàn toàn cold warmup 94 giây (Pitfall #14).
- **Khởi động**: Cold start tiến trình ~0.3s (Python interpreter + thư viện `mcp`, `httpx`), latency chuyển tiếp yêu cầu HTTP nội bộ sub-50ms.

---

## 3. Hướng Dẫn Cấu Hình Kết Nối

### A. Claude Code / Antigravity / Cursor (`mcp.json`)

Thêm đoạn cấu hình sau vào tệp cấu hình MCP của bạn (ví dụ `~/.claude/mcp.json` hoặc `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "dgx-spark-toolkit": {
      "command": "/home/vvc/Codebase/dgx-spark-toolkit/.venv/bin/python",
      "args": [
        "/home/vvc/Codebase/dgx-spark-toolkit/scripts/mcp_server.py"
      ],
      "env": {
        "RAG_SERVICE_URL": "http://localhost:8005"
      }
    }
  }
}
```

### B. Kiểm Tra Trực Tiếp Qua Terminal

Khởi chạy MCP server ở chế độ stdio:
```bash
/home/vvc/Codebase/dgx-spark-toolkit/.venv/bin/python scripts/mcp_server.py
```
Server sẽ tự động lắng nghe các bản tin RPC chuẩn định dạng JSON-RPC 2.0 trên stdin/stdout.
