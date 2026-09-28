#!/usr/bin/env python3
"""
DGX Spark Toolkit - Fast MCP Server (Lightweight HTTP Bridge)
Provides native Model Context Protocol (MCP) tools for AI coding agents
to interact with the Vietnamese Legal Document RAG platform on DGX Spark.

Architecture:
- Connects directly to RAG Service daemon on http://localhost:8005
- Process cold start ~0.3s (Python runtime + imports), sub-50ms tool request dispatch
- 0 MB additional VRAM consumption (avoids Pitfall #14 cold warmup)
"""

import json
import os
import sys
from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    MCPServer = None

try:
    import httpx
except ImportError:
    httpx = None


RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:8005")


def _http_post(endpoint: str, json_data: dict, timeout: float = 30.0) -> str:
    """Helper to dispatch HTTP POST to the local RAG service."""
    if httpx is None:
        return json.dumps({"error": "httpx is required"})
    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(f"{RAG_SERVICE_URL}{endpoint}", json=json_data)
            if res.status_code == 200:
                return res.text
            return json.dumps({"error": f"HTTP {res.status_code}", "detail": res.text})
    except Exception as e:
        return json.dumps({"error": str(e), "service_url": RAG_SERVICE_URL})


def _http_get(endpoint: str, params: Optional[dict] = None, timeout: float = 10.0) -> str:
    """Helper to dispatch HTTP GET to the local RAG service."""
    if httpx is None:
        return json.dumps({"error": "httpx is required"})
    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.get(f"{RAG_SERVICE_URL}{endpoint}", params=params)
            if res.status_code == 200:
                return res.text
            return json.dumps({"error": f"HTTP {res.status_code}", "detail": res.text})
    except Exception as e:
        return json.dumps({"error": str(e), "service_url": RAG_SERVICE_URL})


def _register_search_tools(server: Any) -> None:
    """Register corpus search tool."""
    @server.tool()
    def search_legal_corpus(query: str, limit: int = 5, use_reranker: bool = True) -> str:
        """Thực hiện tìm kiếm văn bản quy phạm pháp luật Việt Nam (Hybrid Vector + Graph RAG).

        Args:
            query: Câu hỏi hoặc từ khóa pháp lý cần tra cứu.
            limit: Số lượng kết quả mong muốn (mặc định 5).
            use_reranker: Áp dụng Cross-Encoder Reranker trên GPU để tối ưu độ chính xác.

        Returns:
            JSON string chứa danh sách kết quả, trích đoạn Điều/Khoản và điểm tương đồng.
        """
        payload = {"query": query, "limit": limit, "use_reranker": use_reranker}
        return _http_post("/search", payload, timeout=30.0)


def _register_graph_and_stat_tools(server: Any) -> None:
    """Register stats, graph validation, and preview tools."""
    @server.tool()
    def inspect_vector_stats() -> str:
        """Truy vấn số liệu thống kê thực thể trong Milvus Vector DB và đồ thị Neo4j.

        Returns:
            JSON string chứa tổng số vector chunks, entities và trạng thái collections.
        """
        return _http_get("/stats", timeout=10.0)

    @server.tool()
    def validate_legal_citation(so_hieu: str) -> str:
        """Tra cứu tính hợp lệ và phả hệ sửa đổi/thay thế của văn bản từ Neo4j Legal Graph.

        Args:
            so_hieu: Số hiệu hoặc doc_id văn bản cần tra cứu (ví dụ: '15/2021/TT-BXD', '50/2014/QH13').

        Returns:
            JSON string chứa nút văn bản, danh sách quan hệ kề và liên kết sửa đổi/thay thế.
        """
        from urllib.parse import quote
        encoded_id = quote(so_hieu, safe="")
        return _http_get(f"/graph/neighbors/{encoded_id}", timeout=10.0)

    @server.tool()
    def inspect_document_preview(doc_id: str, page: int = 1) -> str:
        """Xem trước nội dung trích xuất dạng base64 PNG của văn bản đã nạp theo trang.

        Args:
            doc_id: Định danh canonical của văn bản (ví dụ: '06/2021/TT-BXD').
            page: Số trang cần xem trước (mặc định 1).

        Returns:
            JSON string chứa doc source, page number và chuỗi base64 ảnh PNG.
        """
        return _http_get("/preview", params={"source": doc_id, "page": page}, timeout=10.0)


def create_mcp_server() -> Any:
    """Factory creating and configuring the DGX Spark Fast MCP Server."""
    if MCPServer is None:
        raise RuntimeError("Gói 'mcp' chưa được cài đặt. Vui lòng cài đặt: pip install mcp>=2.2.0")

    server = MCPServer(name="dgx-spark-toolkit")
    _register_search_tools(server)
    _register_graph_and_stat_tools(server)
    return server


def main() -> int:
    if MCPServer is None:
        print("[ERROR] Gói 'mcp' chưa được cài đặt trong môi trường Python.", file=sys.stderr)
        return 1

    server = create_mcp_server()
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
