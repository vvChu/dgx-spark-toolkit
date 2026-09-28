import json
import logging
import uuid
import httpx

from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from retrieval.search_pipeline import SearchPipeline
from retrieval.query_rewriter import rewrite_query
from retrieval.query_tracer import QueryTracer
from core.ai_gateway_client import get_ai_gateway_client, AIGatewayClient
from core.prompts import get_system_prompt
from core.config import get_settings

logger = logging.getLogger(__name__)


class ChatService:
    """
    Service layer for chat/generation functionality.
    Orchestrates query rewriting, retrieval, and LLM generation.
    Integrates Context Lake: session memory, reasoning traces,
    context accumulation, and optional agentic retrieval.
    """

    def __init__(
        self,
        milvus_repo: MilvusRepository | None = None,
        neo4j_repo: Neo4jRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
        session_memory=None,
        trace_store=None,
        context_accumulator=None,
        ai_client: AIGatewayClient | None = None,
        search_pipeline: SearchPipeline | None = None,
    ):
        self.milvus_repo = milvus_repo
        self.neo4j_repo = neo4j_repo
        self.http_client = http_client
        self.ai_client = ai_client or (get_ai_gateway_client(http_client) if http_client else get_ai_gateway_client())
        if search_pipeline is not None:
            self.retrieval_service = search_pipeline
        elif milvus_repo is not None and neo4j_repo is not None:
            self.retrieval_service = SearchPipeline(milvus_repo, neo4j_repo, ai_client=self.ai_client)
        else:
            self.retrieval_service = None
        self.search_pipeline = self.retrieval_service
        self.session_memory = session_memory
        self.trace_store = trace_store
        self.context_accumulator = context_accumulator

    async def generate_response(
        self,
        query: str,
        history: list[dict] | None = None,
        language: str = "vi",
        model: str | None = None,
        session_id: str | None = None,
        use_agentic: bool = False,
    ) -> dict:
        """Generate a chat response with retrieved context.

        Orchestrates 6 sub-steps:
          1. Load session context from Redis
          2. Build message array
          3. Retrieve relevant documents (standard or agentic)
          4. Accumulate cross-turn context
          5. Generate LLM answer
          6. Store session turn + trace
        """
        settings = get_settings()
        session_id = session_id or str(uuid.uuid4())[:12]
        tracer = QueryTracer(query, session_id=session_id)
        target_model = model or settings.VLLM_MODEL

        # 1. Session Memory
        session_context = await self._load_session_context(session_id, tracer)

        # 2. Retrieve
        all_context = await self._retrieve_context(query, tracer, session_id, use_agentic)

        # 3. Accumulate
        all_context = await self._accumulate_context(session_id, all_context, tracer)

        # 4. Build messages (single unified system message at beginning)
        messages = self._build_messages(
            query, history, session_context, language, all_context=all_context
        )

        # 5. Generate
        answer = await self._generate_answer(messages, target_model, tracer)

        # 6. Store turn + trace
        trace_data = await self._store_turn(
            session_id, query, answer, all_context, target_model, tracer
        )

        return {
            "answer": answer,
            "context": all_context[:10],
            "usage": None,
            "cached": False,
            "session_id": session_id,
            "trace": trace_data,
        }

    # ── Sub-steps ─────────────────────────────────────────────────────

    async def _load_session_context(self, session_id: str, tracer: QueryTracer) -> str:
        """Load past conversation context from session memory."""
        if not self.session_memory:
            return ""
        tracer.start_step("session_memory_load")
        try:
            ctx = await self.session_memory.get_context_summary(session_id) or ""
        except Exception as e:
            logger.warning("Session memory load failed: %s", e)
            ctx = ""
        tracer.end_step(has_context=bool(ctx))
        return ctx

    def _build_messages(
        self, query: str, history: list[dict] | None,
        session_context: str, language: str,
        all_context: list[dict] | None = None,
    ) -> list[dict]:
        """Construct the OpenAI-style messages array with a single consolidated system message."""
        system_sections = [get_system_prompt(language)]
        if session_context:
            system_sections.append(f"Ngữ cảnh lịch sử hội thoại trước đó:\n{session_context}")
        if all_context:
            system_sections.append(self._format_context(all_context))

        messages = [{"role": "system", "content": "\n\n---\n\n".join(system_sections)}]
        # Add client-sent history only when no session context (defense against system role injection & malformed payloads)
        if history and not session_context:
            clean_history = []
            for m in history[-6:]:
                if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                    clean_history.append({
                        "role": str(m["role"]),
                        "content": str(m.get("content") or ""),
                    })
            messages.extend(clean_history)
        messages.append({"role": "user", "content": query})
        return messages

    async def _retrieve_context(
        self, query: str, tracer: QueryTracer,
        session_id: str, use_agentic: bool,
    ) -> list[dict]:
        """Execute standard or agentic retrieval."""
        search_res = await self.retrieval_service.search(
            query=query,
            limit=15,
            use_reranker=True,
            use_agentic=use_agentic,
            session_id=session_id,
            tracer=tracer,
        )
        return search_res.get("results", [])

    async def _accumulate_context(
        self, session_id: str, results: list[dict], tracer: QueryTracer,
    ) -> list[dict]:
        """Merge current results with past session context via Context Lake."""
        if not self.context_accumulator or not session_id:
            return results

        tracer.start_step("context_accumulate")
        try:
            await self.context_accumulator.add_retrieval(
                session_id, results,
                [r.get("score", 0.5) for r in results],
            )
            accumulated = await self.context_accumulator.get_accumulated_context(session_id)
            seen_keys = {r.get("doc_number", "") + str(r.get("page", 0)) for r in results}
            for acc in accumulated:
                key = acc.get("doc_number", "") + str(acc.get("page", 0))
                if key not in seen_keys:
                    results.append(acc)
                    seen_keys.add(key)
            tracer.end_step(accumulated_count=len(accumulated))
        except Exception as e:
            logger.warning("Context accumulator failed: %s", e)
            tracer.end_step(error=str(e))
        return results

    @staticmethod
    def _format_context(results: list[dict]) -> str:
        """Format retrieved results as a context string for the LLM."""
        context_str = "\n\n".join([
            f"[Source: {r.get('doc_number', 'unknown')}#page={r.get('page', 0)}&rect={r.get('bbox', [0, 0, 1000, 1000])}]\n{r.get('text', '')}"
            for r in results
        ])
        return (
            f"Dưới đây là các đoạn trích từ văn bản pháp luật liên quan:\n\n{context_str}\n\n"
            f"Hãy trả lời câu hỏi dựa TRÊN CÁC NGUỒN TRÊN. Trích dẫn chính xác mã nguồn [Source: ID#page=X&rect=...] cho mỗi thông tin."
        )

    async def _generate_answer(
        self, messages: list[dict], target_model: str, tracer: QueryTracer,
    ) -> str:
        """Call the LLM and return the generated answer."""
        tracer.start_step("generate")
        enable_thinking = "coder" in target_model.lower() or ("qwen" in target_model.lower() and "primary" in target_model.lower())
        extra = {"chat_template_kwargs": {"enable_thinking": True}} if enable_thinking else {}

        answer = await self.ai_client.complete(
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
        tracer.end_step(model=target_model, answer_length=len(answer))
        return answer

    async def _store_turn(
        self, session_id: str, query: str, answer: str,
        results: list[dict], target_model: str, tracer: QueryTracer,
    ) -> dict:
        """Store session memory turn and finalize query trace."""
        if self.session_memory:
            try:
                sources = [r.get("doc_number", "") for r in results[:5] if r.get("doc_number")]
                await self.session_memory.add_turn(session_id, query, answer, sources)
            except Exception as e:
                logger.warning("Session memory save failed: %s", e)

        trace_data = tracer.finalize(result_count=len(results), model=target_model)

        if self.trace_store:
            try:
                await self.trace_store.store(trace_data)
            except Exception as e:
                logger.warning("Trace store failed: %s", e)

        return trace_data

    async def stream_response(
        self,
        query: str,
        history: list[dict] | None = None,
        language: str = "vi",
        model: str | None = None,
        session_id: str | None = None,
        use_agentic: bool = False,
    ):
        """Generator yielding SSE events for real-time streaming chat responses."""
        settings = get_settings()
        session_id = session_id or str(uuid.uuid4())[:12]
        tracer = QueryTracer(query, session_id=session_id)
        target_model = model or settings.VLLM_MODEL

        try:
            # 1. Session Memory
            session_context = await self._load_session_context(session_id, tracer)

            # 2. Retrieve Context
            all_context = await self._retrieve_context(query, tracer, session_id, use_agentic)

            # 3. Accumulate Context
            all_context = await self._accumulate_context(session_id, all_context, tracer)

            # Yield context as first SSE event
            yield f"data: {json.dumps({'type': 'context', 'data': all_context[:10]}, ensure_ascii=False, default=str)}\n\n"

            # 4. Build Messages (single unified system message at beginning)
            messages = self._build_messages(
                query, history, session_context, language, all_context=all_context
            )

            # 5. Stream tokens from LLM via AIGatewayClient seam
            tracer.start_step("generate_stream")
            full_answer = []
            full_thought = []

            async for chunk in self.ai_client.stream(
                messages,
                model=target_model,
                temperature=0.1,
                max_tokens=8192,
                stop=["\nUser:", "\nObservation:", "</s>"],
                extra_body={
                    "repetition_penalty": 1.1,
                    "presence_penalty": 0.1,
                },
                timeout=120.0,
            ):
                if chunk.is_thought:
                    full_thought.append(chunk.text)
                    yield f"data: {json.dumps({'type': 'thought', 'data': chunk.text}, ensure_ascii=False)}\n\n"
                else:
                    full_answer.append(chunk.text)
                    yield f"data: {json.dumps({'type': 'token', 'data': chunk.text}, ensure_ascii=False)}\n\n"

            answer_text = "".join(full_answer)
            tracer.end_step(model=target_model, answer_length=len(answer_text))

            trace_data = await self._store_turn(
                session_id, query, answer_text, all_context, target_model, tracer
            )

            yield f"data: {json.dumps({'type': 'trace', 'data': trace_data}, ensure_ascii=False, default=str)}\n\n"
            yield "data: [DONE]\n\n"
            return

        except Exception as e:
            logger.error("Streaming chat error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

