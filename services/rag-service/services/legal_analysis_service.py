import logging
import json
import asyncio
from typing import List, Dict, Any
from repositories.milvus_repo import MilvusRepository
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from core.config import get_settings

logger = logging.getLogger(__name__)

class LegalAnalysisService:
    def __init__(self, milvus_repo: MilvusRepository, graph_rag: AdvancedGraphRAG):
        self.milvus_repo = milvus_repo
        self.graph_rag = graph_rag
        self.settings = get_settings()

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
        new_results = await self.milvus_repo.hybrid_search(
            query_vector=await self._get_query_embedding(query),
            sparse_query=None, # Simplified for intra-doc search
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
            
            pred_results = await self.milvus_repo.hybrid_search(
                query_vector=await self._get_query_embedding(query),
                sparse_query=None,
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
        from services.retrieval_service import get_embedding_model
        model = get_embedding_model()
        # In a real async environment, we should run this in an executor, but for this utility
        # we'll assume the cache or small model makes it fast enough.
        return model.embed_query(query)["dense"]

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
            payload = {
                "model": self.settings.VLLM_MODEL,
                "messages": [
                    {"role": "system", "content": "Bạn là chuyên gia phân tích xung đột pháp luật chuyên sâu."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2048
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{self.settings.VLLM_API_BASE}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.settings.LITELLM_MASTER_KEY.get_secret_value()}"}
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
                else:
                    return f"Lỗi gọi LLM: {resp.text}"
        except Exception as e:
            return f"Lỗi phân tích: {e}"
