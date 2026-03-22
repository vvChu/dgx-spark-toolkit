"""Generic lazy-initialization utilities to replace ad-hoc singleton patterns."""
import threading
from typing import TypeVar, Callable

T = TypeVar("T")


class LazyInit:
    """Thread-safe lazy initializer that replaces the repeated
    ``_global = None / _lock = Lock() / def _get(): ...`` pattern.

    Usage::

        _embedding = LazyInit(lambda: BGE_M3_HybridEmbedding())
        model = _embedding.get()   # initialized on first call, cached thereafter
    """

    def __init__(self, factory: Callable[[], T]):
        self._factory = factory
        self._instance: T | None = None
        self._lock = threading.Lock()

    def get(self) -> T:
        if self._instance is None:
            with self._lock:
                if self._instance is None:  # double-checked locking
                    self._instance = self._factory()
        return self._instance

    def reset(self) -> None:
        """Clear the cached instance (useful for testing)."""
        with self._lock:
            self._instance = None
