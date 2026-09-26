"""Two-tier semantic cache: L1 in-memory (numpy) + L2 Redis (persistent).

L1 provides sub-millisecond lookup via vectorized cosine similarity.
L2 provides persistence across container restarts, stored in Redis DB 3.
"""
import json
import logging
import threading
import time
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class SemanticCache:
    """Two-tier semantic cache with TTL, LRU eviction, and vectorized lookup."""

    def __init__(
        self,
        threshold: float = 0.92,
        max_size: int = 1000,
        ttl_seconds: float = 3600.0,
        redis_url: str | None = None,
    ):
        self.threshold = threshold
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

        # L1: In-memory (parallel arrays — kept in sync by index)
        self._keys: list[str] = []
        self._filter_keys: list[str] = []  # filter expression per entry
        self._embeddings: np.ndarray | None = None  # shape: (n, dim)
        self._norms: np.ndarray | None = None        # shape: (n,) precomputed
        self._results: list = []
        self._timestamps: list[float] = []

        # Cache metrics & HyDE query expansion cache
        self._hits = 0
        self._misses = 0
        self._hyde_cache: dict[str, str] = {}

        # L2: Redis persistent cache (optional)
        self._redis = None
        self._redis_key = "semantic_cache:entries"
        if redis_url:
            try:
                import redis
                from retrieval.tier0_cache import format_redis_db3_url
                db3_url = format_redis_db3_url(redis_url)
                self._redis = redis.Redis.from_url(db3_url, decode_responses=False)
                self._redis.ping()
                logger.info("SemanticCache L2 (Redis DB 3) connected.")
            except Exception as e:
                logger.warning("SemanticCache L2 Redis unavailable: %s", e)
                self._redis = None

    def _evict_expired(self):
        """Remove expired entries (caller holds lock)."""
        now = time.monotonic()
        keep = [i for i, ts in enumerate(self._timestamps) if (now - ts) <= self.ttl_seconds]
        if len(keep) == len(self._keys):
            return
        self._keys = [self._keys[i] for i in keep]
        self._filter_keys = [self._filter_keys[i] for i in keep]
        self._results = [self._results[i] for i in keep]
        self._timestamps = [self._timestamps[i] for i in keep]
        if self._embeddings is not None and len(keep) > 0:
            self._embeddings = self._embeddings[keep]
            self._norms = self._norms[keep]
        else:
            self._embeddings = None
            self._norms = None

    def get_hyde(self, query: str) -> Optional[str]:
        """Get cached HyDE query expansion text."""
        with self._lock:
            return self._hyde_cache.get(query.strip())

    def set_hyde(self, query: str, hyde_text: str):
        """Store HyDE query expansion text in cache."""
        with self._lock:
            if len(self._hyde_cache) >= self.max_size:
                self._hyde_cache.clear()
            self._hyde_cache[query.strip()] = hyde_text

    def get_stats(self) -> dict:
        """Return cache hit/miss statistics and storage metrics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = round((self._hits / total * 100.0), 1) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "l1_size": len(self._keys),
                "hyde_cache_size": len(self._hyde_cache),
                "l2_connected": self._redis is not None,
            }

    def get(self, query: str, query_embedding: np.ndarray, filter_key: str = ""):
        """Check L1 (in-memory), then L2 (Redis) for cached results.

        Parameters
        ----------
        filter_key:
            Metadata filter expression. Only entries with matching filter_key
            are considered cache hits, preventing cross-filter contamination.
        """
        # L1 check
        with self._lock:
            self._evict_expired()
            if self._embeddings is not None and len(self._keys) > 0:
                norm_q = np.linalg.norm(query_embedding)
                if norm_q > 0:
                    scores = self._embeddings @ query_embedding / (self._norms * norm_q)
                    # Mask out entries with different filter keys
                    for i, fk in enumerate(self._filter_keys):
                        if fk != filter_key:
                            scores[i] = -1.0
                    best_idx = int(np.argmax(scores))
                    best_score = float(scores[best_idx])

                    if best_score >= self.threshold:
                        # LRU: refresh timestamp on hit
                        self._timestamps[best_idx] = time.monotonic()
                        self._hits += 1
                        logger.info(f"Semantic cache L1 hit! Similarity: {best_score:.4f}")
                        return self._results[best_idx]

        # L2 check (Redis) — scan recent entries
        if self._redis:
            try:
                l2_result = self._get_from_redis(query_embedding, filter_key)
                if l2_result is not None:
                    # Promote to L1
                    self.set(query, query_embedding, l2_result, filter_key=filter_key, skip_redis=True)
                    with self._lock:
                        self._hits += 1
                    logger.info("Semantic cache L2 (Redis) hit, promoted to L1.")
                    return l2_result
            except Exception as e:
                logger.debug("L2 cache check failed: %s", e)

        with self._lock:
            self._misses += 1
        return None

    def _get_from_redis(self, query_embedding: np.ndarray, filter_key: str = "") -> Optional[list]:
        """Scan recent Redis cache entries for semantic similarity match."""
        if not self._redis:
            return None

        entries = self._redis.lrange(self._redis_key, 0, 99)  # Check last 100 entries
        if not entries:
            return None

        for raw_entry in entries:
            try:
                entry = json.loads(raw_entry)
                if entry.get("filter_key", "") != filter_key:
                    continue

                cached_emb = np.array(entry.get("embedding", []), dtype=np.float32)
                if len(cached_emb) != len(query_embedding) or len(cached_emb) == 0:
                    continue

                score = float(np.dot(query_embedding, cached_emb) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(cached_emb) + 1e-9
                ))
                if score >= self.threshold:
                    return entry.get("results")
            except Exception:
                continue

        return None

    def set(self, query: str, query_embedding: np.ndarray, results, filter_key: str = "", skip_redis: bool = False):
        """Store results in L1 (always) and L2 Redis (if available)."""
        if len(query_embedding) == 0:
            return

        # L1: in-memory
        with self._lock:
            if len(self._keys) >= self.max_size:
                oldest_idx = int(np.argmin(self._timestamps))
                self._keys.pop(oldest_idx)
                self._filter_keys.pop(oldest_idx)
                self._results.pop(oldest_idx)
                self._timestamps.pop(oldest_idx)
                if self._embeddings is not None:
                    self._embeddings = np.delete(self._embeddings, oldest_idx, axis=0)
                    self._norms = np.delete(self._norms, oldest_idx)

            self._keys.append(query)
            self._filter_keys.append(filter_key)
            self._results.append(results)
            self._timestamps.append(time.monotonic())

            emb = query_embedding.reshape(1, -1)
            norm = np.linalg.norm(query_embedding)
            if self._embeddings is None:
                self._embeddings = emb
                self._norms = np.array([norm])
            else:
                self._embeddings = np.vstack([self._embeddings, emb])
                self._norms = np.append(self._norms, norm)

        # L2: Redis persistent (skip if this is a L2→L1 promotion)
        if self._redis and not skip_redis and len(query_embedding) > 0:
            try:
                entry = {
                    "query": query[:500],
                    "embedding": query_embedding.tolist(),
                    "results": results,
                    "filter_key": filter_key,
                    "timestamp": time.time(),
                }
                serialized = json.dumps(entry, ensure_ascii=False, default=str)
                self._redis.lpush(self._redis_key, serialized)
                self._redis.ltrim(self._redis_key, 0, self.max_size - 1)
                self._redis.expire(self._redis_key, int(self.ttl_seconds))
            except Exception as e:
                logger.debug("L2 cache write failed: %s", e)

    def clear(self):
        """Clear L1 in-memory entries and L2 Redis semantic cache entries."""
        with self._lock:
            self._keys.clear()
            self._filter_keys.clear()
            self._embeddings = None
            self._norms = None
            self._results.clear()
            self._timestamps.clear()
            self._hyde_cache.clear()
        if self._redis:
            try:
                self._redis.delete(self._redis_key)
            except Exception as e:
                logger.debug("Failed to clear Redis semantic cache: %s", e)


class InMemorySemanticCache(SemanticCache):
    """In-memory test adapter for SemanticCache."""

    def __init__(self, default_results: Optional[list] = None):
        super().__init__(redis_url=None)
        self.default_results = default_results
        self._store: dict[str, list] = {}

    def get(self, query: str, query_embedding: np.ndarray, filter_key: str = ""):
        key = f"{query.strip()}:{filter_key}"
        if key in self._store:
            self._hits += 1
            return self._store[key]
        self._misses += 1
        return None

    def set(self, query: str, query_embedding: np.ndarray, results, filter_key: str = "", skip_redis: bool = False):
        key = f"{query.strip()}:{filter_key}"
        self._store[key] = results

    def clear(self):
        super().clear()
        self._store.clear()
