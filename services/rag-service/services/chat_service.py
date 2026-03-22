import httpx
import logging

from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.retrieval_service import RetrievalService
from retrieval.query_rewriter import rewrite_query
from core.llm_client import call_llm
from core.prompts import get_system_prompt
from core.config import get_settings

logger = logging.getLogger(__name__)


class ChatService:
    """
    Service layer for chat/generation functionality.
    Orchestrates query rewriting, retrieval, and LLM generation.
    """

    def __init__(
        self,
        milvus_repo: MilvusRepository,
        neo4j_repo: Neo4jRepository,
        http_client: httpx.AsyncClient
    ):
        self.milvus_repo = milvus_repo
        self.neo4j_repo = neo4j_repo
        self.http_client = http_client
        self.retrieval_service = RetrievalService(milvus_repo, neo4j_repo)

    async def generate_response(
        self,
        query: str,
        history: list[dict] | None = None,
        language: str = "vi",
        model: str | None = None
    ) -> dict:
        """
        Generate a chat response with retrieved context.

        Args:
            query: User query string
            history: Conversation history (list of message dicts)
            language: Language code for system prompt (default "vi")
            model: Target LLM model (defaults to VLLM_MODEL from settings)

        Returns:
            Dict with keys: answer, context, usage, cached
        """
        settings = get_settings()

        # Build messages
        system_content = get_system_prompt(language)
        messages = [{"role": "system", "content": system_content}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": query})

        target_model = model if model else settings.VLLM_MODEL

        # 1. Query Rewriting (Fast 4B model)
        rewritten_query = await rewrite_query(query, self.http_client)

        # 2. Semantic Search & Graph Context
        # We increase search limit to 15 to give the reranker more candidates,
        # but only take the top results for LLM context.
        search_res = await self.retrieval_service.search(
            query=rewritten_query,
            limit=15,
            use_reranker=True
        )
        all_context_used = search_res["results"]

        # Format context for LLM
        context_str = "\n\n".join([
            f"[Source: {r.get('doc_number', 'unknown')}#page={r['page']}&rect={r.get('bbox', [0,0,1000,1000])}]\n{r['text']}"
            for r in all_context_used
        ])

        # 3. Final Reasoning (High-Power 35B model)
        messages.append({
            "role": "system",
            "content": f"Dưới đây là các đoạn trích từ văn bản pháp luật liên quan:\n\n{context_str}\n\nHãy trả lời câu hỏi dựa TRÊN CÁC NGUỒN TRÊN. Trích dẫn chính xác mã nguồn [Source: ID#page=X&rect=...] cho mỗi thông tin."
        })

        enable_thinking = "35b" in target_model.lower() or "core" in target_model.lower()
        extra = {"chat_template_kwargs": {"enable_thinking": True}} if enable_thinking else {}

        answer = await call_llm(
            self.http_client,
            messages,
            model=target_model,
            max_tokens=8192,
            stop=["\nUser:", "\nObservation:", "</s>"],
            extra_body={
                "repetition_penalty": 1.1,
                "presence_penalty": 0.1,
                **extra,
            },
        )

        return {
            "answer": answer,
            "context": all_context_used[:10],
            "usage": None,
            "cached": False
        }
