"""Lightweight in-memory rate limiter middleware for FastAPI.

Uses token-bucket algorithm per IP address. No external dependencies.
"""
import logging
import os
import threading
import time

from prometheus_client import Counter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

RATE_LIMIT_REJECTED = Counter(
    'rag_rate_limit_rejected_total',
    'Total requests rejected by rate limiter',
    ['path_group'],
)


class _TokenBucket:
    """Simple token bucket rate limiter per key."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate          # tokens added per second
        self.capacity = capacity  # max burst
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}  # key → (tokens, last_refill)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            elapsed = now - last
            tokens = min(self.capacity, tokens + elapsed * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True
            self._buckets[key] = (tokens, now)
            return False

    def cleanup(self, max_age: float = 3600.0):
        """Remove stale entries older than max_age seconds."""
        now = time.monotonic()
        with self._lock:
            stale = [k for k, (_, t) in self._buckets.items() if now - t > max_age]
            for k in stale:
                del self._buckets[k]


# ── Pre-configured rate limiters ────────────────────────────────────────
_api_capacity = int(os.getenv("RATE_LIMIT_API_CAPACITY", "30"))
_admin_capacity = int(os.getenv("RATE_LIMIT_ADMIN_CAPACITY", "10"))

# API endpoints: configurable burst, sustained rate = capacity / 60
_api_limiter = _TokenBucket(rate=_api_capacity / 60.0, capacity=_api_capacity)
# Admin endpoints: configurable burst
_admin_limiter = _TokenBucket(rate=_admin_capacity / 60.0, capacity=_admin_capacity)

# Paths that bypass rate limiting
_EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/metrics"}


class QuotaTracker:
    """Tracks sliding window requests for Google AI Studio Free Tier (14,400 RPD)."""

    def __init__(self, max_rpd: int = 14400):
        self.max_rpd = max_rpd
        self._counter = 0
        self._lock = threading.Lock()
        self._reset_time = time.time() + 86400

    def record_request(self) -> bool:
        """Returns True if within safe cloud quota limit (<95%), False if threshold exceeded."""
        now = time.time()
        with self._lock:
            if now > self._reset_time:
                self._counter = 0
                self._reset_time = now + 86400
            self._counter += 1
            return self._counter < int(self.max_rpd * 0.95)

    def is_safe(self) -> bool:
        with self._lock:
            return self._counter < int(self.max_rpd * 0.95)


quota_tracker = QuotaTracker()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies IP-based rate limiting & Zero-Cloud Fallback.

    - Admin paths (/admin/*): 10 req/min
    - API paths (/search, /chat, etc.): 30 req/min
    - Health/docs: exempt
    - High traffic / quota exhaustion: Seamlessly routes to Local vLLM Qwen 35B (Zero-Cloud Fallback).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in _EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if "/admin" in path:
            limiter = _admin_limiter
        else:
            limiter = _api_limiter

        is_allowed = limiter.allow(client_ip)
        is_quota_safe = quota_tracker.record_request()

        if not is_allowed or not is_quota_safe:
            path_group = "admin" if "/admin" in path else "api"
            RATE_LIMIT_REJECTED.labels(path_group=path_group).inc()
            logger.info(
                f"[ZERO-CLOUD-FALLBACK] Rate/Quota limit reached ({client_ip} on {path}). "
                f"Seamlessly falling back to Local vLLM Qwen 35B."
            )
            request.state.force_local_vllm = True
            response = await call_next(request)
            response.headers["X-Zero-Cloud-Fallback"] = "1"
            return response

        return await call_next(request)
