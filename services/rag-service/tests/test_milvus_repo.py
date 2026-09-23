"""Unit tests for repositories.milvus_repo.MilvusRepository."""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from repositories.milvus_repo import MilvusRepository, _sanitize_pid


def _run(coro):
    return asyncio.run(coro)


class TestSanitizePid:
    def test_strips_unsafe_chars(self):
        assert _sanitize_pid('hello"world') == "helloworld"
        assert _sanitize_pid("ab\\cd") == "abcd"

    def test_leaves_safe_chars(self):
        assert _sanitize_pid("TT/123-2024") == "TT/123-2024"


class TestMilvusRepository:
    def _make_repo(self):
        client = AsyncMock()
        repo = MilvusRepository(client)
        return repo, client

    def test_hybrid_search(self):
        repo, client = self._make_repo()
        client.hybrid_search = AsyncMock(return_value=[[MagicMock(score=0.9)]])
        results = _run(repo.hybrid_search([0.1] * 1024, {}, limit=5))
        assert len(results[0]) == 1
        client.hybrid_search.assert_called_once()

    def test_hybrid_search_sparse_fallback(self):
        repo, client = self._make_repo()
        client.hybrid_search = AsyncMock(side_effect=Exception("fieldName(sparse_vector) not found"))
        client.search = AsyncMock(return_value=[[MagicMock(score=0.85)]])
        results = _run(repo.hybrid_search([0.1] * 1024, {}, limit=5))
        assert len(results[0]) == 1
        client.search.assert_called_once()

    def test_get_parent_chunks_empty(self):
        repo, client = self._make_repo()
        results = _run(repo.get_parent_chunks([]))
        assert results == []
        client.query.assert_not_called()

    def test_get_parent_chunks_with_ids(self):
        repo, client = self._make_repo()
        client.query = AsyncMock(return_value=[{"parent_id": "p1", "text": "parent text"}])
        results = _run(repo.get_parent_chunks(["p1"]))
        assert len(results) == 1
        assert results[0]["text"] == "parent text"

    def test_cache_search_hit(self):
        repo, client = self._make_repo()
        hit = MagicMock()
        hit.score = 0.99
        hit.entity = MagicMock()
        hit.entity.get.return_value = "cached answer"
        client.search = AsyncMock(return_value=[[hit]])
        answer, score = _run(repo.cache_search([0.1] * 1024, threshold=0.98))
        assert answer == "cached answer"
        assert score == 0.99

    def test_cache_search_miss(self):
        repo, client = self._make_repo()
        hit = MagicMock()
        hit.score = 0.5
        hit.entity = MagicMock()
        hit.entity.get.return_value = None
        client.search = AsyncMock(return_value=[[hit]])
        answer, score = _run(repo.cache_search([0.1] * 1024, threshold=0.98))
        assert answer is None

    def test_cache_search_exception(self):
        repo, client = self._make_repo()
        client.search = AsyncMock(side_effect=Exception("err"))
        answer, score = _run(repo.cache_search([0.1] * 1024))
        assert answer is None

    def test_update_doc_validity(self):
        repo, client = self._make_repo()
        client.query = AsyncMock(return_value=[{"doc_id": "A", "validity_status": "ACTIVE"}])
        client.upsert = AsyncMock()
        _run(repo.update_doc_validity("A", "OUTDATED"))
        client.upsert.assert_called_once()

    def test_update_doc_validity_no_chunks(self):
        repo, client = self._make_repo()
        client.query = AsyncMock(return_value=[])
        client.upsert = AsyncMock()
        _run(repo.update_doc_validity("X", "OUTDATED"))
        client.upsert.assert_not_called()

    def test_update_doc_validity_exception(self):
        repo, client = self._make_repo()
        client.query = AsyncMock(side_effect=Exception("err"))
        with pytest.raises(Exception, match="err"):
            _run(repo.update_doc_validity("A", "BAD"))

    def test_get_collection_stats(self):
        repo, client = self._make_repo()
        client.get_collection_stats = AsyncMock(return_value={"row_count": 42})
        result = _run(repo.get_collection_stats())
        assert result["row_count"] == 42

    def test_get_collection_stats_custom_collection(self):
        repo, client = self._make_repo()
        client.get_collection_stats = AsyncMock(return_value={"row_count": 10})
        result = _run(repo.get_collection_stats("other_collection"))
        client.get_collection_stats.assert_called_with("other_collection")

    def test_ensure_collection_schema(self):
        repo, client = self._make_repo()
        client.has_collection = AsyncMock(return_value=False)
        client.create_collection = AsyncMock()
        res = _run(repo.ensure_collection_schema())
        assert res is True
        client.create_collection.assert_called_once()

    def test_close(self):
        repo, client = self._make_repo()
        client.close = AsyncMock()
        _run(repo.close())
        client.close.assert_called_once()
