"""Server-Sent Events (SSE) streaming endpoint for chat responses.

Provides real-time token streaming for the /chat/stream endpoint,
reducing perceived latency for long LLM responses (up to 8192 tokens).
"""
import json
import logging

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from models.schemas import ChatRequest
from core.config import get_settings
from core.database import get_milvus_repo, get_neo4j_repo, get_http_client
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.retrieval_service import RetrievalService
from retrieval.query_rewriter import rewrite_query
from core.prompts import get_system_prompt

logger = logging.getLogger(__name__)
router = APIRouter()


async def _stream_chat(
    query: str,
    history: list[dict] | None,
    language: str,
    model: str | None,
    milvus_repo: MilvusRepository,
    neo4j_repo: Neo4jRepository,
    http_client: httpx.AsyncClient,
):
    """Generator that yields SSE events for streaming chat."""
    try:
        settings = get_settings()
        target_model = model or settings.VLLM_MODEL

        # 1. Retrieve context (non-streaming part)
        retrieval = RetrievalService(milvus_repo, neo4j_repo)
        rewritten = await rewrite_query(query, http_client)
        search_res = await retrieval.search(query=rewritten, limit=15, use_reranker=True)
        context_results = search_res.get("results", []) if isinstance(search_res, dict) else []

        context_str = "\n\n".join([
            f"[Source: {r.get('doc_number', 'unknown')}#page={r.get('page', 0)}]\n{r.get('text', '')}"
            for r in context_results
        ])

        # Send context as first SSE event
        yield f"data: {json.dumps({'type': 'context', 'data': context_results[:10]}, ensure_ascii=False, default=str)}\n\n"

        # 2. Build messages
        system_content = get_system_prompt(language)
        messages = [{"role": "system", "content": system_content}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": query})
        messages.append({
            "role": "system",
            "content": f"Dưới đây là các đoạn trích từ văn bản pháp luật liên quan:\n\n{context_str}\n\nHãy trả lời câu hỏi dựa TRÊN CÁC NGUỒN TRÊN."
        })

        enable_thinking = "35b" in target_model.lower() or "core" in target_model.lower()
        extra = {"chat_template_kwargs": {"enable_thinking": True}} if enable_thinking else {}

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 8192,
            "stream": True,
            "stop": ["\nUser:", "\nObservation:", "</s>"],
            "repetition_penalty": 1.1,
            "presence_penalty": 0.1,
            **extra,
        }

        # 3. Stream from LLM via AI Gateway
        async with http_client.stream(
            "POST",
            f"{settings.VLLM_API_BASE}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"},
            timeout=120.0,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    yield "data: [DONE]\n\n"
                    return
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield f"data: {json.dumps({'type': 'token', 'data': content}, ensure_ascii=False)}\n\n"
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        logger.error(f"Streaming chat error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/chat/stream", tags=["Generation"])
async def chat_stream_endpoint(
    request: ChatRequest,
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    """Stream a chat response with retrieved legal document context via SSE."""
    return StreamingResponse(
        _stream_chat(
            query=request.query,
            history=request.history,
            language=request.language,
            model=request.model,
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            http_client=http_client,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
