import logging
from typing import List, Dict, Any

import httpx

from repositories.milvus_repo import MilvusRepository
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from core.config import get_settings
from core.llm_client import call_llm

logger = logging.getLogger(__name__)


async def _get_full_embeddings(query: str) -> dict:
    """Return both dense and sparse embeddings for a query.

    This shared helper ensures hybrid search uses the full BGE-M3
    sparse path (BM25-like) rather than an empty sparse vector.
    """
    import asyncio
    from services.retrieval_service import get_embedding_model
    loop = asyncio.get_running_loop()
    model = get_embedding_model()
    # Run in executor to avoid blocking the event loop
    embeddings = await loop.run_in_executor(None, model.embed_query, query)
    return embeddings  # {"dense": [...], "sparse": {...}}


class LegalAnalysisService:
    def __init__(self, milvus_repo: MilvusRepository, graph_rag: AdvancedGraphRAG, http_client: httpx.AsyncClient | None = None):
        self.milvus_repo = milvus_repo
        self.graph_rag = graph_rag
        self.settings = get_settings()
        self._http_client = http_client

    async def analyze_conflicts(self, doc_id: str, query: str, depth: int = 1) -> Dict[str, Any]:
        """
        Compare a document with its predecessors to identify regulatory changes or conflicts.
        """
        logger.info(f"Analyzing conflicts for {doc_id} with query: '{query}' (depth={depth})")

        # 1. Get the legal timeline/predecessors from Neo4j
        timeline = await self.graph_rag.get_legal_timeline(doc_id)
        if not timeline or len(timeline) < 2:
            return {
                "status": "no_predecessors",
                "message": f"No previous versions or related documents found for {doc_id}.",
                "timeline": timeline
            }

        # The timeline is [Newest -> ... -> Oldest] or [Oldest -> ... -> Newest] depending on query.
        # get_legal_timeline query ORDER BY length(path) DESC returns the full path.
        # It's better to explicitly find the 'target' of REPLACES/AMENDS.

        predecessors = []
        for entry in timeline:
            if entry.get("id") != doc_id:
                predecessors.append(entry)
                if len(predecessors) >= depth:
                    break

        if not predecessors:
            return {"status": "no_predecessors", "timeline": timeline}

        # 2. Retrieve relevant chunks from the NEW document
        # We use a standard dense search for the specific topic within the document
        # [FIX] Use full hybrid embeddings (dense + sparse) — empty sparse
        # bypasses BM25 completely, causing poor exact-term lookup within docs.
        _emb_new = await _get_full_embeddings(query)
        new_results = await self.milvus_repo.hybrid_search(
            query_vector=_emb_new.get("dense", []),
            sparse_vector=_emb_new.get("sparse", {}),
            limit=5,
            expr=f"doc_number == '{doc_id.split('/')[-1]}'"
        )
        # Note: doc_number in Milvus usually doesn't include the namespace part if extracted via regex.
        # But doc_id in graph is Namespace/Number.

        new_context = "\n".join([hit.entity.get("text") for hit in new_results[0]]) if new_results else "No content found."

        # 3. Retrieve relevant chunks from PREDECESSOR(S)
        predecessor_analyses = []
        for pred in predecessors:
            pred_id = pred["id"]
            # Extract number from ID (Namespace/Number)
            pred_num = pred_id.split('/')[-1] if '/' in pred_id else pred_id

            _emb_pred = await _get_full_embeddings(query)
            pred_results = await self.milvus_repo.hybrid_search(
                query_vector=_emb_pred.get("dense", []),
                sparse_vector=_emb_pred.get("sparse", {}),
                limit=5,
                expr=f"doc_number == '{pred_num}'"
            )
            pred_context = "\n".join([hit.entity.get("text") for hit in pred_results[0]]) if pred_results else "No content found."

            # 4. LLM Delta Analysis
            analysis = await self._generate_delta_analysis(doc_id, pred_id, query, new_context, pred_context)
            predecessor_analyses.append({
                "predecessor_id": pred_id,
                "relation": pred.get("relation_to_next"),
                "analysis": analysis
            })

        return {
            "status": "success",
            "doc_id": doc_id,
            "query": query,
            "comparisons": predecessor_analyses
        }

    async def _get_query_embedding(self, query: str) -> List[float]:
        """Return only dense embedding (kept for backward compat with callers needing just dense)."""
        embeddings = await _get_full_embeddings(query)
        if isinstance(embeddings, dict):
            return embeddings.get("dense", [])
        return embeddings

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
            client = self._http_client or await self.graph_rag._get_client()
            return await call_llm(
                client,
                [
                    {"role": "system", "content": "Bạn là chuyên gia phân tích xung đột pháp luật chuyên sâu."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048,
            )
        except Exception as e:
            return f"Lỗi phân tích: {e}"
