"""Thread-safe in-memory semantic cache with TTL and LRU eviction."""
import logging
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)


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
                oldest = min(self.cache, key=lambda k: self.cache[k]["timestamp"])
                del self.cache[oldest]
            self.cache[query] = {
                "embedding": query_embedding,
                "results": results,
                "timestamp": time.monotonic(),
            }
