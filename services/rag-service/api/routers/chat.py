from fastapi import APIRouter, Depends, HTTPException, Request
from models.schemas import ChatRequest, ChatResponse
from core.database import get_milvus_repo, get_neo4j_repo, get_http_client
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.retrieval_service import RetrievalService
from retrieval.query_rewriter import rewrite_query
from core.prompts import get_system_prompt
from core.config import get_settings
import httpx
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_legal_docs",
        "description": "Semantic search for specific information within legal and BIM documents. Priority: Construction (BXD), BIM (ISO), and Government Decrees (ND-CP). Always include relevant domain keywords in query if ambiguous.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The semantic search query for document retrieval."},
                "limit": {"type": "integer", "description": "Number of document chunks to retrieve (default 5)."},
                "doc_type": {"type": "string", "description": "Filter by type (QD, TT, ND, etc.) if known."}
            },
            "required": ["query"]
        }
    }
}

GRAPH_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "graph_search",
        "description": "Traverse the legal graph to find relations (REPLACES, AMENDS, REFERENCES) or descendants (GUIDES) of a document.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "The document exact ID/Number (e.g. 15/2021/ND-CP)"},
                "find_guides": {"type": "boolean", "description": "If true, finds Circulars (Thông tư) that guide this Decree (Nghị định)."}
            },
            "required": ["doc_id"]
        }
    }
}

@router.post("/chat", tags=["Generation"], response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    try:
        settings = get_settings()
        retrieval_service = RetrievalService(milvus_repo, neo4j_repo)

        # Build messages
        system_content = get_system_prompt(request.language)
        messages = [{"role": "system", "content": system_content}]
        if request.history:
            messages.extend(request.history[-6:])
        messages.append({"role": "user", "content": request.query})

        target_model = request.model if request.model else settings.VLLM_MODEL
        all_context_used = []

        # 1. Query Rewriting (Fast 4B model)
        rewritten_query = await rewrite_query(request.query)

        # 2. Semantic Search & Graph Context
        # We increase search limit to 15 to give the reranker more candidates, 
        # but only take the top results for LLM context.
        search_res = await retrieval_service.search(
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

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 8192,
            "repetition_penalty": 1.1,
            "presence_penalty": 0.1,
            "stop": ["\nUser:", "\nObservation:", "</s>"],
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": True}
            } if "35b" in target_model.lower() or "core" in target_model.lower() else {}
        }

        # H2: use the shared client injected from lifespan — no new TCP connection per request
        resp = await http_client.post(
            f"{settings.VLLM_API_BASE}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"},
        )
        resp.raise_for_status()
        result = resp.json()

        choice = result["choices"][0]
        msg = choice["message"]

        return {
            "answer": msg["content"],
            "context": all_context_used[:10],
            "usage": result.get("usage"),
            "cached": False
        }

    except Exception as e:
        logger.error(f"Chat API error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
