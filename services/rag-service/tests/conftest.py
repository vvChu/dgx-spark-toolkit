import os
import sys
import types
from contextlib import asynccontextmanager

# Set CI/test defaults so get_settings() doesn't crash when importing main.py
# outside Docker.  These are NOT real credentials — they only satisfy the
# @model_validator that rejects empty values.
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")
os.environ.setdefault("ADMIN_SECRET", "test-admin-key-for-ci")

# Stub the heavy embedding module before importing main.py.  This keeps tests
# independent from optional model/runtime package compatibility issues.
_fake_embedding_module = types.ModuleType("retrieval.embeddings.bge_m3_hybrid")


class _FakeEmbeddingModel:
    def __init__(self, *args, **kwargs):
        pass


_fake_embedding_module.BGE_M3_HybridEmbedding = _FakeEmbeddingModel
sys.modules.setdefault("retrieval.embeddings.bge_m3_hybrid", _fake_embedding_module)

import pytest
from starlette.testclient import TestClient
from main import app


@asynccontextmanager
async def _test_lifespan(_app):
    yield


app.router.lifespan_context = _test_lifespan

@pytest.fixture
def client():
    """TestClient wired to the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Keep FastAPI dependency overrides isolated per test."""
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


# ── Shared Mock Fixtures ────────────────────────────────────────────────
@pytest.fixture
def mock_milvus_repo():
    """A fully-mocked MilvusRepository."""
    from unittest.mock import AsyncMock, MagicMock
    repo = MagicMock()
    repo.hybrid_search = AsyncMock(return_value=[])
    repo.get_parent_chunks = AsyncMock(return_value=[])
    repo.count = MagicMock(return_value=0)
    return repo


@pytest.fixture
def mock_neo4j_repo():
    """A fully-mocked Neo4jRepository."""
    from unittest.mock import AsyncMock, MagicMock
    repo = MagicMock()
    repo.get_graph_data = AsyncMock(return_value={"nodes": [], "links": []})
    repo.find_document_status = AsyncMock(return_value={})
    repo.get_document_graph = AsyncMock(return_value={"nodes": [], "links": []})
    repo.driver = MagicMock()
    return repo


@pytest.fixture
def mock_state_manager():
    """A fully-mocked PostgresStateManager."""
    from unittest.mock import AsyncMock, MagicMock
    mgr = MagicMock()
    mgr.get_document_state = AsyncMock(return_value=None)
    mgr.update_document_state = AsyncMock(return_value=True)
    return mgr


@pytest.fixture
def admin_headers():
    """Headers with valid admin key for protected endpoints."""
    return {"X-Admin-Key": "test-admin-key-for-ci"}
