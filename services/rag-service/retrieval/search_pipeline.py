"""Deep SearchPipeline module for hybrid vector search, reranking, and Graph RAG enrichment."""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import numpy as np
from prometheus_client import Counter, Histogram

from core.config import get_settings
from core.singleton import LazyInit
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from retrieval.hyde import HyDEGenerator
from retrieval.query_classifier import classify_query, QueryIntent
from retrieval.query_rewriter import rewrite_query
from retrieval.query_tracer import QueryTracer
from retrieval.reranker import get_reranker
from retrieval.semantic_cache import SemanticCache

from core.ai_gateway_client import get_ai_gateway_client, AIGatewayClient

logger = logging.getLogger(__name__)

# Prometheus Metrics
SEARCH_LATENCY = Histogram('rag_search_latency_seconds', 'Latency of search requests', buckets=(1, 2, 5, 10, 15, 20, 30, 60))
SEMANTIC_CACHE_HITS = Counter('rag_semantic_cache_hits_total', 'Total semantic cache hits')
HYBRID_RECALL_10 = Counter('rag_hybrid_recall_top10_total', 'Total hybrid searches')
GRAPH_TIMELINE_HOPS = Histogram('rag_graph_timeline_hops_total', 'Number of hops in timeline traversal', buckets=(1, 2, 3, 5, 10))
TIMELINE_GEN_COUNT = Counter('rag_timeline_generated_total', 'Total legal timelines generated')
QUERY_INTENT_COUNTER = Counter('rag_query_intent_total', 'Query intents classified', ['intent'])

_FILTER_UNSAFE = re.compile(r'["\\\\\\x00-\\x1f]')
_BBOX_FALLBACK = [0, 0, 1000, 1000]


def _sanitize_filter_value(value: str) -> str:
    return _FILTER_UNSAFE.sub('', str(value))


def _safe_json_loads(value: str) -> list:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return _BBOX_FALLBACK


def _get_hit_entity(hit: Any) -> dict:
    if hasattr(hit, "entity"):
        return hit.entity
    if isinstance(hit, dict):
        return hit.get("entity", hit)
    return {}


def _get_hit_score(hit: Any) -> float:
    if hasattr(hit, "score"):
        return float(hit.score)
    if isinstance(hit, dict):
        return float(hit.get("score", 0.0))
    return 0.0


def _build_result_item(entity: dict, text: str, score: float) -> dict:
    return {
        "text": text, "source": entity.get("source"), "page": entity.get("page", 0),
        "summary": entity.get("summary", ""), "doc_date": entity.get("doc_date", ""),
        "doc_type": entity.get("doc_type", ""), "authority": entity.get("authority", ""),
        "doc_number": entity.get("doc_number", ""),
        "is_table": entity.get("is_table", False), "chunk_type": entity.get("chunk_type", ""),
        "parent_id": entity.get("parent_id", ""),
        "bbox": _safe_json_loads(entity.get("bbox", "[0,0,1000,1000]")),
        "validity_status": entity.get("validity_status", "ACTIVE"),
        "project_code": entity.get("project_code", "GENERIC"),
        "discipline": entity.get("discipline", "UNKNOWN"),
        "hierarchy_path": entity.get("hierarchy_path", ""),
        "doc_status": entity.get("doc_status", "ACTIVE"),
        "revision": entity.get("revision", 0),
        "score": score,
    }


_semantic_cache = LazyInit(lambda: SemanticCache(
    threshold=get_settings().SEMANTIC_CACHE_THRESHOLD,
    ttl_seconds=get_settings().SEMANTIC_CACHE_TTL_SECONDS,
    redis_url=get_settings().REDIS_URL if get_settings().SEMANTIC_CACHE_REDIS_ENABLED else None,
))
_hyde_gen = LazyInit(lambda: HyDEGenerator())
_embedding_model = LazyInit(lambda: BGE_M3_HybridEmbedding())


def get_embedding_model() -> BGE_M3_HybridEmbedding:
    return _embedding_model.get()


_AGENTIC_PLAN_PROMPT = """Bạn là chuyên gia phân tích truy vấn pháp luật Việt Nam. Phân tích câu hỏi sau và xác định các nội dung cần tra cứu.

Câu hỏi: {query}

Trả về JSON:
{{
  "sub_queries": ["câu hỏi phụ 1", "câu hỏi phụ 2"],
  "reasoning": "giải thích ngắn gọn"
}}

Quy tắc:
- Tối đa 3 sub_queries độc lập, tập trung vào từ khóa pháp lý cốt lõi.
- Nếu câu hỏi đơn giản, trả về 1 sub_query giống câu hỏi gốc."""

_AGENTIC_EVAL_PROMPT = """Đánh giá xem các trích đoạn văn bản dưới đây có đủ cơ sở để trả lời câu hỏi pháp lý hay chưa.

Câu hỏi: {query}

Trích đoạn:
{context}

Trả về JSON:
{{
  "is_sufficient": true/false,
  "confidence": 0.0-1.0,
  "follow_up_query": "câu hỏi bổ sung nếu còn thiếu"
}}"""


@dataclass
class SearchContext:
    raw_query: str
    limit: int = 10
    use_reranker: bool = True
    doc_type: Optional[str] = None
    authority: Optional[str] = None
    year: Optional[int] = None
    doc_number: Optional[str] = None
    use_hyde: bool = False
    use_agentic: Optional[bool] = None
    use_cache: bool = True
    session_id: Optional[str] = None
    tracer: Optional[QueryTracer] = None
    ai_client: Optional[AIGatewayClient] = None

    # Pipeline processing state
    intent: Optional[QueryIntent] = None
    filter_expr: Optional[str] = None
    cache_filter_key: str = ""
    search_query: str = ""
    query_vector_np: Optional[np.ndarray] = None
    query_vector: Optional[list] = None
    sparse_query: Optional[dict] = None
    raw_hits: Optional[list] = None
    top_results: List[Dict[str, Any]] = field(default_factory=list)
    cached_hit: bool = False
    search_grounding_triggered: bool = False

    # Multi-hop agentic state
    sub_queries: List[str] = field(default_factory=list)
    hops: int = 1
    reasoning: str = ""
    is_sufficient: bool = True
    confidence: float = 1.0


async def stage1_fast_batch_rerank(query: str, docs: List[str], top_k: int = 10, ai_client: Optional[AIGatewayClient] = None) -> List[str]:
    """Stage 1: Fast batch filtering using Gemini 3.5 Flash Lite (250K TPM) with Gemma 4 fallback."""
    if len(docs) <= top_k:
        return docs

    try:
        client = ai_client or get_ai_gateway_client()

        doc_entries = [f"[{i+1}] {text[:250]}" for i, text in enumerate(docs[:30])]
        prompt = (
            f"Query: {query}\n\n"
            f"Evaluate and rank the following document chunks by legal relevance to the query.\n"
            f"Return a JSON object with key 'top_indices' containing an array of 1-based integer indices of top {top_k} most relevant chunks.\n\n"
            f"Chunks:\n" + "\n".join(doc_entries)
        )
        messages = [{"role": "user", "content": prompt}]
        res_data = await client.complete_json(
            messages,
            model="gemini-3.5-flash-lite",
            model_chain=["gemini-3.5-flash-lite", "claude-haiku-4"],
            timeout=10.0,
            retries=1,
        )
        if isinstance(res_data, list):
            indices = res_data
        elif isinstance(res_data, dict):
            indices = res_data.get("top_indices", res_data.get("indices", []))
        else:
            indices = []

        filtered_docs = []
        if isinstance(indices, list):
            for item in indices:
                idx = item.get("index") if isinstance(item, dict) else item
                if isinstance(idx, int) and 1 <= idx <= len(docs):
                    filtered_docs.append(docs[idx - 1])
        if filtered_docs:
            for d in docs:
                if len(filtered_docs) >= top_k:
                    break
                if d not in filtered_docs:
                    filtered_docs.append(d)
    except Exception as e:
        logger.warning(
            "Stage 1 Fast Batch Rerank skipped (%s). Using raw candidate set.", e
        )
        return docs

    return filtered_docs if filtered_docs else docs


class SearchPipeline:
    """Deep search pipeline consolidating vector search, multi-hop agentic retrieval, reranking, and Graph RAG."""

    def __init__(
        self,
        milvus_repo: MilvusRepository,
        neo4j_repo: Neo4jRepository,
        ai_client: Optional[AIGatewayClient] = None,
        sampler_hook: Optional[Callable[[str, list[dict], str], Any]] = None,
    ):
        self.milvus = milvus_repo
        self.neo4j = neo4j_repo
        self.ai_client = ai_client or get_ai_gateway_client()
        self._sampler_hook = sampler_hook
        driver = getattr(neo4j_repo, "driver", None) or getattr(neo4j_repo, "_driver", None)
        self.graph_timeline = AdvancedGraphRAG(driver, ai_client=self.ai_client) if driver is not None else None

    async def get_legal_timeline(self, doc_number_or_id: str) -> list[dict]:
        """Fetch legal timeline for a document node via Graph RAG."""
        if self.graph_timeline:
            return await self.graph_timeline.get_legal_timeline(doc_number_or_id)
        return []

    async def search(
        self,
        query: str,
        limit: int = 10,
        use_reranker: bool = True,
        doc_type: Optional[str] = None,
        authority: Optional[str] = None,
        year: Optional[int] = None,
        doc_number: Optional[str] = None,
        use_hyde: bool = False,
        use_agentic: Optional[bool] = None,
        use_cache: bool = True,
        session_id: Optional[str] = None,
        tracer: Optional[QueryTracer] = None,
    ) -> Dict[str, Any]:
        """Single deep search interface executing full search pipeline."""
        ctx = SearchContext(
            raw_query=query,
            limit=limit,
            use_reranker=use_reranker,
            doc_type=doc_type,
            authority=authority,
            year=year,
            doc_number=doc_number,
            use_hyde=use_hyde,
            use_agentic=use_agentic,
            use_cache=use_cache,
            session_id=session_id,
            tracer=tracer,
            ai_client=self.ai_client,
        )
        return await self.execute(ctx)

    async def execute(self, ctx: SearchContext) -> Dict[str, Any]:
        if ctx.ai_client is None:
            ctx.ai_client = self.ai_client
        if ctx.tracer is None:
            ctx.tracer = QueryTracer(ctx.raw_query, session_id=ctx.session_id)

        with SEARCH_LATENCY.time():
            # Step 1: Intent & Cache Check
            if await self._stage_intent_and_cache(ctx):
                return {
                    "results": ctx.top_results,
                    "cached": True,
                    "trace": ctx.tracer.finalize(cache_hit=True, result_count=len(ctx.top_results)),
                    "query_intent": ctx.intent.value if ctx.intent else "GENERAL",
                    "hops": ctx.hops,
                    "sub_queries": ctx.sub_queries,
                    "reasoning": ctx.reasoning,
                }

            is_agentic = (ctx.use_agentic is True) or (ctx.use_agentic is None and ctx.intent == QueryIntent.COMPLEX)

            if is_agentic:
                await self._stage_agentic_multihop(ctx)
            else:
                # Step 2: Query Rewrite & HyDE
                await self._stage_rewrite_and_hyde(ctx)

                # Step 3: Hybrid Search
                await self._stage_hybrid_search(ctx)

            # Step 4: Rerank & Score
            await self._stage_rerank_and_score(ctx)

            # Step 5: Graph RAG & Timeline Enrichment
            await self._stage_graph_enrichment(ctx)

            # Step 6: Search Grounding Fallback Check (1,500 RPD Free Quota Pool)
            max_score = max((r.get("score", 0.0) for r in ctx.top_results), default=0.0)
            if not ctx.top_results or max_score < 0.65:
                ctx.search_grounding_triggered = True
                logger.info(
                    f"[SEARCH-GROUNDING] Low RAG confidence ({max_score:.2f} < 0.65). "
                    f"Triggered 1,500 RPD Search Grounding Fallback for query: {ctx.raw_query}"
                )

            # Cache final results
            if ctx.use_cache and ctx.top_results:
                _semantic_cache.get().set(ctx.search_query or ctx.raw_query, ctx.query_vector_np, ctx.top_results, filter_key=ctx.cache_filter_key)

            # HITL Sampling
            if self._sampler_hook:
                try:
                    self._sampler_hook(ctx.raw_query, ctx.top_results, ctx.session_id or "")
                except Exception as _hitl_err:
                    logger.debug(f"Sampler hook failed: {_hitl_err}")

            trace_data = ctx.tracer.finalize(result_count=len(ctx.top_results))
            return {
                "results": ctx.top_results,
                "trace": trace_data,
                "query_intent": ctx.intent.value if ctx.intent else "GENERAL",
                "search_grounding_triggered": ctx.search_grounding_triggered,
                "hops": ctx.hops,
                "sub_queries": ctx.sub_queries,
                "reasoning": ctx.reasoning,
            }

    async def _stage_intent_and_cache(self, ctx: SearchContext) -> bool:
        intent_result = classify_query(ctx.raw_query)
        ctx.intent = intent_result.intent
        QUERY_INTENT_COUNTER.labels(intent=ctx.intent.value).inc()

        if ctx.intent == QueryIntent.EXACT and not ctx.use_hyde:
            ctx.use_hyde = False
        if ctx.intent == QueryIntent.COMPLEX:
            ctx.use_hyde = True

        filters = []
        if ctx.doc_type:
            filters.append(f'doc_type == "{_sanitize_filter_value(ctx.doc_type)}"')
        if ctx.authority:
            filters.append(f'authority == "{_sanitize_filter_value(ctx.authority)}"')
        if ctx.year:
            filters.append(f'doc_date LIKE "{int(ctx.year)}%"')
        if ctx.doc_number:
            filters.append(f'doc_number == "{_sanitize_filter_value(ctx.doc_number)}"')
        ctx.filter_expr = " and ".join(filters) if filters else None
        ctx.cache_filter_key = ctx.filter_expr or ""

        # Initial embedding for cache lookup
        ctx.tracer.start_step("embed")
        loop = asyncio.get_running_loop()
        model = get_embedding_model()
        emb = await loop.run_in_executor(None, model.embed_query, ctx.raw_query)
        ctx.query_vector_np = np.array(emb["dense"])
        ctx.query_vector = emb["dense"]
        ctx.sparse_query = emb.get("sparse", {})
        ctx.tracer.end_step(model="bge-m3")

        if ctx.use_cache:
            ctx.tracer.start_step("cache_check")
            cached = _semantic_cache.get().get(ctx.raw_query, ctx.query_vector_np, filter_key=ctx.cache_filter_key)
            if cached:
                SEMANTIC_CACHE_HITS.inc()
                ctx.tracer.end_step(result="hit")
                ctx.top_results = cached
                ctx.cached_hit = True
                return True
            ctx.tracer.end_step(result="miss")

        return False

    async def _stage_rewrite_and_hyde(self, ctx: SearchContext):
        ctx.tracer.start_step("rewrite")
        rewritten = await rewrite_query(ctx.raw_query, ai_client=ctx.ai_client)
        ctx.search_query = rewritten
        ctx.tracer.end_step(original=ctx.raw_query[:100], rewritten=rewritten[:100])

        if ctx.use_hyde:
            ctx.tracer.start_step("hyde")
            gen = HyDEGenerator(ai_client=ctx.ai_client)
            hyde_doc = await gen.generate_hypothetical_answer(rewritten)
            if hyde_doc:
                ctx.search_query = f"{rewritten}\n{hyde_doc}"
            ctx.tracer.end_step(generated=bool(hyde_doc))

        if ctx.search_query != ctx.raw_query:
            loop = asyncio.get_running_loop()
            model = get_embedding_model()
            emb = await loop.run_in_executor(None, model.embed_query, ctx.search_query)
            ctx.query_vector_np = np.array(emb["dense"])
            ctx.query_vector = emb["dense"]
            ctx.sparse_query = emb.get("sparse", {})

    async def _embed_query(self, query_text: str) -> tuple[np.ndarray, list, dict]:
        loop = asyncio.get_running_loop()
        model = get_embedding_model()
        emb = await loop.run_in_executor(None, model.embed_query, query_text)
        return np.array(emb["dense"]), emb["dense"], emb.get("sparse", {})

    async def _retrieve_raw_hits(self, dense_vec: list, sparse_vec: dict, limit: int, expr: Optional[str] = None) -> list:
        results = await self.milvus.hybrid_search(dense_vec, sparse_vec, limit=limit, expr=expr)
        HYBRID_RECALL_10.inc()
        return results[0] if results and results[0] else []

    async def _stage_hybrid_search(self, ctx: SearchContext):
        ctx.tracer.start_step("retrieve")
        initial_limit = min(ctx.limit * 10 if ctx.use_reranker else ctx.limit, 100)
        ctx.raw_hits = await self._retrieve_raw_hits(ctx.query_vector, ctx.sparse_query, limit=initial_limit, expr=ctx.filter_expr)
        ctx.tracer.end_step(source="milvus", hits=len(ctx.raw_hits))

    async def _stage_agentic_multihop(self, ctx: SearchContext):
        """Execute multi-hop plan-retrieve-reflect loop inside SearchPipeline."""
        ctx.tracer.start_step("agentic_plan")
        try:
            plan = await ctx.ai_client.extract_json(
                _AGENTIC_PLAN_PROMPT.format(query=ctx.raw_query),
                model="gemini-3.5-flash-lite",
            )
            sub_queries = plan.get("sub_queries", [ctx.raw_query])
            if not isinstance(sub_queries, list) or not sub_queries:
                sub_queries = [ctx.raw_query]
            ctx.sub_queries = sub_queries[:3]
            ctx.reasoning = plan.get("reasoning", "")
        except Exception as e:
            logger.warning(f"Agentic plan generation failed: {e}")
            ctx.sub_queries = [ctx.raw_query]
        ctx.tracer.end_step(sub_queries=ctx.sub_queries, reasoning=ctx.reasoning)

        # Hop 1: Parallel sub-query retrieval
        ctx.tracer.start_step("agentic_retrieve_hop1")
        ctx.hops = 1
        initial_limit = min(ctx.limit * 5 if ctx.use_reranker else ctx.limit, 40)

        async def _fetch_for_sub_query(sub_q: str):
            _, dense_vec, sparse_vec = await self._embed_query(sub_q)
            return await self._retrieve_raw_hits(dense_vec, sparse_vec, limit=initial_limit, expr=ctx.filter_expr)

        tasks = [_fetch_for_sub_query(sq) for sq in ctx.sub_queries]
        hop1_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_hits = []
        seen_texts = set()
        for res in hop1_results:
            if isinstance(res, list):
                for hit in res:
                    txt = _get_hit_entity(hit).get("text", "")[:200]
                    if txt and txt not in seen_texts:
                        seen_texts.add(txt)
                        all_hits.append(hit)

        ctx.raw_hits = all_hits
        ctx.tracer.end_step(hop=1, unique_hits=len(all_hits))

        # Hop 2: Reflection & Follow-up (if necessary)
        if all_hits and len(all_hits) > 0:
            ctx.tracer.start_step("agentic_evaluate")
            preview_chunks = []
            for hit in all_hits[:8]:
                ent = _get_hit_entity(hit)
                doc_num = ent.get("doc_number", "")
                txt = ent.get("text", "")[:300]
                preview_chunks.append(f"[{doc_num}] {txt}")
            context_preview = "\n".join(preview_chunks)

            try:
                eval_res = await ctx.ai_client.extract_json(
                    _AGENTIC_EVAL_PROMPT.format(query=ctx.raw_query, context=context_preview),
                    model="gemini-3.5-flash-lite",
                )
                ctx.is_sufficient = eval_res.get("is_sufficient", True)
                ctx.confidence = float(eval_res.get("confidence", 1.0))
                follow_up = eval_res.get("follow_up_query", "")
            except Exception as e:
                logger.warning(f"Agentic evaluation failed: {e}")
                ctx.is_sufficient = True
                ctx.confidence = 1.0
                follow_up = ""

            ctx.tracer.end_step(is_sufficient=ctx.is_sufficient, confidence=ctx.confidence)

            if not ctx.is_sufficient and ctx.confidence < 0.70 and follow_up and follow_up != ctx.raw_query:
                ctx.hops = 2
                ctx.tracer.start_step("agentic_retrieve_hop2")
                try:
                    _, dense_vec, sparse_vec = await self._embed_query(follow_up)
                    hop2_hits = await self._retrieve_raw_hits(dense_vec, sparse_vec, limit=initial_limit, expr=ctx.filter_expr)
                    for hit in hop2_hits:
                        txt = _get_hit_entity(hit).get("text", "")[:200]
                        if txt and txt not in seen_texts:
                            seen_texts.add(txt)
                            all_hits.append(hit)
                    ctx.sub_queries.append(follow_up)
                    ctx.raw_hits = all_hits
                    ctx.tracer.end_step(hop=2, added_hits=len(hop2_hits))
                except Exception as e:
                    logger.warning(f"Hop 2 retrieval failed: {e}")
                    ctx.tracer.end_step(hop=2, error=str(e))

    async def _stage_rerank_and_score(self, ctx: SearchContext):
        if not ctx.raw_hits:
            return

        if ctx.use_reranker:
            ctx.tracer.start_step("rerank")
            docs = [_get_hit_entity(hit).get("text", "") for hit in ctx.raw_hits]

            # Stage 1: Fast batch filtering using Flash Lite when candidate set is exceptionally large
            if len(docs) > 60:
                candidate_docs = await stage1_fast_batch_rerank(
                    ctx.raw_query, docs, top_k=30, ai_client=ctx.ai_client
                )
            else:
                candidate_docs = docs

            # Stage 2: Deep Local Reranking (CrossEncoder)
            reranker = get_reranker()
            reranked = await reranker.rerank(ctx.raw_query, candidate_docs, top_k=max(ctx.limit * 2, 10))

            hit_map = {}
            for hit in ctx.raw_hits:
                t = _get_hit_entity(hit).get("text", "")
                if t not in hit_map:
                    hit_map[t] = hit

            settings = get_settings()
            for doc_text, score in reranked:
                hit = hit_map.get(doc_text)
                if hit is None:
                    continue
                ent = _get_hit_entity(hit)
                table_boost = settings.TABLE_BOOST if ent.get("is_table", False) else 0.0
                status = ent.get("validity_status", "ACTIVE")
                validity_boost = (
                    settings.VALIDITY_BOOST_ACTIVE if status == "ACTIVE"
                    else (settings.VALIDITY_PENALTY_OUTDATED if status == "OUTDATED" else 0.0)
                )
                hybrid_score = (float(score) * settings.RERANK_WEIGHT) + (_get_hit_score(hit) * settings.MILVUS_WEIGHT) + table_boost + validity_boost
                ctx.top_results.append(_build_result_item(ent, doc_text, hybrid_score))

            ctx.top_results.sort(key=lambda x: x["score"], reverse=True)
            ctx.top_results = ctx.top_results[:ctx.limit]
            ctx.tracer.end_step(input_count=len(docs), output_count=len(ctx.top_results))
        else:
            for hit in ctx.raw_hits:
                ent = _get_hit_entity(hit)
                ctx.top_results.append(_build_result_item(ent, ent.get("text", ""), _get_hit_score(hit)))

    async def _stage_graph_enrichment(self, ctx: SearchContext):
        if not ctx.top_results:
            return

        # Graph Status Injection
        unique_sources = list(set(r["source"] for r in ctx.top_results if r.get("source")))
        status_map = await self.neo4j.find_document_status(unique_sources)
        for r in ctx.top_results:
            status = status_map.get(r["source"], "ACTIVE")
            if status == "OUTDATED":
                r["text"] = f"[WARNING: THIS DOCUMENT IS OUTDATED/REPLACED] {r['text']}"
            r["status"] = status

        # Parent-Child context expansion
        parent_ids = list(set(r["parent_id"] for r in ctx.top_results if r.get("chunk_type") == "child" and r.get("parent_id")))
        if parent_ids:
            parent_results = await self.milvus.get_parent_chunks(parent_ids)
            parent_map = {p["parent_id"]: p["text"] for p in parent_results}
            for r in ctx.top_results:
                if r.get("chunk_type") == "child" and r["parent_id"] in parent_map:
                    r["child_text"] = r["text"]
                    r["text"] = parent_map[r["parent_id"]]

        # Graph RAG Timeline Traversal
        ctx.tracer.start_step("graph_timeline")
        timeline_count = 0
        if self.graph_timeline is not None:
            try:
                for r in ctx.top_results:
                    if timeline_count >= 2:
                        break
                    doc_num = r.get("doc_number")
                    if doc_num:
                        timeline = await self.graph_timeline.get_legal_timeline(doc_num)
                        if timeline and len(timeline) > 1:
                            TIMELINE_GEN_COUNT.inc()
                            GRAPH_TIMELINE_HOPS.observe(len(timeline))
                            summary = await self.graph_timeline.generate_timeline_summary(timeline, ctx.raw_query)
                            r["legal_timeline_summary"] = summary
                            r["text"] = f"[LEGAL TIMELINE]: {summary}\n\n[CONTENT]: {r['text']}"
                            timeline_count += 1
            except Exception as e:
                logger.warning(f"Graph timeline enrichment failed gracefully: {e}")
        ctx.tracer.end_step(timelines_generated=timeline_count)


class InMemorySearchPipeline(SearchPipeline):
    """In-memory test adapter for SearchPipeline offline testing."""

    def __init__(self, custom_results: Optional[List[Dict[str, Any]]] = None, ai_client: Optional[AIGatewayClient] = None):
        self.custom_results = custom_results or [
            {
                "text": "Điều 1. Phạm vi điều chỉnh",
                "source": "01_2024_TT-BXD.pdf",
                "page": 1,
                "summary": "Quy định chung",
                "doc_date": "2024-01-01",
                "doc_type": "TT",
                "authority": "BXD",
                "doc_number": "01/2024/TT-BXD",
                "is_table": False,
                "chunk_type": "parent",
                "parent_id": "VBPL/01_2024_TT-BXD",
                "bbox": [0, 0, 1000, 1000],
                "validity_status": "ACTIVE",
                "project_code": "GENERIC",
                "discipline": "UNKNOWN",
                "hierarchy_path": "",
                "doc_status": "ACTIVE",
                "revision": 0,
                "score": 0.95,
            }
        ]
        self.ai_client = ai_client
        self.call_history: List[Dict[str, Any]] = []

    async def search(self, query: str, limit: int = 10, use_agentic: Optional[bool] = None, **kwargs) -> Dict[str, Any]:
        self.call_history.append({"query": query, "limit": limit, "use_agentic": use_agentic, "kwargs": kwargs})
        results = self.custom_results[:limit]
        return {
            "results": results,
            "cached": False,
            "trace": {"query": query, "steps": [], "total_time": 0.01},
            "query_intent": "COMPLEX" if use_agentic else "GENERAL",
            "search_grounding_triggered": False,
            "hops": 2 if use_agentic else 1,
            "sub_queries": [query, f"{query} chi tiết"] if use_agentic else [query],
            "reasoning": "Mock in-memory agentic plan" if use_agentic else "",
        }

    async def execute(self, ctx: SearchContext) -> Dict[str, Any]:
        return await self.search(ctx.raw_query, limit=ctx.limit, use_agentic=ctx.use_agentic)

    async def get_legal_timeline(self, doc_number_or_id: str) -> list[dict]:
        return [
            {"id": doc_number_or_id, "title": f"Document {doc_number_or_id}", "date": "2024-01-01", "relation_to_next": "REPLACES"},
            {"id": f"{doc_number_or_id}_pred", "title": "Predecessor Document", "date": "2020-01-01", "relation_to_next": None},
        ]
