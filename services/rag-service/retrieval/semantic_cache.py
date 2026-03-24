"""Thread-safe in-memory semantic cache with TTL and LRU eviction.

Uses vectorized numpy operations for O(1) amortized similarity lookup
instead of O(n) per-entry cosine computation.
"""
import logging
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)


class SemanticCache:
    """In-memory semantic cache with TTL, LRU eviction, and vectorized lookup."""

    def __init__(self, threshold: float = 0.92, max_size: int = 1000, ttl_seconds: float = 3600.0):
        self.threshold = threshold
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

        # Parallel arrays — kept in sync by index
        self._keys: list[str] = []
        self._embeddings: np.ndarray | None = None  # shape: (n, dim)
        self._norms: np.ndarray | None = None        # shape: (n,) precomputed
        self._results: list = []
        self._timestamps: list[float] = []

    def _evict_expired(self):
        """Remove expired entries (caller holds lock)."""
        now = time.monotonic()
        keep = [i for i, ts in enumerate(self._timestamps) if (now - ts) <= self.ttl_seconds]
        if len(keep) == len(self._keys):
            return
        self._keys = [self._keys[i] for i in keep]
        self._results = [self._results[i] for i in keep]
        self._timestamps = [self._timestamps[i] for i in keep]
        if self._embeddings is not None and len(keep) > 0:
            self._embeddings = self._embeddings[keep]
            self._norms = self._norms[keep]
        else:
            self._embeddings = None
            self._norms = None

    def get(self, query: str, query_embedding: np.ndarray):
        with self._lock:
            self._evict_expired()
            if self._embeddings is None or len(self._keys) == 0:
                return None

            norm_q = np.linalg.norm(query_embedding)
            if norm_q == 0:
                return None

            # Vectorized cosine similarity: dot(matrix, query) / (norms * norm_q)
            scores = self._embeddings @ query_embedding / (self._norms * norm_q)
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])

            if best_score >= self.threshold:
                # LRU: refresh timestamp on hit
                self._timestamps[best_idx] = time.monotonic()
                logger.info(f"Semantic cache hit! Similarity: {best_score:.4f}")
                return self._results[best_idx]
        return None

    def set(self, query: str, query_embedding: np.ndarray, results):
        with self._lock:
            if len(self._keys) >= self.max_size:
                # Evict oldest entry
                oldest_idx = int(np.argmin(self._timestamps))
                self._keys.pop(oldest_idx)
                self._results.pop(oldest_idx)
                self._timestamps.pop(oldest_idx)
                if self._embeddings is not None:
                    self._embeddings = np.delete(self._embeddings, oldest_idx, axis=0)
                    self._norms = np.delete(self._norms, oldest_idx)

            self._keys.append(query)
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
