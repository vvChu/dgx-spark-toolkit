"""Structured reasoning trace logger for RAG query observability.

Captures the full decision chain (cache check → rewrite → embed → retrieve →
rerank → graph → generate) with timing and metadata, then stores the trace in
Redis for later inspection via the /traces API.
"""
import json
import logging
import time
import uuid
from typing import Any, Optional

import redis.asyncio as aioredis
from prometheus_client import Histogram

logger = logging.getLogger(__name__)

TRACE_LATENCY = Histogram(
    "rag_query_trace_total_ms",
    "End-to-end query latency in milliseconds",
    buckets=(100, 250, 500, 1000, 2000, 5000, 10000, 30000),
)

# Redis key for the sorted set of recent traces (scored by timestamp)
_TRACES_KEY = "rag:traces"
_TRACE_TTL = 86400  # 24 hours
_MAX_STORED_TRACES = 500


class QueryTracer:
    """Collects structured trace steps for a single query execution."""

    def __init__(self, user_query: str, session_id: str | None = None):
        self.query_id = str(uuid.uuid4())[:12]
        self.user_query = user_query
        self.session_id = session_id
        self.steps: list[dict] = []
        self._started_at = time.monotonic()
        self._step_start: float | None = None

    def start_step(self, action: str) -> "QueryTracer":
        """Begin timing a new step."""
        self._step_start = time.monotonic()
        self.steps.append({"action": action})
        return self

    def end_step(self, **kwargs) -> None:
        """End the current step with optional metadata."""
        if not self.steps:
            return
        step = self.steps[-1]
        if self._step_start is not None:
            step["duration_ms"] = round((time.monotonic() - self._step_start) * 1000, 1)
        step.update(kwargs)
        self._step_start = None

    def add_step(self, action: str, **kwargs) -> None:
        """Add a complete step in one call (no timing)."""
        self.steps.append({"action": action, **kwargs})

    def finalize(
        self,
        outcome: str = "answered",
        result_count: int = 0,
        cache_hit: bool = False,
        model: str | None = None,
    ) -> dict:
        """Build the final trace dict and record latency metric."""
        total_ms = round((time.monotonic() - self._started_at) * 1000, 1)
        TRACE_LATENCY.observe(total_ms)

        trace = {
            "query_id": self.query_id,
            "user_query": self.user_query[:500],
            "session_id": self.session_id,
            "steps": self.steps,
            "total_latency_ms": total_ms,
            "outcome": outcome,
            "result_count": result_count,
            "cache_hit": cache_hit,
            "model": model,
            "timestamp": time.time(),
        }
        return trace


class TraceStore:
    """Redis-backed store for recent query traces."""

    def __init__(self, redis_url: str):
        base_url = redis_url.rsplit("/", 1)[0] if "/" in redis_url.rsplit(":", 1)[-1] else redis_url
        self.redis = aioredis.from_url(f"{base_url}/2", decode_responses=True)

    async def store(self, trace: dict) -> None:
        """Store a completed trace in the sorted set."""
        try:
            score = trace.get("timestamp", time.time())
            value = json.dumps(trace, ensure_ascii=False, default=str)
            await self.redis.zadd(_TRACES_KEY, {value: score})
            # Trim to max stored traces (remove oldest)
            count = await self.redis.zcard(_TRACES_KEY)
            if count > _MAX_STORED_TRACES:
                await self.redis.zremrangebyrank(_TRACES_KEY, 0, count - _MAX_STORED_TRACES - 1)
        except Exception as e:
            logger.warning("Failed to store trace: %s", e)

    async def get_recent(self, limit: int = 50) -> list[dict]:
        """Retrieve the N most recent traces."""
        try:
            raw_items = await self.redis.zrevrange(_TRACES_KEY, 0, limit - 1)
            return [json.loads(item) for item in raw_items]
        except Exception as e:
            logger.warning("Failed to read traces: %s", e)
            return []

    async def get_by_session(self, session_id: str, limit: int = 20) -> list[dict]:
        """Retrieve traces for a specific session."""
        all_traces = await self.get_recent(limit=200)
        return [t for t in all_traces if t.get("session_id") == session_id][:limit]

    async def close(self):
        await self.redis.aclose()
