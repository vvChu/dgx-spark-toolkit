import asyncio
import json
import logging
import re
import numpy as np

from core.config import get_settings
from core.singleton import LazyInit
from repositories.neo4j_repo import Neo4jRepository
from repositories.milvus_repo import MilvusRepository
from retrieval.hyde import HyDEGenerator
from retrieval.reranker import get_reranker
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from retrieval.semantic_cache import SemanticCache
from retrieval.query_rewriter import rewrite_query
from prometheus_client import Summary, Counter, Histogram, Gauge

# Prometheus Metrics
SEARCH_LATENCY = Histogram('rag_search_latency_seconds', 'Latency of search requests', buckets=(1, 2, 5, 10, 15, 20, 30, 60))
SEMANTIC_CACHE_HITS = Counter('rag_semantic_cache_hits_total', 'Total semantic cache hits')
HYBRID_RECALL_10 = Counter('rag_hybrid_recall_top10_total', 'Total hybrid searches')
GRAPH_TIMELINE_HOPS = Histogram('rag_graph_timeline_hops_total', 'Number of hops in timeline traversal', buckets=(1, 2, 3, 5, 10))
TIMELINE_GEN_COUNT = Counter('rag_timeline_generated_total', 'Total legal timelines generated')
SPARSE_HIT_RATIO = Gauge('rag_sparse_hit_ratio', 'Ratio of sparse hits in hybrid search')

logger = logging.getLogger(__name__)

# Characters that must not appear unescaped inside Milvus filter string literals
_FILTER_UNSAFE = re.compile(r'["\\\x00-\x1f]')

def _sanitize_filter_value(value: str) -> str:
    """Escape or strip characters that could break a Milvus filter expression."""
    return _FILTER_UNSAFE.sub('', str(value))


_BBOX_FALLBACK = [0, 0, 1000, 1000]


def _safe_json_loads(value: str) -> list:
    """Parse a JSON bbox string, returning a safe fallback on malformed input."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Malformed bbox value, using fallback: {value!r}")
        return _BBOX_FALLBACK


# Lazy-initialized module singletons — deferred to avoid import-time get_settings() calls
_semantic_cache = LazyInit(lambda: SemanticCache(
    threshold=get_settings().SEMANTIC_CACHE_THRESHOLD,
    ttl_seconds=get_settings().SEMANTIC_CACHE_TTL_SECONDS,
))
_hyde_gen = LazyInit(lambda: HyDEGenerator())

from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding

_embedding_model = LazyInit(lambda: BGE_M3_HybridEmbedding())


def get_embedding_model() -> BGE_M3_HybridEmbedding:
    """Return the singleton embedding model, initializing it thread-safely on first call."""
    return _embedding_model.get()


def _build_result_item(entity: dict, text: str, score: float) -> dict:
    """Build a standardized result dict from a Milvus entity — single source of truth."""
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


class RetrievalService:
    def __init__(self, milvus_repo: MilvusRepository, neo4j_repo: Neo4jRepository):
        self.milvus = milvus_repo
        self.neo4j = neo4j_repo
        self.graph_timeline = AdvancedGraphRAG(neo4j_repo.driver)

    async def search(self, query: str, limit: int = 10, use_reranker: bool = True,
                     doc_type: str = None, authority: str = None, year: int = None,
                     doc_number: str = None, use_hyde: bool = False, use_cache: bool = True):
        """End-to-end search with latency measurement."""
        with SEARCH_LATENCY.time():
            return await self._search_internal(
                query=query, limit=limit, use_reranker=use_reranker,
                doc_type=doc_type, authority=authority, year=year,
                doc_number=doc_number, use_hyde=use_hyde, use_cache=use_cache
            )

    async def _search_internal(self, query: str, limit: int = 10, use_reranker: bool = True,
                               doc_type: str = None, authority: str = None, year: int = None,
                               doc_number: str = None, use_hyde: bool = False, use_cache: bool = True):

        # Step 0: Fast Exact Semantic Cache
        # embed_query is synchronous CPU/GPU work — run in executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        model = get_embedding_model()
        query_embeddings = await loop.run_in_executor(None, model.embed_query, query)
        q_vector_np = np.array(query_embeddings["dense"])
        
        if use_cache:
            cached_results = _semantic_cache.get().get(query, q_vector_np)
            if cached_results:
                SEMANTIC_CACHE_HITS.inc()
                return {"results": cached_results, "cached": True}

        # Step 1: Query Rewriting
        rewritten_query = await rewrite_query(query)
        search_query = rewritten_query
        
        # Step 2: HyDE
        if use_hyde:
            hyde_doc = await _hyde_gen.get().generate_hypothetical_answer(rewritten_query)
            if hyde_doc:
                search_query = f"{rewritten_query}\n{hyde_doc}"

        # embed_query now returns a dictionary containing 'dense' and 'sparse'
        query_embeddings = await loop.run_in_executor(None, model.embed_query, search_query)
        query_vector_np = np.array(query_embeddings["dense"])
        query_vector = query_embeddings["dense"]
        sparse_query = query_embeddings["sparse"]

        if use_cache:
            cached_results = _semantic_cache.get().get(search_query, query_vector_np)
            if cached_results:
                return {"results": cached_results, "cached": True}

        # Build filter expression — sanitize all user-supplied values to prevent injection
        filters = []
        if doc_type:
            filters.append(f'doc_type == "{_sanitize_filter_value(doc_type)}"')
        if authority:
            filters.append(f'authority == "{_sanitize_filter_value(authority)}"')
        if year:
            filters.append(f'doc_date LIKE "{int(year)}%"')
        if doc_number:
            filters.append(f'doc_number == "{_sanitize_filter_value(doc_number)}"')
        expr = " and ".join(filters) if filters else None

        # Hybrid Search
        initial_limit = min(limit * 10 if use_reranker else limit, 100)
        results = await self.milvus.hybrid_search(query_vector, sparse_query, limit=initial_limit, expr=expr)
        HYBRID_RECALL_10.inc()
        
        top_results = []
        if results:
            raw_hits = results[0]
            if use_reranker:
                docs = [hit.entity.get("text") for hit in raw_hits]
                reranker = get_reranker()
                reranked = await reranker.rerank(query, docs, top_k=limit)
                
                # Build hit_map; keep first occurrence if text is duplicated in results
                hit_map: dict = {}
                for hit in raw_hits:
                    t = hit.entity.get("text")
                    if t not in hit_map:
                        hit_map[t] = hit

                for doc_text, score in reranked:
                    hit = hit_map.get(doc_text)
                    if hit is None:
                        # Reranker returned a text not in hit_map (shouldn't happen, but guard it)
                        logger.warning(f"Reranker returned unknown doc_text, skipping.")
                        continue
                    ent = hit.entity
                    milvus_score = hit.score
                    table_boost = 0.2 if ent.get("is_table", False) else 0.0
                    
                    # Absolute Quality: Boost ACTIVE documents and penalize OUTDATED ones
                    status = ent.get("validity_status", "ACTIVE")
                    validity_boost = 0.15 if status == "ACTIVE" else (-0.3 if status == "OUTDATED" else 0.0)
                    
                    hybrid_score = (float(score) * 0.8) + (float(milvus_score) * 0.2) + table_boost + validity_boost
                    top_results.append(_build_result_item(ent, doc_text, hybrid_score))
                top_results.sort(key=lambda x: x["score"], reverse=True)
            else:
                for hit in raw_hits:
                    ent = hit.entity
                    top_results.append(_build_result_item(ent, ent.get("text"), float(hit.score)))

        if top_results:
            # Inject Graph Status — fetch for all unique sources so every result gets accurate status
            unique_sources = list(set(r["source"] for r in top_results if r.get("source")))
            status_map = await self.neo4j.find_document_status(unique_sources)
            for r in top_results:
                status = status_map.get(r["source"], "ACTIVE")
                if status == "OUTDATED":
                    r["text"] = f"[WARNING: THIS DOCUMENT IS OUTDATED/REPLACED] {r['text']}"
                r["status"] = status

            # Parent-Child context expansion
            parent_ids = list(set(r["parent_id"] for r in top_results if r.get("chunk_type") == "child" and r.get("parent_id")))
            if parent_ids:
                parent_results = await self.milvus.get_parent_chunks(parent_ids)
                parent_map = {p["parent_id"]: p["text"] for p in parent_results}
                for r in top_results:
                    if r.get("chunk_type") == "child" and r["parent_id"] in parent_map:
                        r["child_text"] = r["text"]
                        r["text"] = parent_map[r["parent_id"]]

            # Mức độ 3: Advanced Graph RAG - Timeline Traversal
            # Chỉ lấy timeline cho top 2 kết quả phù hợp nhất để tối ưu latency
            for r in top_results[:2]:
                doc_num = r.get("doc_number")
                if doc_num:
                    timeline = await self.graph_timeline.get_legal_timeline(doc_num)
                    if timeline and len(timeline) > 1:
                        TIMELINE_GEN_COUNT.inc()
                        GRAPH_TIMELINE_HOPS.observe(len(timeline))
                        summary = await self.graph_timeline.generate_timeline_summary(timeline, query)
                        r["legal_timeline_summary"] = summary
                        r["text"] = f"[LEGAL TIMELINE]: {summary}\n\n[CONTENT]: {r['text']}"

        if use_cache and top_results:
            _semantic_cache.get().set(search_query, query_vector_np, top_results)
            
        return {"results": top_results}
