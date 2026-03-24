"""Lightweight in-memory rate limiter middleware for FastAPI.

Uses token-bucket algorithm per IP address. No external dependencies.
"""
import logging
import time
import threading
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from prometheus_client import Counter

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
import os as _os
_api_capacity = int(_os.getenv("RATE_LIMIT_API_CAPACITY", "30"))
_admin_capacity = int(_os.getenv("RATE_LIMIT_ADMIN_CAPACITY", "10"))
# API endpoints: configurable burst, sustained rate = capacity / 60
_api_limiter = _TokenBucket(rate=_api_capacity / 60.0, capacity=_api_capacity)
# Admin endpoints: configurable burst
_admin_limiter = _TokenBucket(rate=_admin_capacity / 60.0, capacity=_admin_capacity)

# Paths that bypass rate limiting
_EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/metrics"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies IP-based rate limiting.

    - Admin paths (/admin/*): 10 req/min
    - API paths (/search, /chat, etc.): 30 req/min
    - Health/docs: exempt
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

        if not limiter.allow(client_ip):
            path_group = "admin" if "/admin" in path else "api"
            RATE_LIMIT_REJECTED.labels(path_group=path_group).inc()
            logger.warning(f"Rate limited: {client_ip} on {path}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": "5"},
            )

        return await call_next(request)
