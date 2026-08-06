"""Server-Sent Events (SSE) streaming endpoint for chat responses.

Provides real-time token streaming for the /chat/stream endpoint,
reducing perceived latency for long LLM responses (up to 8192 tokens).
Integrates Context Lake: session memory and query tracing.
"""
import json
import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from models.schemas import ChatRequest
from core.config import get_settings
from core.database import get_milvus_repo, get_neo4j_repo, get_http_client
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from retrieval.search_pipeline import SearchPipeline
from retrieval.query_rewriter import rewrite_query
from retrieval.query_tracer import QueryTracer
from core.prompts import get_system_prompt

logger = logging.getLogger(__name__)
router = APIRouter()


async def _stream_chat(
    query: str,
    history: list[dict] | None,
    language: str,
    model: str | None,
    session_id: str | None,
    milvus_repo: MilvusRepository,
    neo4j_repo: Neo4jRepository,
    http_client: httpx.AsyncClient,
    session_memory=None,
    trace_store=None,
    context_accumulator=None,
):
    """Generator that yields SSE events for streaming chat."""
    try:
        settings = get_settings()
        target_model = model or settings.VLLM_MODEL

        # Initialize tracer
        tracer = QueryTracer(query, session_id=session_id)

        # Load session context
        session_context_str = ""
        if session_memory and session_id:
            try:
                session_context_str = await session_memory.get_context_summary(session_id) or ""
            except Exception as e:
                logger.warning("Session memory load failed in stream: %s", e)

        # 1. Retrieve context (non-streaming part)
        retrieval = SearchPipeline(milvus_repo, neo4j_repo)
        rewritten = await rewrite_query(query, http_client)
        search_res = await retrieval.search(
            query=rewritten, limit=15, use_reranker=True,
            session_id=session_id, tracer=tracer,
        )
        context_results = search_res.get("results", []) if isinstance(search_res, dict) else []

        # Update context accumulator
        if context_accumulator and session_id:
            try:
                await context_accumulator.add_retrieval(
                    session_id, context_results,
                    [r.get("score", 0.5) for r in context_results],
                )
            except Exception:
                pass

        context_str = "\n\n".join([
            f"[Source: {r.get('doc_number', 'unknown')}#page={r.get('page', 0)}]\n{r.get('text', '')}"
            for r in context_results
        ])

        # Send context as first SSE event
        yield f"data: {json.dumps({'type': 'context', 'data': context_results[:10]}, ensure_ascii=False, default=str)}\n\n"

        # 2. Build messages
        system_content = get_system_prompt(language)
        messages = [{"role": "system", "content": system_content}]

        # Inject session context
        if session_context_str:
            messages.append({"role": "system", "content": session_context_str})
        elif history:
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
        tracer.start_step("generate_stream")
        full_answer = []
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

                    # Store session memory and trace after stream completes
                    answer_text = "".join(full_answer)
                    tracer.end_step(model=target_model, answer_length=len(answer_text))

                    if session_memory and session_id:
                        try:
                            sources = [r.get("doc_number", "") for r in context_results[:5]]
                            await session_memory.add_turn(session_id, query, answer_text, sources)
                        except Exception:
                            pass

                    trace_data = tracer.finalize(result_count=len(context_results), model=target_model)
                    if trace_store:
                        try:
                            await trace_store.store(trace_data)
                        except Exception:
                            pass

                    # Send trace as final event
                    yield f"data: {json.dumps({'type': 'trace', 'data': trace_data}, ensure_ascii=False, default=str)}\n\n"
                    return
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_answer.append(content)
                        yield f"data: {json.dumps({'type': 'token', 'data': content}, ensure_ascii=False)}\n\n"
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        logger.error(f"Streaming chat error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/chat/stream", tags=["Generation"])
async def chat_stream_endpoint(
    request_obj: Request,
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
            session_id=request.session_id,
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            http_client=http_client,
            session_memory=getattr(request_obj.app.state, "session_memory", None),
            trace_store=getattr(request_obj.app.state, "trace_store", None),
            context_accumulator=getattr(request_obj.app.state, "context_accumulator", None),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
