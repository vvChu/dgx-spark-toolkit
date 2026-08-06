"""Unit tests for api.routers.chat_stream — SSE streaming endpoint."""
import os
import sys
import types

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# CI stubs
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")
os.environ.setdefault("ADMIN_SECRET", "test-admin-key-for-ci")

_fake_mod = types.ModuleType("retrieval.embeddings.bge_m3_hybrid")


class _FakeEmb:
    def __init__(self, *a, **kw): pass


_fake_mod.BGE_M3_HybridEmbedding = _FakeEmb
sys.modules.setdefault("retrieval.embeddings.bge_m3_hybrid", _fake_mod)

from starlette.testclient import TestClient
from contextlib import asynccontextmanager
from core.database import get_milvus_repo, get_neo4j_repo, get_http_client
from main import app


@asynccontextmanager
async def _test_lifespan(_app):
    yield


app.router.lifespan_context = _test_lifespan


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _install_overrides():
    mock_milvus = MagicMock()
    mock_milvus.hybrid_search = AsyncMock(return_value=[])
    mock_milvus.get_parent_chunks = AsyncMock(return_value=[])

    mock_neo4j = MagicMock()
    mock_neo4j.driver = MagicMock()

    mock_http = AsyncMock()
    # Mock the stream context manager for SSE
    mock_stream_resp = AsyncMock()
    mock_stream_resp.raise_for_status = MagicMock()
    mock_stream_resp.aiter_lines = AsyncMock(return_value=iter([
        'data: {"type": "token", "data": "hello"}',
        'data: [DONE]',
    ]))

    async def _mock_milvus():
        return mock_milvus

    async def _mock_neo4j():
        return mock_neo4j

    async def _mock_http():
        return mock_http

    app.dependency_overrides[get_milvus_repo] = _mock_milvus
    app.dependency_overrides[get_neo4j_repo] = _mock_neo4j
    app.dependency_overrides[get_http_client] = _mock_http


class TestChatStream:
    def test_stream_endpoint_rejects_invalid_payload(self, client):
        """Missing required 'query' field should return 422."""
        _install_overrides()
        response = client.post("/chat/stream", json={"language": "vi"})
        assert response.status_code == 422

    def test_stream_endpoint_returns_event_stream(self, client):
        """Verify /chat/stream returns content-type text/event-stream and no-cache headers."""
        _install_overrides()

        # Mock the internal retrieval and streaming to avoid real LLM calls
        with patch("api.routers.chat_stream._stream_chat") as mock_stream:
            async def _fake_stream(*args, **kwargs):
                yield 'data: {"type": "token", "data": "hello"}\n\n'
                yield "data: [DONE]\n\n"

            mock_stream.return_value = _fake_stream()

            response = client.post(
                "/chat/stream",
                json={"query": "test query", "language": "vi"},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            assert response.headers.get("cache-control") == "no-cache"
            assert response.headers.get("x-accel-buffering") == "no"
