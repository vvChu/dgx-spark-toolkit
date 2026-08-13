"""Unit tests for retrieval.semantic_cache.SemanticCache and InMemorySemanticCache adapter."""
import numpy as np

from retrieval.semantic_cache import SemanticCache, InMemorySemanticCache


class TestSemanticCache:
    def test_l1_cache_hit_and_miss(self):
        cache = SemanticCache(threshold=0.9, ttl_seconds=3600.0)
        emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb2 = np.array([0.99, 0.01, 0.0], dtype=np.float32)
        emb_diff = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        cache.set("query 1", emb1, [{"id": 1}], filter_key="")

        # Miss before hit
        assert cache.get("diff query", emb_diff, filter_key="") is None

        # Hit
        res = cache.get("query 1 approx", emb2, filter_key="")
        assert res == [{"id": 1}]

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0

    def test_filter_key_masking(self):
        cache = SemanticCache(threshold=0.9)
        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        cache.set("doc query", emb, [{"doc": "A"}], filter_key="doc_number == 'ND87'")
        assert cache.get("doc query", emb, filter_key="doc_number == 'ND87'") == [{"doc": "A"}]
        assert cache.get("doc query", emb, filter_key="doc_number == 'ND88'") is None

    def test_hyde_cache_get_set(self):
        cache = SemanticCache()
        assert cache.get_hyde("QCVN 06:2022") is None

        cache.set_hyde("QCVN 06:2022", "Văn bản Quy chuẩn 06 về PCCC...")
        assert cache.get_hyde("QCVN 06:2022") == "Văn bản Quy chuẩn 06 về PCCC..."

    def test_in_memory_semantic_cache_adapter(self):
        cache = InMemorySemanticCache(default_results=[{"mock": True}])
        assert cache.get("query", np.array([])) is None

        cache.set("query", np.array([]), [{"id": 1}])
        assert cache.get("query", np.array([])) == [{"id": 1}]

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
