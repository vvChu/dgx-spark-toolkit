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
    def test_init_schema(self):
        repo, session = _make_repo()
        _run(repo.init_schema())
        assert session.run.call_count == 2

    def test_close(self):
        from unittest.mock import AsyncMock
        driver = MagicMock()
        driver.close = AsyncMock()
        repo = Neo4jRepository(driver)
        _run(repo.close())
        driver.close.assert_called_once()

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

    def test_create_document_node_with_guides_and_relationships(self):
        repo, session = _make_repo()
        doc = MagicMock()
        doc.identity.doc_id = "TT/2025/BXD"
        doc.identity.doc_number = "01/2025/TT-BXD"
        doc.identity.file_name = "01_2025_TT-BXD.pdf"
        doc.identity.rel_path = "01_2025_TT-BXD.pdf"
        doc.metadata.doc_type = "TT"
        doc.metadata.authority = "BXD"
        doc.metadata.date = "2025-01-01"
        doc.metadata.validity_status = "ACTIVE"
        doc.relationships = {
            "replaces": ["TT/2020/BXD"],
            "amends": ["TT/2022/BXD"],
            "references": ["ND/2021/CP"],
            "guides": ["ND/2024/CP"],
        }

        _run(repo.create_document_node(doc))
        # 1 node MERGE + 4 relationship MERGE calls = 5 calls
        assert session.run.call_count == 5

        calls = session.run.call_args_list
        assert calls[0].kwargs["doc_id"] == "TT/2025/BXD"
        assert calls[0].kwargs["validity"] == "ACTIVE"

        guides_calls = [c for c in calls if "[:GUIDES]" in c.args[0]]
        assert len(guides_calls) == 1
        assert guides_calls[0].kwargs["source_id"] == "TT/2025/BXD"
        assert guides_calls[0].kwargs["target_id"] == "ND/2024/CP"

    def test_create_document_node_with_dataclass_relationships(self):
        from ingestion.models import DocumentRelationships
        repo, session = _make_repo()
        doc = MagicMock()
        doc.identity.doc_id = "TT/2026/BXD"
        doc.identity.doc_number = "02/2026/TT-BXD"
        doc.identity.file_name = "02_2026_TT-BXD.pdf"
        doc.identity.rel_path = "02_2026_TT-BXD.pdf"
        doc.metadata.doc_type = "TT"
        doc.metadata.authority = "BXD"
        doc.metadata.date = "2026-01-01"
        doc.metadata.validity_status = "ACTIVE"
        doc.relationships = DocumentRelationships(
            guides=["Luat/50/2014/QH13"],
            references=["ND/15/2021/ND-CP"],
        )

        _run(repo.create_document_node(doc))
        # 1 node MERGE + 1 REFERENCES + 1 GUIDES = 3 calls
        assert session.run.call_count == 3
        guides_calls = [c for c in session.run.call_args_list if "[:GUIDES]" in c.args[0]]
        assert len(guides_calls) == 1
        assert guides_calls[0].kwargs["source_id"] == "TT/2026/BXD"
        assert guides_calls[0].kwargs["target_id"] == "Luat/50/2014/QH13"

    def test_create_document_node_with_none_and_whitespace_relationships(self):
        repo, session = _make_repo()
        doc = MagicMock()
        doc.identity.doc_id = "ND/2025/CP"
        doc.identity.doc_number = "15/2025/ND-CP"
        doc.identity.file_name = "15_2025_ND-CP.pdf"
        doc.identity.rel_path = "15_2025_ND-CP.pdf"
        doc.metadata.doc_type = "ND"
        doc.metadata.authority = "CP"
        doc.metadata.date = "2025-06-01"
        doc.metadata.validity_status = "ACTIVE"
        # None values and whitespace-padded IDs
        doc.relationships = {
            "replaces": None,
            "amends": ["  ND/10/2020/ND-CP  "],
            "references": ["", "  ", None],
            "guides": None,
        }

        # Should execute safely without raising TypeError
        _run(repo.create_document_node(doc))
        # 1 node MERGE + 1 amends MERGE = 2 calls
        assert session.run.call_count == 2
        amends_calls = [c for c in session.run.call_args_list if "[:AMENDS]" in c.args[0]]
        assert len(amends_calls) == 1
        assert amends_calls[0].kwargs["source_id"] == "ND/2025/CP"
        assert amends_calls[0].kwargs["target_id"] == "ND/10/2020/ND-CP"

    def test_get_document_relations_includes_guides_in_cypher(self):
        repo, session = _make_repo()
        session.run.return_value = _MockResult([
            _MockRecord({
                "id": "TT/123",
                "status": "ACTIVE",
                "out_rels": ["GUIDES"],
                "targets": ["ND/456"],
                "in_rels": [],
                "sources": [],
            })
        ])
        results = _run(repo.get_document_relations("TT/123"))
        assert len(results) == 1
        query_executed = session.run.call_args[0][0]
        assert "GUIDES" in query_executed

    def test_get_guided_circulars_traversal(self):
        repo, session = _make_repo()
        session.run.return_value = _MockResult([
            _MockRecord({"source": "ND/15/2021", "guided_id": "TT/01/2021/TT-BXD", "status": "ACTIVE"})
        ])
        results = _run(repo.get_guided_circulars("ND/15/2021"))
        assert len(results) == 1
        assert results[0]["guided_id"] == "TT/01/2021/TT-BXD"
        query_executed = session.run.call_args[0][0]
        assert "[:GUIDES|REFERENCES*1..2]" in query_executed

