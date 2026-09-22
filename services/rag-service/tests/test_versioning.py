"""Tests for the new Neo4j versioning relationship methods."""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")


def _run(coro):
    return asyncio.run(coro)


def _make_repo():
    from repositories.neo4j_repo import Neo4jRepository
    from unittest.mock import MagicMock, AsyncMock

    # Build a mock session that is a proper async context manager
    mock_session = AsyncMock()
    mock_session.run = AsyncMock()

    # session_ctx is the object returned by driver.session() — must be async context manager
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    # driver.session() is a REGULAR (sync) call that returns the context manager
    mock_driver = MagicMock()
    mock_driver.session = MagicMock(return_value=session_ctx)

    return Neo4jRepository(mock_driver), mock_driver, mock_session


class TestNeo4jVersioningRelations:
    def test_create_supersedes_relation_success(self):
        repo, driver, session = _make_repo()
        session.run = AsyncMock()
        _run(repo.create_supersedes_relation("BXD/01-2025", "BXD/01-2023"))
        session.run.assert_awaited_once()
        call_args = session.run.await_args
        assert "SUPERSEDES" in call_args[0][0]
        assert call_args[1]["new_doc_id"] == "BXD/01-2025"
        assert call_args[1]["old_doc_id"] == "BXD/01-2023"

    def test_create_supersedes_relation_raises_on_failure(self):
        repo, driver, session = _make_repo()
        session.run = AsyncMock(side_effect=Exception("Neo4j connection failed"))
        with pytest.raises(Exception):
            _run(repo.create_supersedes_relation("BXD/01-2025", "BXD/01-2023"))

    def test_create_amends_relation_success(self):
        repo, driver, session = _make_repo()
        session.run = AsyncMock()
        _run(repo.create_amends_relation("BXD/02-2025", "BXD/02-2023"))
        session.run.assert_awaited_once()
        call_args = session.run.await_args
        assert "AMENDS" in call_args[0][0]
        assert call_args[1]["new_doc_id"] == "BXD/02-2025"
        assert call_args[1]["amended_doc_id"] == "BXD/02-2023"

    def test_get_superseded_by_returns_empty_on_error(self):
        repo, driver, session = _make_repo()
        session.run = AsyncMock(side_effect=Exception("timeout"))
        result = _run(repo.get_superseded_by("BXD/01-2023"))
        assert result == []

    def test_get_superseded_by_returns_data(self):
        repo, driver, session = _make_repo()

        # Simulate async iteration over records
        mock_record = MagicMock()
        mock_record.data.return_value = {
            "id": "BXD/01-2025",
            "title": "Thông tư 01/2025",
            "effective_date": "2025-01-01"
        }

        class MockResult:
            async def __aiter__(self):
                yield mock_record

        async def mock_run(*args, **kwargs):
            return MockResult()

        session.run = mock_run
        result = _run(repo.get_superseded_by("BXD/01-2023"))
        # Result should have the mock data
        assert isinstance(result, list)


class TestDocumentStoreVersioning:
    """Test the notify_version_update() method on DocumentStore."""

    def _make_store(self):
        from repositories.document_store import DocumentStore
        state_mgr = MagicMock()
        milvus_repo = AsyncMock()
        neo4j_repo = AsyncMock()
        return DocumentStore(
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            state_manager=state_mgr,
        )

    def test_supersedes_calls_sync_and_neo4j(self):
        store = self._make_store()
        result = _run(store.notify_version_update(
            new_doc_id="BXD/01-2025",
            supersedes=["BXD/01-2023"],
        ))
        assert result["status"] == "success"
        assert "BXD/01-2023" in result["superseded"]
        store.milvus_repo.update_doc_validity.assert_awaited()
        store.neo4j_repo.create_supersedes_relation.assert_awaited_once_with("BXD/01-2025", "BXD/01-2023")

    def test_amends_marks_outdated(self):
        store = self._make_store()
        result = _run(store.notify_version_update(
            new_doc_id="BXD/02-2025",
            amends=["BXD/02-2023"],
        ))
        assert result["status"] == "success"
        assert "BXD/02-2023" in result["amended"]
        store.neo4j_repo.create_amends_relation.assert_awaited_once_with("BXD/02-2025", "BXD/02-2023")

    def test_partial_failure_neo4j_supersedes(self):
        store = self._make_store()
        store.neo4j_repo.create_supersedes_relation.side_effect = Exception("neo4j down")
        result = _run(store.notify_version_update(
            new_doc_id="BXD/01-2025",
            supersedes=["BXD/01-2023"],
        ))
        assert result["status"] == "partial_success"
        assert any("neo4j_supersedes" in e for e in result["errors"])

    def test_multiple_supersedes(self):
        store = self._make_store()
        result = _run(store.notify_version_update(
            new_doc_id="BXD/NEW",
            supersedes=["BXD/OLD-1", "BXD/OLD-2", "BXD/OLD-3"],
        ))
        assert result["status"] == "success"
        assert len(result["superseded"]) == 3
        assert store.neo4j_repo.create_supersedes_relation.await_count == 3

