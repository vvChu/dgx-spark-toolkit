"""Deep SearchPipeline module for hybrid vector search, reranking, and Graph RAG enrichment."""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np
from prometheus_client import Summary, Counter, Histogram, Gauge

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
    use_cache: bool = True
    session_id: Optional[str] = None
    tracer: Optional[QueryTracer] = None

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


class SearchPipeline:
    """Deep search pipeline consolidating vector search, reranking, and Graph RAG."""

    def __init__(self, milvus_repo: MilvusRepository, neo4j_repo: Neo4jRepository):
        self.milvus = milvus_repo
        self.neo4j = neo4j_repo
        self.graph_timeline = AdvancedGraphRAG(neo4j_repo.driver)

    async def execute(self, ctx: SearchContext) -> Dict[str, Any]:
        if ctx.tracer is None:
            ctx.tracer = QueryTracer(ctx.raw_query, session_id=ctx.session_id)

        with SEARCH_LATENCY.time():
            # Step 1: Intent & Cache Check
            if await self._stage_intent_and_cache(ctx):
                return {
                    "results": ctx.top_results,
                    "cached": True,
                    "trace": ctx.tracer.finalize(cache_hit=True, result_count=len(ctx.top_results)),
                    "query_intent": ctx.intent.value if ctx.intent else "GENERAL"
                }

            # Step 2: Query Rewrite & HyDE
            await self._stage_rewrite_and_hyde(ctx)

            # Step 3: Hybrid Search
            await self._stage_hybrid_search(ctx)

            # Step 4: Rerank & Score
            await self._stage_rerank_and_score(ctx)

            # Step 5: Graph RAG & Timeline Enrichment
            await self._stage_graph_enrichment(ctx)

            # Cache final results
            if ctx.use_cache and ctx.top_results:
                _semantic_cache.get().set(ctx.search_query, ctx.query_vector_np, ctx.top_results, filter_key=ctx.cache_filter_key)

            # HITL Sampling
            try:
                from services.hitl_service import get_hitl_service
                get_hitl_service().maybe_sample(ctx.raw_query, ctx.top_results, session_id=ctx.session_id or "")
            except Exception as _hitl_err:
                logger.debug(f"HITL sampling skipped: {_hitl_err}")

            trace_data = ctx.tracer.finalize(result_count=len(ctx.top_results))
            return {
                "results": ctx.top_results,
                "trace": trace_data,
                "query_intent": ctx.intent.value if ctx.intent else "GENERAL"
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
        rewritten = await rewrite_query(ctx.raw_query)
        ctx.search_query = rewritten
        ctx.tracer.end_step(original=ctx.raw_query[:100], rewritten=rewritten[:100])

        if ctx.use_hyde:
            ctx.tracer.start_step("hyde")
            hyde_doc = await _hyde_gen.get().generate_hypothetical_answer(rewritten)
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

    async def _stage_hybrid_search(self, ctx: SearchContext):
        ctx.tracer.start_step("retrieve")
        initial_limit = min(ctx.limit * 10 if ctx.use_reranker else ctx.limit, 100)
        results = await self.milvus.hybrid_search(ctx.query_vector, ctx.sparse_query, limit=initial_limit, expr=ctx.filter_expr)
        HYBRID_RECALL_10.inc()
        ctx.raw_hits = results[0] if results and results[0] else []
        ctx.tracer.end_step(source="milvus", hits=len(ctx.raw_hits))

    async def _stage_rerank_and_score(self, ctx: SearchContext):
        if not ctx.raw_hits:
            return

        if ctx.use_reranker:
            ctx.tracer.start_step("rerank")
            docs = [hit.entity.get("text") for hit in ctx.raw_hits]
            reranker = get_reranker()
            reranked = await reranker.rerank(ctx.raw_query, docs, top_k=ctx.limit)

            hit_map = {}
            for hit in ctx.raw_hits:
                t = hit.entity.get("text")
                if t not in hit_map:
                    hit_map[t] = hit

            settings = get_settings()
            for doc_text, score in reranked:
                hit = hit_map.get(doc_text)
                if hit is None:
                    continue
                ent = hit.entity
                table_boost = settings.TABLE_BOOST if ent.get("is_table", False) else 0.0
                status = ent.get("validity_status", "ACTIVE")
                validity_boost = (
                    settings.VALIDITY_BOOST_ACTIVE if status == "ACTIVE"
                    else (settings.VALIDITY_PENALTY_OUTDATED if status == "OUTDATED" else 0.0)
                )
                hybrid_score = (float(score) * settings.RERANK_WEIGHT) + (float(hit.score) * settings.MILVUS_WEIGHT) + table_boost + validity_boost
                ctx.top_results.append(_build_result_item(ent, doc_text, hybrid_score))

            ctx.top_results.sort(key=lambda x: x["score"], reverse=True)
            ctx.tracer.end_step(input_count=len(docs), output_count=len(ctx.top_results))
        else:
            for hit in ctx.raw_hits:
                ent = hit.entity
                ctx.top_results.append(_build_result_item(ent, ent.get("text"), float(hit.score)))

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
        for r in ctx.top_results[:2]:
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
        ctx.tracer.end_step(timelines_generated=timeline_count)
