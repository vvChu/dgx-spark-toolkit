"""Unit tests for Tier 0 Pre-Embedding Exact Query Cache and BGE-M3 thread safety."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time
import unicodedata
from unittest.mock import MagicMock, patch

import numpy as np

from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding
from retrieval.search_pipeline import SearchContext, SearchPipeline, get_tier0_cache, get_semantic_cache
from retrieval.tier0_cache import Tier0ExactCache, compute_sha256_cache_key, format_redis_db3_url


class TestTier0CacheKey:
    def test_format_redis_db3_url(self):
        assert format_redis_db3_url("redis://localhost:16379/0") == "redis://localhost:16379/3"
        assert format_redis_db3_url("redis://localhost:16379") == "redis://localhost:16379/3"
        assert format_redis_db3_url("redis://redis") == "redis://redis/3"
        assert format_redis_db3_url("redis://localhost") == "redis://localhost/3"
        assert format_redis_db3_url("redis://:secret@host:6379/1") == "redis://:secret@host:6379/3"
        assert format_redis_db3_url("") == ""
        assert format_redis_db3_url(None) is None

    def test_sha256_cache_key_deterministic_normalization(self):
        # Case and whitespace normalization
        k1 = compute_sha256_cache_key("  Quy Định PCCC  \n\t")
        k2 = compute_sha256_cache_key("quy định pccc")
        assert k1 == k2

        # Unicode NFC vs NFD equivalence
        text = "Quy chuẩn kỹ thuật quốc gia về an toàn cháy cho nhà và công trình"
        nfc_text = unicodedata.normalize("NFC", text)
        nfd_text = unicodedata.normalize("NFD", text)
        assert nfc_text != nfd_text  # Underlying code points differ
        assert compute_sha256_cache_key(nfc_text) == compute_sha256_cache_key(nfd_text)

    def test_sha256_cache_key_robustness(self):
        # None query fallback
        k_none = compute_sha256_cache_key(None)
        k_empty = compute_sha256_cache_key("")
        assert k_none == k_empty

        # Whitespace handling in filter_expr
        k_filter_clean = compute_sha256_cache_key("quy định", filter_expr='doc_type == "TT"')
        k_filter_spaces = compute_sha256_cache_key("quy định", filter_expr='  doc_type == "TT"  ')
        assert k_filter_clean == k_filter_spaces

        # Type determinism for limit and use_reranker
        k_typed1 = compute_sha256_cache_key("test", limit=10, use_reranker=True)
        k_typed2 = compute_sha256_cache_key("test", limit="10", use_reranker=1)
        assert k_typed1 == k_typed2

    def test_tier0_cache_filter_isolation(self):
        base_query = "quy định pccc"
        k_no_filter = compute_sha256_cache_key(base_query)
        k_filter_tt = compute_sha256_cache_key(base_query, filter_expr='doc_type == "TT"')
        k_filter_qcvn = compute_sha256_cache_key(base_query, filter_expr='doc_type == "QCVN"')
        k_limit_5 = compute_sha256_cache_key(base_query, limit=5)
        k_no_rerank = compute_sha256_cache_key(base_query, use_reranker=False)

        # All variants should produce distinct cache keys
        keys = {k_no_filter, k_filter_tt, k_filter_qcvn, k_limit_5, k_no_rerank}
        assert len(keys) == 5


class TestTier0ExactCache:
    def test_l0_ram_hit_and_miss(self):
        cache = Tier0ExactCache(max_size=10, ttl_seconds=3600.0, redis_url=None)
        key = "rag:exact:test1"
        data = [{"id": 1, "text": "QCVN 06"}]

        assert cache.get(key) is None
        cache.set(key, data)
        assert cache.get(key) == data

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert stats["l0_size"] == 1

    def test_lru_eviction(self):
        cache = Tier0ExactCache(max_size=3, ttl_seconds=3600.0, redis_url=None)
        cache.set("k1", [{"id": 1}])
        cache.set("k2", [{"id": 2}])
        cache.set("k3", [{"id": 3}])

        # Access k1 to make it most recently used
        assert cache.get("k1") == [{"id": 1}]

        # Insert k4, should evict k2 (least recently used)
        cache.set("k4", [{"id": 4}])

        assert cache.get("k1") == [{"id": 1}]
        assert cache.get("k2") is None  # Evicted
        assert cache.get("k3") == [{"id": 3}]
        assert cache.get("k4") == [{"id": 4}]

    def test_ttl_expiration(self):
        cache = Tier0ExactCache(max_size=10, ttl_seconds=0.05, redis_url=None)
        key = "rag:exact:expire_test"
        cache.set(key, [{"id": 100}], ttl_seconds=0.05)

        # Immediate fetch succeeds
        assert cache.get(key) == [{"id": 100}]

        # Wait for expiration
        time.sleep(0.07)
        assert cache.get(key) is None

    def test_default_instance_ttl_used(self):
        # When ttl_seconds is omitted in set(), instance ttl_seconds should be used
        cache = Tier0ExactCache(max_size=10, ttl_seconds=0.05, redis_url=None)
        key = "rag:exact:instance_ttl_test"
        cache.set(key, [{"id": 200}])  # No ttl_seconds passed

        assert cache.get(key) == [{"id": 200}]
        time.sleep(0.07)
        assert cache.get(key) is None

    def test_concurrency_thread_safety(self):
        cache = Tier0ExactCache(max_size=500, ttl_seconds=300.0, redis_url=None)

        def worker(thread_id: int):
            for i in range(50):
                k = f"rag:exact:worker_{thread_id}_{i % 10}"
                cache.set(k, [{"thread": thread_id, "i": i}])
                res = cache.get(k)
                assert res is not None

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(worker, tid) for tid in range(16)]
            for f in futures:
                f.result()

        stats = cache.get_stats()
        assert stats["hits"] > 0
        assert stats["l0_size"] <= 500

    def test_redis_ttl_inheritance(self):
        cache = Tier0ExactCache(max_size=10, ttl_seconds=3600.0, redis_url=None)
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe
        # Simulate Redis returning data with 45s remaining TTL
        mock_pipe.execute.return_value = [json.dumps([{"id": 42}]), 45]
        cache._redis = mock_redis

        res = cache.get("rag:exact:redis_key")
        assert res == [{"id": 42}]
        assert "rag:exact:redis_key" in cache._store
        stored_results, expire_at = cache._store["rag:exact:redis_key"]
        # Verify L0 TTL was set to ~45s, NOT the full 3600s
        time_left = expire_at - time.monotonic()
        assert 40 <= time_left <= 46

    def test_clear_method_ram_and_redis(self):
        cache = Tier0ExactCache(max_size=10, ttl_seconds=3600.0, redis_url=None)
        cache.set("k1", [{"id": 1}])
        cache.set("k2", [{"id": 2}])
        assert len(cache._store) == 2

        cache.clear()
        assert len(cache._store) == 0
        assert cache.get("k1") is None

        # Test Redis clear mocking
        mock_redis = MagicMock()
        mock_redis.scan.side_effect = [(10, ["rag:exact:abc", "rag:exact:def"]), (0, ["rag:exact:xyz"])]
        cache._redis = mock_redis
        cache.clear()
        assert mock_redis.delete.call_count == 2


class TestTier0SearchPipelineIntegration:
    def test_tier0_cache_hit_bypasses_embedding(self):
        tier0 = get_tier0_cache()
        tier0.clear()

        raw_query = "quy định chiều cao phòng cháy"
        exact_key = compute_sha256_cache_key(raw_query, filter_expr=None, limit=5, use_reranker=True)
        cached_result = [{"text": "Điều 5", "score": 0.99, "source": "06_2022_QCVN"}]
        tier0.set(exact_key, cached_result)

        milvus = MagicMock()
        neo4j = MagicMock()
        pipeline = SearchPipeline(milvus, neo4j)

        with patch("retrieval.search_pipeline.get_embedding_model") as mock_get_emb:
            mock_emb_model = MagicMock()
            mock_get_emb.return_value = mock_emb_model

            ctx = SearchContext(raw_query=raw_query, limit=5, use_reranker=True, use_cache=True)
            res = asyncio.run(pipeline.execute(ctx))

            assert res["cached"] is True
            assert res["results"] == cached_result
            assert res["search_grounding_triggered"] is False
            # Crucial assertion: embedding was completely bypassed
            assert not mock_emb_model.embed_query.called

        tier0.clear()

    def test_semantic_cache_hit_populates_tier0(self):
        tier0 = get_tier0_cache()
        semantic = get_semantic_cache()
        tier0.clear()
        semantic.clear()

        raw_query = "quy chuẩn xây dựng nhà chung cư"
        exact_key = compute_sha256_cache_key(raw_query, filter_expr=None, limit=5, use_reranker=True)
        dummy_emb = np.array([0.1] * 1024, dtype=np.float32)
        cached_result = [{"text": "Điều 10", "score": 0.95, "source": "04_2021_QCVN"}]

        # Seed semantic cache
        semantic.set(raw_query, dummy_emb, cached_result)

        milvus = MagicMock()
        neo4j = MagicMock()
        pipeline = SearchPipeline(milvus, neo4j)

        with patch("retrieval.search_pipeline.get_embedding_model") as mock_get_emb:
            mock_emb_model = MagicMock()
            mock_emb_model.embed_query.return_value = {"dense": dummy_emb.tolist(), "sparse": {}}
            mock_get_emb.return_value = mock_emb_model

            # First run: semantic cache hit -> populates Tier 0
            ctx1 = SearchContext(raw_query=raw_query, limit=5, use_reranker=True, use_cache=True)
            res1 = asyncio.run(pipeline.execute(ctx1))
            assert res1["cached"] is True
            assert res1["results"] == cached_result
            assert mock_emb_model.embed_query.call_count == 1

            # Verify Tier 0 is now populated
            assert tier0.get(exact_key) == cached_result

            # Second run: Tier 0 exact cache hit -> embedding call count stays 1 (bypassed)
            ctx2 = SearchContext(raw_query=raw_query, limit=5, use_reranker=True, use_cache=True)
            res2 = asyncio.run(pipeline.execute(ctx2))
            assert res2["cached"] is True
            assert res2["results"] == cached_result
            assert mock_emb_model.embed_query.call_count == 1  # Not incremented!

        tier0.clear()
        semantic.clear()


class TestBGEM3HybridLock:
    def test_bge_m3_hybrid_has_lock(self):
        import importlib.util
        import sys
        import types
        from pathlib import Path

        # Load real module directly, bypassing conftest stub
        module_path = Path(__file__).resolve().parents[1] / "retrieval" / "embeddings" / "bge_m3_hybrid.py"
        spec = importlib.util.spec_from_file_location("bge_m3_hybrid_real", str(module_path))
        real_mod = importlib.util.module_from_spec(spec)

        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([[0.1, 0.2]]),
            "lexical_weights": [{"1": 0.5}],
        }
        mock_fe = types.ModuleType("FlagEmbedding")
        mock_fe.BGEM3FlagModel = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"FlagEmbedding": mock_fe}):
            spec.loader.exec_module(real_mod)
            emb = real_mod.BGE_M3_HybridEmbedding()
            assert hasattr(emb, "_lock")
            assert hasattr(emb._lock, "__enter__")
            assert hasattr(emb._lock, "__exit__")

            # Test encode uses lock
            res = emb.encode(["test text"])
            assert len(res) == 1
            assert "dense" in res[0]
            assert "sparse" in res[0]

            # Test embed_documents uses lock
            doc_res = emb.embed_documents(["doc 1"])
            assert "dense" in doc_res
            assert doc_res["sparse"] == [{1: 0.5}]

            # Test embed_query uses lock
            query_res = emb.embed_query("query 1")
            assert "dense" in query_res
            assert query_res["sparse"] == {1: 0.5}


class TestRAGRouterImport:
    def test_rag_router_get_embedding_import(self):
        from ingestion.rag_router import RAGRouter
        router = RAGRouter(gateway_client=MagicMock())
        with patch("retrieval.search_pipeline.get_embedding_model") as mock_get_emb:
            mock_model = MagicMock()
            mock_model.embed_query.return_value = {"dense": [0.1, 0.2, 0.3]}
            mock_get_emb.return_value = mock_model

            dense = router.get_embedding("Tiêu chuẩn PCCC")
            assert dense == [0.1, 0.2, 0.3]
