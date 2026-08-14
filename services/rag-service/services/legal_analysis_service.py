import logging
from typing import List, Dict, Any, Optional

import httpx

from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from retrieval.search_pipeline import SearchPipeline
from core.config import get_settings
from core.ai_gateway_client import get_ai_gateway_client, AIGatewayClient

logger = logging.getLogger(__name__)


class LegalAnalysisEngine:
    """Deep domain module for legal conflict analysis, compliance checking, and validity verification."""

    def __init__(
        self,
        milvus_repo: Optional[MilvusRepository] = None,
        graph_rag: Optional[AdvancedGraphRAG] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        ai_client: Optional[AIGatewayClient] = None,
        search_pipeline: Optional[SearchPipeline] = None,
    ):
        self.milvus_repo = milvus_repo
        self.graph_rag = graph_rag
        self.settings = get_settings()
        self._http_client = http_client
        self.ai_client = ai_client or get_ai_gateway_client(http_client)
        if search_pipeline is not None:
            self.search_pipeline = search_pipeline
        elif milvus_repo is not None:
            driver = getattr(graph_rag, "driver", None)
            neo4j = Neo4jRepository(driver) if driver else None
            self.search_pipeline = SearchPipeline(milvus_repo, neo4j, ai_client=self.ai_client)
        else:
            self.search_pipeline = None

    async def _fetch_doc_context(self, doc_number_or_id: str, query: str) -> str:
        """Fetch relevant chunk texts for a document using search pipeline."""
        if '/' in doc_number_or_id:
            parts = doc_number_or_id.split('/', 1)
            if not parts[0].isdigit() and not any(c.isdigit() for c in parts[0]):
                num = parts[1]
            else:
                num = doc_number_or_id
        else:
            num = doc_number_or_id

        if self.search_pipeline:
            try:
                res = await self.search_pipeline.search(
                    query=query,
                    limit=5,
                    doc_number=num,
                    use_cache=True,
                )
                texts = [r.get("text", "") for r in res.get("results", []) if r.get("text")]
                if texts:
                    return "\n".join(texts)
            except Exception as e:
                logger.warning(f"SearchPipeline fetch context error for {num}: {e}")

        return "No content found."

    async def analyze_conflicts(self, doc_id: str, query: str, depth: int = 1) -> Dict[str, Any]:
        """Compare a document with its predecessors to identify regulatory changes or conflicts."""
        logger.info(f"Analyzing conflicts for {doc_id} with query: '{query}' (depth={depth})")

        timeline = []
        if self.search_pipeline and hasattr(self.search_pipeline, "get_legal_timeline"):
            timeline = await self.search_pipeline.get_legal_timeline(doc_id)
        elif self.graph_rag and hasattr(self.graph_rag, "get_legal_timeline"):
            timeline = await self.graph_rag.get_legal_timeline(doc_id)

        if not timeline or len(timeline) < 2:
            return {
                "status": "no_predecessors",
                "message": f"No previous versions or related documents found for {doc_id}.",
                "timeline": timeline,
            }

        predecessors = []
        for entry in timeline:
            if entry.get("id") != doc_id:
                predecessors.append(entry)
                if len(predecessors) >= depth:
                    break

        if not predecessors:
            return {"status": "no_predecessors", "timeline": timeline}

        new_context = await self._fetch_doc_context(doc_id, query)

        predecessor_analyses = []
        for pred in predecessors:
            pred_id = pred["id"]
            pred_context = await self._fetch_doc_context(pred_id, query)

            analysis = await self._generate_delta_analysis(doc_id, pred_id, query, new_context, pred_context)
            predecessor_analyses.append({
                "predecessor_id": pred_id,
                "relation": pred.get("relation_to_next"),
                "analysis": analysis,
            })

        return {
            "status": "success",
            "doc_id": doc_id,
            "query": query,
            "comparisons": predecessor_analyses,
        }

    async def _generate_delta_analysis(self, doc_new: str, doc_old: str, query: str, context_new: str, context_old: str) -> str:
        prompt = f"""Bạn là một chuyên gia pháp lý cao cấp. Hãy so sánh sự thay đổi giữa văn bản MỚI và văn bản CŨ dựa trên nội dung được trích xuất dưới đây cho chủ đề: "{query}".

VĂN BẢN MỚI: {doc_new}
NỘI DUNG TRÍCH XUẤT (VĂN BẢN MỚI):
{context_new}

VĂN BẢN CŨ: {doc_old}
NỘI DUNG TRÍCH XUẤT (VĂN BẢN CŨ):
{context_old}

Yêu cầu phân tích:
1. **Điểm giữ nguyên**: Các quy định không thay đổi.
2. **Điểm thay đổi/Sửa đổi**: So sánh trực tiếp [Cũ] -> [Mới]. Phân tích ý nghĩa của sự thay đổi này (chặt chẽ hơn, nới lỏng hơn, hay làm rõ hơn).
3. **Điểm bãi bỏ**: Những nội dung có trong văn bản cũ nhưng không còn xuất hiện trong văn bản mới.
4. **Điểm mới**: Những quy định hoàn toàn mới chưa từng có trước đây.
5. **Cảnh báo xung đột**: Nếu có mâu thuẫn trực tiếp gây khó khăn cho việc áp dụng.

Trình bày bằng tiếng Việt, có cấu trúc rõ ràng (sử dụng Header và Bullet points).
"""
        try:
            return await self.ai_client.complete(
                [
                    {"role": "system", "content": "Bạn là chuyên gia phân tích xung đột pháp luật chuyên sâu."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048,
            )
        except Exception as e:
            return f"Lỗi phân tích: {e}"


class LegalAnalysisService(LegalAnalysisEngine):
    """Backward-compatible facade alias for LegalAnalysisEngine."""
    pass


class InMemoryLegalAnalysisEngine(LegalAnalysisEngine):
    """In-memory test adapter for LegalAnalysisEngine for offline unit testing."""

    def __init__(self, default_analysis: str = "Mocked Delta Analysis"):
        self.default_analysis = default_analysis
        self.call_history: List[Dict[str, Any]] = []

    async def analyze_conflicts(self, doc_id: str, query: str, depth: int = 1) -> Dict[str, Any]:
        self.call_history.append({"doc_id": doc_id, "query": query, "depth": depth})
        return {
            "status": "success",
            "doc_id": doc_id,
            "query": query,
            "comparisons": [
                {
                    "predecessor_id": "mock_pred_1",
                    "relation": "REPLACES",
                    "analysis": self.default_analysis,
                }
            ]
        }

