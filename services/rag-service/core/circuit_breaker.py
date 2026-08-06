"""Circuit breaker + per-key token bucket rate limiter for LLM gateway.

Usage:
    from core.circuit_breaker import get_circuit_breaker, KeyRateLimiter

    cb = get_circuit_breaker("rag-core")
    if cb.is_open():
        raise RuntimeError("Circuit open — rag-core unavailable")
    try:
        result = call_llm(...)
        cb.record_success()
    except Exception as e:
        cb.record_failure(e)
        raise
"""
import logging
import threading
import time
from collections import defaultdict, deque
from enum import Enum
from functools import lru_cache

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal — calls pass through
    OPEN = "open"          # Failing — calls blocked
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Per-model circuit breaker with half-open recovery testing.

    States:
        CLOSED  → failure_count >= threshold → OPEN
        OPEN    → recovery_timeout elapsed  → HALF_OPEN
        HALF_OPEN → success               → CLOSED
                  → failure              → OPEN (reset timer)
    """

    def __init__(
        self,
        model_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ):
        self.model_name = model_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        """Return True if circuit is open (calls should be blocked)."""
        with self._lock:
            return self._check_state() == CircuitState.OPEN

    def _check_state(self) -> CircuitState:
        """Internal state check — caller must hold lock."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"[CircuitBreaker] {self.model_name}: OPEN → HALF_OPEN (testing recovery)")
        return self._state

    def allow_request(self) -> bool:
        """Gate check before a model call. Returns False if circuit is open."""
        with self._lock:
            state = self._check_state()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False  # Already testing with another call
            return False  # OPEN

    def record_success(self):
        """Record a successful model call — resets the breaker."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"[CircuitBreaker] {self.model_name}: HALF_OPEN → CLOSED (recovery confirmed)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    def record_failure(self, exc: Exception | None = None):
        """Record a failed model call. Opens circuit if threshold exceeded."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[CircuitBreaker] {self.model_name}: HALF_OPEN → OPEN (probe failed: {exc})"
                )
            elif self._failure_count >= self.failure_threshold:
                prev = self._state
                self._state = CircuitState.OPEN
                if prev != CircuitState.OPEN:
                    logger.warning(
                        f"[CircuitBreaker] {self.model_name}: CLOSED → OPEN "
                        f"(failures={self._failure_count}/{self.failure_threshold}, err={exc})"
                    )

    @property
    def state(self) -> str:
        with self._lock:
            return self._check_state().value

    def status(self) -> dict:
        with self._lock:
            return {
                "model": self.model_name,
                "state": self._check_state().value,
                "failure_count": self._failure_count,
                "last_failure_age_s": (
                    round(time.monotonic() - self._last_failure_time, 1)
                    if self._last_failure_time else None
                ),
            }


# ── Token Bucket Rate Limiter ──────────────────────────────────────────────────

class TokenBucket:
    """Thread-safe token bucket for rate limiting.

    Args:
        capacity: Maximum tokens (burst capacity)
        refill_rate: Tokens added per second
    """

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume `tokens`. Returns True if successful."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def available(self) -> float:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            return min(self.capacity, self._tokens + elapsed * self.refill_rate)


class KeyRateLimiter:
    """Per-API-key rate limiter: RPM (requests per minute) + RPD (requests per day).

    Usage:
        limiter = KeyRateLimiter(rpm=15, rpd=500, key_id="gemini-key-1")
        if not limiter.allow():
            raise RateLimitError(f"Key {limiter.key_id} quota exceeded")
        # proceed with call
    """

    def __init__(self, rpm: float = 15, rpd: float = 500, key_id: str = "default"):
        self.key_id = key_id
        self._minute_bucket = TokenBucket(capacity=rpm, refill_rate=rpm / 60.0)
        self._day_bucket = TokenBucket(capacity=rpd, refill_rate=rpd / 86400.0)

    def allow(self) -> bool:
        """Returns True if both RPM and RPD buckets have capacity."""
        rpm_ok = self._minute_bucket.consume()
        if not rpm_ok:
            logger.debug(f"[RateLimiter] {self.key_id}: RPM bucket exhausted")
            return False
        rpd_ok = self._day_bucket.consume()
        if not rpd_ok:
            # Refund the RPM token we just consumed
            self._minute_bucket._tokens = min(
                self._minute_bucket.capacity,
                self._minute_bucket._tokens + 1
            )
            logger.warning(f"[RateLimiter] {self.key_id}: RPD bucket exhausted")
            return False
        return True

    def remaining(self) -> dict:
        return {
            "key_id": self.key_id,
            "rpm_available": round(self._minute_bucket.available(), 1),
            "rpd_available": round(self._day_bucket.available(), 1),
        }


# ── Module-level singletons ────────────────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(
    model_name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Return or create a CircuitBreaker for the named model."""
    with _breakers_lock:
        if model_name not in _breakers:
            _breakers[model_name] = CircuitBreaker(
                model_name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _breakers[model_name]


def all_circuit_statuses() -> list[dict]:
    """Return status of all registered circuit breakers (for /health endpoint)."""
    with _breakers_lock:
        return [cb.status() for cb in _breakers.values()]
