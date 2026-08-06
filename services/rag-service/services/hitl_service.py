"""HITL (Human-in-the-Loop) sampling service for Legal RAG QA.

Randomly samples a fraction of queries for expert review.
Stores flagged queries in Redis for review dashboard consumption.

Features:
  - Configurable sampling rate (default 1%)
  - Confidence-gated flagging: auto-flag low-score retrievals
  - Redis-backed queue for review workflow
  - Prometheus metrics

Usage:
    from services.hitl_service import get_hitl_service

    hitl = get_hitl_service()
    hitl.maybe_sample(query, results, session_id="session-123")
    # or force-flag:
    hitl.flag_for_review(query, results, reason="low_confidence")
"""
import json
import logging
import os
import random
import time
import threading
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge
    HITL_SAMPLED = Counter("hitl_samples_total", "Queries sampled for expert review", ["reason"])
    HITL_QUEUE_SIZE = Gauge("hitl_review_queue_size", "Current HITL review queue size")
except (ImportError, ValueError):
    class _Metric:
        def labels(self, **kw): return self
        def inc(self, n=1): pass
        def set(self, v): pass
    HITL_SAMPLED = _Metric()
    HITL_QUEUE_SIZE = _Metric()


@dataclass
class HITLSample:
    query: str
    session_id: str
    top_results: list[dict]       # Top 3 results (truncated for size)
    retrieval_scores: list[float]
    flagged_reason: str           # "random_sample", "low_confidence", "manual"
    timestamp: float
    reviewed: bool = False
    expert_rating: int | None = None   # 1-5 rating assigned by expert
    expert_notes: str = ""


class HITLService:
    """Human-in-the-Loop review sampling service."""

    REDIS_KEY = "hitl:review_queue"
    REDIS_REVIEWED_KEY = "hitl:reviewed"

    def __init__(
        self,
        sample_rate: float = 0.01,           # 1% of queries
        low_confidence_threshold: float = 0.45,  # Flag below this score
        max_queue_size: int = 500,
        redis_url: str | None = None,
    ):
        self.sample_rate = float(os.environ.get("HITL_SAMPLE_RATE", sample_rate))
        self.low_confidence_threshold = low_confidence_threshold
        self.max_queue_size = max_queue_size
        self._redis = None
        self._lock = threading.Lock()

        if redis_url:
            try:
                import redis
                # Use DB 4 for HITL data (separate from L2 cache on DB 3)
                base_url = redis_url.rsplit("/", 1)[0] if "/" in redis_url.rsplit(":", 1)[-1] else redis_url
                self._redis = redis.Redis.from_url(f"{base_url}/4", decode_responses=True)
                self._redis.ping()
                logger.info("HITLService connected to Redis DB 4.")
            except Exception as e:
                logger.warning(f"HITLService Redis unavailable: {e} — using in-memory queue.")
                self._redis = None

        # In-memory fallback queue
        self._memory_queue: list[dict] = []

    def maybe_sample(
        self,
        query: str,
        results: list[dict],
        session_id: str = "",
    ) -> bool:
        """Randomly sample or auto-flag a query for expert review.

        Returns True if the query was queued for review.
        """
        # Low-confidence gate: check top-5 avg score
        if results:
            scores = [r.get("score", 0.0) for r in results[:5]]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            if avg_score < self.low_confidence_threshold:
                return self.flag_for_review(query, results, session_id, reason="low_confidence")

        # Random sampling
        if random.random() < self.sample_rate:
            return self.flag_for_review(query, results, session_id, reason="random_sample")

        return False

    def flag_for_review(
        self,
        query: str,
        results: list[dict],
        session_id: str = "",
        reason: str = "manual",
    ) -> bool:
        """Force-flag a query for expert review."""
        sample = HITLSample(
            query=query,
            session_id=session_id,
            top_results=[
                {"text": r.get("text", "")[:500], "source": r.get("source"), "score": r.get("score")}
                for r in results[:3]
            ],
            retrieval_scores=[r.get("score", 0.0) for r in results[:5]],
            flagged_reason=reason,
            timestamp=time.time(),
        )

        success = self._enqueue(sample)
        if success:
            HITL_SAMPLED.labels(reason=reason).inc()
            logger.info(f"[HITL] Queued for review ({reason}): {query[:60]}")
        return success

    def _enqueue(self, sample: HITLSample) -> bool:
        """Add sample to Redis or memory queue. Returns True on success."""
        payload = json.dumps(asdict(sample), ensure_ascii=False, default=str)

        if self._redis:
            try:
                with self._lock:
                    current_size = self._redis.llen(self.REDIS_KEY)
                    if current_size >= self.max_queue_size:
                        logger.debug(f"[HITL] Queue full ({current_size}), skipping.")
                        return False
                    self._redis.lpush(self.REDIS_KEY, payload)
                    HITL_QUEUE_SIZE.set(current_size + 1)
                return True
            except Exception as e:
                logger.warning(f"[HITL] Redis enqueue failed: {e}")

        # Fallback: in-memory
        with self._lock:
            if len(self._memory_queue) >= self.max_queue_size:
                return False
            self._memory_queue.append(json.loads(payload))
        return True

    def get_pending_reviews(self, limit: int = 50) -> list[dict]:
        """Retrieve pending review items (for admin dashboard)."""
        if self._redis:
            try:
                raw = self._redis.lrange(self.REDIS_KEY, 0, limit - 1)
                return [json.loads(r) for r in raw]
            except Exception as e:
                logger.warning(f"[HITL] Redis read failed: {e}")
        return self._memory_queue[:limit]

    def submit_review(self, query: str, rating: int, notes: str = "") -> bool:
        """Mark a reviewed item with expert rating (1-5)."""
        if not (1 <= rating <= 5):
            raise ValueError(f"Rating must be 1-5, got {rating}")

        review = {
            "query": query,
            "rating": rating,
            "notes": notes,
            "reviewed_at": time.time(),
        }
        if self._redis:
            try:
                self._redis.lpush(self.REDIS_REVIEWED_KEY, json.dumps(review, ensure_ascii=False))
                self._redis.ltrim(self.REDIS_REVIEWED_KEY, 0, 999)  # Keep last 1000
                logger.info(f"[HITL] Review submitted: rating={rating} for '{query[:40]}'")
                return True
            except Exception as e:
                logger.warning(f"[HITL] Review submission failed: {e}")
        return False

    def queue_size(self) -> int:
        """Current review queue size."""
        if self._redis:
            try:
                return self._redis.llen(self.REDIS_KEY)
            except Exception:
                pass
        return len(self._memory_queue)


# ── Module singleton ─────────────────────────────────────────────────────────

_hitl_instance: HITLService | None = None
_hitl_lock = threading.Lock()


def get_hitl_service(redis_url: str | None = None) -> HITLService:
    """Return the module-level HITLService singleton."""
    global _hitl_instance
    if _hitl_instance is None:
        with _hitl_lock:
            if _hitl_instance is None:
                if redis_url is None:
                    try:
                        from core.config import get_settings
                        redis_url = get_settings().REDIS_URL
                    except Exception:
                        pass
                _hitl_instance = HITLService(redis_url=redis_url)
    return _hitl_instance
