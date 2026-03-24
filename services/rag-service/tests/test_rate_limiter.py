"""Unit tests for core.rate_limiter — TokenBucket and RateLimitMiddleware."""
import os
import sys
import time
import types

import pytest

# CI stubs
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")
os.environ.setdefault("ADMIN_SECRET", "test-admin-key-for-ci")

_fake_mod = types.ModuleType("retrieval.embeddings.bge_m3_hybrid")


class _FakeEmb:
    def __init__(self, *a, **kw): pass


_fake_mod.BGE_M3_HybridEmbedding = _FakeEmb
sys.modules.setdefault("retrieval.embeddings.bge_m3_hybrid", _fake_mod)


from core.rate_limiter import _TokenBucket, RateLimitMiddleware


# ── TokenBucket ─────────────────────────────────────────────────────────
class TestTokenBucket:
    def test_allows_within_capacity(self):
        b = _TokenBucket(rate=1.0, capacity=5)
        for _ in range(5):
            assert b.allow("ip1") is True

    def test_rejects_after_capacity_exhausted(self):
        b = _TokenBucket(rate=0.001, capacity=3)  # very slow refill
        for _ in range(3):
            b.allow("ip1")
        assert b.allow("ip1") is False

    def test_refills_over_time(self):
        b = _TokenBucket(rate=100.0, capacity=5)  # fast refill: 100 tok/s
        for _ in range(5):
            b.allow("ip1")
        assert b.allow("ip1") is False
        time.sleep(0.02)  # wait 20ms → ~2 tokens refilled
        assert b.allow("ip1") is True

    def test_separate_keys_isolated(self):
        b = _TokenBucket(rate=0.001, capacity=2)
        b.allow("ip1")
        b.allow("ip1")
        assert b.allow("ip1") is False
        assert b.allow("ip2") is True  # ip2 unaffected

    def test_cleanup_removes_stale(self):
        b = _TokenBucket(rate=1.0, capacity=5)
        b.allow("stale")
        # Manually set old timestamp
        b._buckets["stale"] = (5.0, time.monotonic() - 7200)
        b.cleanup(max_age=3600)
        assert "stale" not in b._buckets


# ── RateLimitMiddleware integration ─────────────────────────────────────
class TestRateLimitMiddleware:
    def test_health_exempt(self, client):
        """Health endpoint should never be rate limited."""
        for _ in range(50):
            resp = client.get("/health")
            assert resp.status_code != 429

    def test_docs_exempt(self, client):
        """OpenAPI docs should never be rate limited."""
        for _ in range(10):
            resp = client.get("/openapi.json")
            assert resp.status_code != 429


@pytest.fixture
def client():
    from starlette.testclient import TestClient
    from main import app
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _test_lifespan(_app):
        yield

    app.router.lifespan_context = _test_lifespan
    with TestClient(app) as c:
        yield c
