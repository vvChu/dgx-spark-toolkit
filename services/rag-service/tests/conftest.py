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


# ── Fake Repository Classes (for FastAPI DI overrides) ────────────────
# These are concrete implementations that match repository interfaces,
# used by test_endpoints.py for dependency injection overrides.

class _FakeMilvusRepo:
    def __init__(self):
        from unittest.mock import AsyncMock
        self._client = AsyncMock()
        self._client.get_collection_stats = AsyncMock(return_value={"row_count": 42})

    async def get_collection_stats(self, collection=None):
        return {"row_count": 42}


class _FakeNeo4jResult:
    def __init__(self, records):
        self._records = list(records)
        self._idx = 0

    async def single(self):
        return self._records[0] if self._records else None

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._records):
            raise StopAsyncIteration
        value = self._records[self._idx]
        self._idx += 1
        return value


class _FakeNeo4jSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def run(self, query, **kwargs):
        if "count(d) AS docs" in query:
            return _FakeNeo4jResult([{"docs": 7}])
        if "count(r) AS rels" in query:
            return _FakeNeo4jResult([{"rels": 3}])
        if "RETURN d.doc_id AS id" in query:
            return _FakeNeo4jResult([
                {"id": "doc-1", "name": "Doc 1", "group": "QD"},
                {"id": "doc-2", "name": None, "group": None},
            ])
        if "RETURN a.doc_id AS source" in query:
            return _FakeNeo4jResult([
                {"source": "doc-1", "target": "doc-2", "type": "REFERENCES"},
            ])
        if "MATCH (d:Document {doc_id: $node_id})-[r]-(n:Document)" in query:
            return _FakeNeo4jResult([
                {"id": "doc-2", "name": "Doc 2", "group": "TT", "rtype": "AMENDS", "src": kwargs["node_id"], "tgt": "doc-2"},
            ])
        return _FakeNeo4jResult([])


class _FakeNeo4jDriver:
    def session(self):
        return _FakeNeo4jSession()


class _FakeNeo4jRepo:
    def __init__(self):
        self._driver = _FakeNeo4jDriver()
        self._session = _FakeNeo4jSession()

    @property
    def driver(self):
        return self._driver

    async def run_query(self, cypher, **params):
        result = await self._session.run(cypher, **params)
        records = []
        async for r in result:
            records.append(r)
        return records


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpClient:
    def __init__(self, payload):
        self._payload = payload

    async def post(self, *args, **kwargs):
        return _FakeHttpResponse(self._payload)
