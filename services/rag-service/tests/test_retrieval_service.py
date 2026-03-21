"""Unit tests for services.retrieval_service — SemanticCache, rewrite_query, RetrievalService.search."""
import asyncio
import os
import sys
import types
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure CI-safe credentials
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

# Stub heavy embedding module (same as conftest.py)
_fake_mod = types.ModuleType("retrieval.embeddings.bge_m3_hybrid")
class _FakeEmb:
    def __init__(self, *a, **kw): pass
_fake_mod.BGE_M3_HybridEmbedding = _FakeEmb
sys.modules.setdefault("retrieval.embeddings.bge_m3_hybrid", _fake_mod)

from services.retrieval_service import SemanticCache


# ── SemanticCache ───────────────────────────────────────────────────────
class TestSemanticCache:
    def test_cache_miss_on_empty(self):
        cache = SemanticCache(threshold=0.9)
        vec = np.array([1.0, 0.0, 0.0])
        assert cache.get("q", vec) is None

    def test_set_and_get_exact_hit(self):
        cache = SemanticCache(threshold=0.9)
        vec = np.array([1.0, 0.0, 0.0])
        cache.set("q", vec, [{"text": "result"}])
        result = cache.get("q", vec)
        assert result is not None
        assert result[0]["text"] == "result"

    def test_cache_miss_below_threshold(self):
        cache = SemanticCache(threshold=0.99)
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.5, 0.5, 0.0])
        cache.set("q1", v1, [{"text": "r1"}])
        assert cache.get("q2", v2) is None

    def test_eviction_on_max_size(self):
        cache = SemanticCache(threshold=0.9, max_size=2)
        for i in range(3):
            vec = np.zeros(3)
            vec[i % 3] = 1.0
            cache.set(f"q{i}", vec, [{"text": f"r{i}"}])
        assert len(cache.cache) == 2

    def test_expired_entries_cleaned(self):
        cache = SemanticCache(threshold=0.9, ttl_seconds=0)
        vec = np.array([1.0, 0.0, 0.0])
        cache.set("q", vec, [{"text": "old"}])
        # TTL=0 means instant expiry
        assert cache.get("q", vec) is None


# ── rewrite_query ───────────────────────────────────────────────────────
class TestRewriteQuery:
    def test_rewrite_returns_original_on_failure(self):
        from services.retrieval_service import rewrite_query, _query_rewrite_cache
        _query_rewrite_cache.clear()

        with patch("services.retrieval_service._get_rewrite_http_client") as mock_fn:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("timeout")
            mock_fn.return_value = mock_client

            result = asyncio.get_event_loop().run_until_complete(
                rewrite_query("test query")
            )
            assert result == "test query"

    def test_rewrite_caches_result(self):
        from services.retrieval_service import rewrite_query, _query_rewrite_cache
        _query_rewrite_cache.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '"improved query"'}}]
        }

        with patch("services.retrieval_service._get_rewrite_http_client") as mock_fn:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_fn.return_value = mock_client

            result = asyncio.get_event_loop().run_until_complete(
                rewrite_query("original")
            )
            assert result == "improved query"
            assert "original" in _query_rewrite_cache
