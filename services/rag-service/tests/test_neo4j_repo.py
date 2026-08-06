"""Unit tests for repositories.neo4j_repo.Neo4jRepository."""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from repositories.neo4j_repo import Neo4jRepository


def _run(coro):
    return asyncio.run(coro)


class _MockResult:
    def __init__(self, records):
        self._records = list(records)

    def __aiter__(self):
        return _MockResultIter(list(self._records))

    async def single(self):
        return self._records[0] if self._records else None


class _MockResultIter:
    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._records:
            raise StopAsyncIteration
        return self._records.pop(0)


class _MockRecord:
    def __init__(self, d):
        self._d = d

    def data(self):
        return self._d


class _MockSession:
    def __init__(self):
        self.run = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_repo():
    driver = MagicMock()
    session = _MockSession()
    driver.session.return_value = session
    repo = Neo4jRepository(driver)
    return repo, session


class TestNeo4jRepository:
    def test_driver_property(self):
        driver = MagicMock()
        repo = Neo4jRepository(driver)
        assert repo.driver is driver

    def test_get_document_relations_success(self):
        repo, session = _make_repo()
        session.run.return_value = _MockResult([
            _MockRecord({"id": "TT/123", "status": "ACTIVE", "out_rels": ["REPLACES"], "targets": [], "in_rels": [], "sources": []})
        ])
        results = _run(repo.get_document_relations("TT/123"))
        assert len(results) == 1
        assert results[0]["id"] == "TT/123"

    def test_get_document_relations_exception(self):
        repo, session = _make_repo()
        session.run.side_effect = Exception("boom")
        results = _run(repo.get_document_relations("TT/123"))
        assert results == []

    def test_find_document_status_success(self):
        repo, session = _make_repo()
        session.run.return_value = _MockResult([
            _MockRecord({"id": "A", "status": "ACTIVE"}),
            _MockRecord({"id": "B", "status": "OUTDATED"}),
        ])
        m = _run(repo.find_document_status(["A", "B"]))
        assert m == {"A": "ACTIVE", "B": "OUTDATED"}

    def test_find_document_status_exception(self):
        repo, session = _make_repo()
        session.run.side_effect = Exception("err")
        assert _run(repo.find_document_status(["A"])) == {}

    def test_update_node_status_success(self):
        repo, session = _make_repo()
        session.run.return_value = None
        _run(repo.update_node_status("TT/1", "OUTDATED"))
        session.run.assert_called_once()

    def test_update_node_status_exception(self):
        repo, session = _make_repo()
        session.run.side_effect = Exception("fail")
        with pytest.raises(Exception, match="fail"):
            _run(repo.update_node_status("TT/1", "OUTDATED"))

    def test_run_query_success(self):
        repo, session = _make_repo()
        session.run.return_value = _MockResult([_MockRecord({"cnt": 42})])
        results = _run(repo.run_query("MATCH (d) RETURN count(d) AS cnt"))
        assert results == [{"cnt": 42}]

    def test_run_query_exception(self):
        repo, session = _make_repo()
        session.run.side_effect = Exception("err")
        assert _run(repo.run_query("BAD")) == []

    def test_clear_db_refuses_without_confirm(self):
        repo, session = _make_repo()
        with pytest.raises(RuntimeError, match="refused"):
            _run(repo.clear_db(confirm=False))

    def test_clear_db_refuses_without_env(self):
        repo, session = _make_repo()
        os.environ.pop("ALLOW_DB_CLEAR", None)
        with pytest.raises(RuntimeError, match="refused"):
            _run(repo.clear_db(confirm=True))

    def test_clear_db_success(self):
        repo, session = _make_repo()
        session.run.return_value = None
        os.environ["ALLOW_DB_CLEAR"] = "1"
        try:
            _run(repo.clear_db(confirm=True))
            session.run.assert_called_once()
        finally:
            os.environ.pop("ALLOW_DB_CLEAR", None)
