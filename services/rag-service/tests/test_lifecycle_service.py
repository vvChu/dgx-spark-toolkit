"""Unit tests for services.lifecycle_service.LifecycleService."""
import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_service():
    from services.lifecycle_service import LifecycleService

    state_mgr = MagicMock()
    milvus_repo = AsyncMock()
    neo4j_repo = AsyncMock()
    return LifecycleService(state_mgr, milvus_repo, neo4j_repo)


class TestLifecycleService:
    def test_sync_all_success(self):
        svc = _make_service()
        result = _run(svc.sync_document_status("BXD/01-2024", "OUTDATED"))
        assert result["status"] == "success"
        svc.state_manager.update_validity_status.assert_called_once_with("BXD/01-2024", "OUTDATED")
        svc.milvus_repo.update_doc_validity.assert_awaited_once()
        svc.neo4j_repo.update_node_status.assert_awaited_once()

    def test_partial_failure_postgres(self):
        svc = _make_service()
        svc.state_manager.update_validity_status.side_effect = Exception("DB down")
        result = _run(svc.sync_document_status("BXD/01-2024", "ACTIVE"))
        assert result["status"] == "partial_success"
        assert len(result["errors"]) == 1
        assert "Postgres" in result["errors"][0]

    def test_partial_failure_milvus(self):
        svc = _make_service()
        svc.milvus_repo.update_doc_validity.side_effect = Exception("Milvus timeout")
        result = _run(svc.sync_document_status("BXD/01-2024", "REPLACED"))
        assert result["status"] == "partial_success"
        assert any("Milvus" in e for e in result["errors"])
        # Neo4j should still have been called
        svc.neo4j_repo.update_node_status.assert_awaited_once()

    def test_all_stores_fail(self):
        svc = _make_service()
        svc.state_manager.update_validity_status.side_effect = Exception("pg")
        svc.milvus_repo.update_doc_validity.side_effect = Exception("mv")
        svc.neo4j_repo.update_node_status.side_effect = Exception("n4j")
        result = _run(svc.sync_document_status("X/Y", "OUTDATED"))
        assert result["status"] == "partial_success"
        assert len(result["errors"]) == 3
