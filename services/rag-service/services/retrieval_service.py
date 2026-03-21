import asyncio
import json
import logging
import re
import time
import threading
import httpx
import numpy as np

from core.config import get_settings
from repositories.neo4j_repo import Neo4jRepository
from repositories.milvus_repo import MilvusRepository
from retrieval.hyde import HyDEGenerator
from retrieval.reranker import get_reranker
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
import torch
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


class SemanticCache:
    """In-memory semantic cache with TTL and LRU eviction."""

    def __init__(self, threshold: float = 0.92, max_size: int = 1000, ttl_seconds: float = 3600.0):
        self.cache: dict = {}
        self.threshold = threshold
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def _is_expired(self, entry: dict) -> bool:
        return (time.monotonic() - entry["timestamp"]) > self.ttl_seconds

    def get(self, query: str, query_embedding: np.ndarray):
        best_match = None
        highest_score = -1.0
        with self._lock:
            for q_text, data in list(self.cache.items()):
                if self._is_expired(data):
                    del self.cache[q_text]
                    continue
                norm_q = np.linalg.norm(query_embedding)
                norm_d = np.linalg.norm(data["embedding"])
                if norm_q == 0 or norm_d == 0:
                    continue
                score = np.dot(query_embedding, data["embedding"]) / (norm_q * norm_d)
                if score > highest_score:
                    highest_score = score
                    best_match = q_text
            if highest_score >= self.threshold and best_match:
                # LRU: refresh timestamp on hit
                self.cache[best_match]["timestamp"] = time.monotonic()
                logger.info(f"Semantic cache hit! Similarity: {highest_score:.4f}")
                return self.cache[best_match]["results"]
        return None

    def set(self, query: str, query_embedding: np.ndarray, results):
        with self._lock:
            if len(self.cache) >= self.max_size:
                # Evict the oldest entry (smallest timestamp)
                oldest = min(self.cache, key=lambda k: self.cache[k]["timestamp"])
                del self.cache[oldest]
            self.cache[query] = {
                "embedding": query_embedding,
                "results": results,
                "timestamp": time.monotonic(),
            }


# Lazy-initialized module singletons — deferred to avoid import-time get_settings() calls
_semantic_cache = None
_hyde_gen = None


def _get_semantic_cache() -> SemanticCache:
    global _semantic_cache
    if _semantic_cache is None:
        s = get_settings()
        _semantic_cache = SemanticCache(
            threshold=s.SEMANTIC_CACHE_THRESHOLD,
            ttl_seconds=s.SEMANTIC_CACHE_TTL_SECONDS,
        )
    return _semantic_cache


def _get_hyde_gen() -> HyDEGenerator:
    global _hyde_gen
    if _hyde_gen is None:
        _hyde_gen = HyDEGenerator()
    return _hyde_gen

from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding

_embedding_model = None
_embedding_model_lock = threading.Lock()


def get_embedding_model() -> BGE_M3_HybridEmbedding:
    """Return the singleton embedding model, initializing it thread-safely on first call."""
    global _embedding_model
    if _embedding_model is None:
        with _embedding_model_lock:
            if _embedding_model is None:  # double-checked locking
                _embedding_model = BGE_M3_HybridEmbedding()
    return _embedding_model


# Single in-memory cache for query rewrites (bounded, FIFO)
# asyncio.Lock is created lazily inside the first coroutine call to avoid
# binding to the wrong event loop when the module is imported before the loop starts.
_query_rewrite_cache: dict = {}
_query_rewrite_lock: asyncio.Lock | None = None


def _get_rewrite_lock() -> asyncio.Lock:
    global _query_rewrite_lock
    if _query_rewrite_lock is None:
        _query_rewrite_lock = asyncio.Lock()
    return _query_rewrite_lock

# Module-level shared AsyncClient — avoids creating a new TCP connection per rewrite call
_rewrite_http_client: httpx.AsyncClient | None = None
_rewrite_http_client_thread_lock = threading.Lock()


def _get_rewrite_http_client() -> httpx.AsyncClient:
    global _rewrite_http_client
    if _rewrite_http_client is None:
        with _rewrite_http_client_thread_lock:
            if _rewrite_http_client is None:
                _rewrite_http_client = httpx.AsyncClient(timeout=30.0)
    return _rewrite_http_client


async def rewrite_query(original_query: str) -> str:
    """Standardize legal terms and expand acronyms using LLM."""
    lock = _get_rewrite_lock()
    async with lock:
        if original_query in _query_rewrite_cache:
            return _query_rewrite_cache[original_query]

    try:
        settings = get_settings()
        from core.prompts import QUERY_REWRITE_PROMPT
        prompt = QUERY_REWRITE_PROMPT.format(original_query=original_query)
        payload = {
            "model": settings.VLLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 100
        }
        client = _get_rewrite_http_client()
        resp = await client.post(
            f"{settings.VLLM_API_BASE}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"},
        )
        if resp.status_code == 200:
            rewritten = resp.json()["choices"][0]["message"]["content"].strip().strip('"')
            async with lock:
                if len(_query_rewrite_cache) >= 1000:
                    _query_rewrite_cache.pop(next(iter(_query_rewrite_cache)))
                _query_rewrite_cache[original_query] = rewritten
            return rewritten
    except Exception as e:
        logger.warning(f"Query rewriting failed: {e}")
    return original_query

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
            cached_results = _get_semantic_cache().get(query, q_vector_np)
            if cached_results:
                SEMANTIC_CACHE_HITS.inc()
                return {"results": cached_results, "cached": True}

        # Step 1: Query Rewriting
        rewritten_query = await rewrite_query(query)
        search_query = rewritten_query
        
        # Step 2: HyDE
        if use_hyde:
            hyde_doc = await _get_hyde_gen().generate_hypothetical_answer(rewritten_query)
            if hyde_doc:
                search_query = f"{rewritten_query}\n{hyde_doc}"

        # embed_query now returns a dictionary containing 'dense' and 'sparse'
        query_embeddings = await loop.run_in_executor(None, model.embed_query, search_query)
        query_vector_np = np.array(query_embeddings["dense"])
        query_vector = query_embeddings["dense"]
        sparse_query = query_embeddings["sparse"]

        if use_cache:
            cached_results = _get_semantic_cache().get(search_query, query_vector_np)
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
                    top_results.append({
                        "text": doc_text, "source": ent.get("source"), "page": ent.get("page", 0),
                        "summary": ent.get("summary", ""), "doc_date": ent.get("doc_date", ""),
                        "doc_type": ent.get("doc_type", ""), "authority": ent.get("authority", ""),
                        "doc_number": ent.get("doc_number", ""),
                        "is_table": ent.get("is_table", False), "chunk_type": ent.get("chunk_type", ""),
                        "parent_id": ent.get("parent_id", ""),
                        "bbox": _safe_json_loads(ent.get("bbox", "[0,0,1000,1000]")),
                        "validity_status": ent.get("validity_status", "ACTIVE"),
                        "project_code": ent.get("project_code", "GENERIC"),
                        "discipline": ent.get("discipline", "UNKNOWN"),
                        "hierarchy_path": ent.get("hierarchy_path", ""),
                        "doc_status": ent.get("doc_status", "ACTIVE"),
                        "revision": ent.get("revision", 0),
                        "score": hybrid_score
                    })
                top_results.sort(key=lambda x: x["score"], reverse=True)
            else:
                for hit in raw_hits:
                    ent = hit.entity
                    top_results.append({
                        "text": ent.get("text"), "source": ent.get("source"), "page": ent.get("page", 0),
                        "summary": ent.get("summary", ""), "doc_date": ent.get("doc_date", ""),
                        "doc_type": ent.get("doc_type", ""), "authority": ent.get("authority", ""),
                        "doc_number": ent.get("doc_number", ""),
                        "is_table": ent.get("is_table", False), "chunk_type": ent.get("chunk_type", ""),
                        "parent_id": ent.get("parent_id", ""),
                        "bbox": _safe_json_loads(ent.get("bbox", "[0,0,1000,1000]")),
                        "validity_status": ent.get("validity_status", "ACTIVE"),
                        "project_code": ent.get("project_code", "GENERIC"),
                        "discipline": ent.get("discipline", "UNKNOWN"),
                        "hierarchy_path": ent.get("hierarchy_path", ""),
                        "doc_status": ent.get("doc_status", "ACTIVE"),
                        "revision": ent.get("revision", 0),
                        "score": float(hit.score)
                    })

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
            _get_semantic_cache().set(search_query, query_vector_np, top_results)
            
        return {"results": top_results}
