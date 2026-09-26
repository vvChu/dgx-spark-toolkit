"""Tier 0 Pre-Embedding Exact Query Cache.

Provides sub-millisecond (< 1 ms) exact match query caching using:
- L0 In-Memory: Thread-safe LRU OrderedDict with TTL expiration.
- L1/L2 Distributed: Redis DB 3 for cross-pod / cross-restart persistence.
Deterministic key generation uses Unicode NFC normalization and canonical JSON serialization.
"""
from collections import OrderedDict
import hashlib
import json
import logging
import threading
import time
from typing import Any, Optional
import unicodedata
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def format_redis_db3_url(redis_url: str) -> str:
    """Format and guarantee a Redis URL connects specifically to DB 3.

    Handles URLs with or without explicit ports, credentials, or paths.
    E.g.
    'redis://localhost:16379/0' -> 'redis://localhost:16379/3'
    'redis://redis' -> 'redis://redis/3'
    'redis://localhost' -> 'redis://localhost/3'
    """
    if not redis_url:
        return redis_url
    parsed = urlparse(redis_url)
    return urlunparse(parsed._replace(path="/3"))


def compute_sha256_cache_key(
    query: str,
    filter_expr: Optional[str] = None,
    limit: int = 10,
    use_reranker: bool = True,
) -> str:
    """Compute Tier 0 normalized SHA-256 exact cache key.

    Normalizes Unicode to NFC, collapses whitespace, lowers case, and serializes
    parameters deterministically via JSON.

    Args:
        query: Raw query text.
        filter_expr: Optional Milvus filter expression.
        limit: Number of search results requested.
        use_reranker: Flag indicating whether reranker is applied.

    Returns:
        Hex-encoded SHA-256 cache key prefixed with 'rag:exact:'.
    """
    clean_query = query if query is not None else ""
    normalized_query = " ".join(unicodedata.normalize("NFC", clean_query).strip().lower().split())
    filter_str = filter_expr.strip() if filter_expr else ""
    payload = json.dumps(
        [normalized_query, filter_str, int(limit), bool(use_reranker)],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"rag:exact:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class Tier0ExactCache:
    """Thread-safe two-tier exact query cache (L0 RAM + Redis DB 3)."""

    def __init__(
        self,
        max_size: int = 2000,
        ttl_seconds: float = 3600.0,
        redis_url: Optional[str] = None,
    ):
        """Initialize Tier 0 Exact Cache.

        Args:
            max_size: Maximum entries in L0 in-memory OrderedDict LRU store.
            ttl_seconds: Default expiration time in seconds for cached entries.
            redis_url: Optional Redis connection URL.
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._store: OrderedDict[str, tuple[list[dict[str, Any]], float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

        self._redis = None
        if redis_url:
            try:
                import redis
                db3_url = format_redis_db3_url(redis_url)
                self._redis = redis.Redis.from_url(db3_url, decode_responses=True)
                self._redis.ping()
                logger.info("Tier0ExactCache connected to Redis DB 3 (%s).", db3_url)
            except Exception as e:
                logger.warning("Tier0ExactCache Redis DB 3 unavailable: %s", e)
                self._redis = None

    def get(self, key: str) -> Optional[list]:
        """Retrieve cached search results by exact key.

        Checks L0 in-memory cache first. On miss, queries Redis DB 3 and populates
        L0 while preserving the remaining Redis TTL to prevent TTL drift.

        Args:
            key: Exact cache key string.

        Returns:
            Cached results list if hit and not expired, otherwise None.
        """
        now = time.monotonic()
        with self._lock:
            if key in self._store:
                results, expire_at = self._store[key]
                if now < expire_at:
                    self._store.move_to_end(key)
                    self._hits += 1
                    return results
                else:
                    del self._store[key]

        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.get(key)
                pipe.ttl(key)
                raw, ttl_rem = pipe.execute()
                if raw is not None:
                    results = json.loads(raw)
                    l0_ttl = ttl_rem if (ttl_rem is not None and ttl_rem > 0) else self.ttl_seconds
                    with self._lock:
                        self._store[key] = (results, now + l0_ttl)
                        self._store.move_to_end(key)
                        if len(self._store) > self.max_size:
                            self._store.popitem(last=False)
                        self._hits += 1
                    return results
            except Exception as e:
                logger.debug("Tier0ExactCache Redis get failed: %s", e)

        with self._lock:
            self._misses += 1
        return None

    def set(self, key: str, results: list, ttl_seconds: Optional[float] = None):
        """Store results into L0 RAM and Redis DB 3.

        Args:
            key: Exact cache key string.
            results: List of search result dictionaries.
            ttl_seconds: Optional custom TTL in seconds. Defaults to instance ttl_seconds.
        """
        effective_ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        if effective_ttl <= 0:
            return

        now = time.monotonic()
        expire_at = now + effective_ttl
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (results, expire_at)
            if len(self._store) > self.max_size:
                self._store.popitem(last=False)

        if self._redis:
            try:
                serialized = json.dumps(results, ensure_ascii=False, default=str)
                self._redis.set(key, serialized, ex=max(1, int(effective_ttl)))
            except Exception as e:
                logger.debug("Tier0ExactCache Redis set failed: %s", e)

    def clear(self):
        """Clear L0 RAM and scan-delete rag:exact:* keys from Redis DB 3."""
        with self._lock:
            self._store.clear()

        if self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(cursor=cursor, match="rag:exact:*", count=100)
                    if keys:
                        self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning("Failed to clear Redis exact cache: %s", e)

    def get_stats(self) -> dict:
        """Return cache hit/miss statistics and storage metrics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = round((self._hits / total * 100.0), 1) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "l0_size": len(self._store),
                "redis_connected": self._redis is not None,
            }
