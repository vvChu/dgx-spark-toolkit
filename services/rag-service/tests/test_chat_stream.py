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
        with patch("services.chat_service.ChatService.stream_response") as mock_stream:
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

    def test_chat_service_stream_response_with_mock_ai_gateway(self):
        """Test ChatService.stream_response directly with MockAIGatewayClient."""
        import asyncio
        import json
        from core.ai_gateway_client import MockAIGatewayClient, StreamChunk
        from services.chat_service import ChatService

        async def _test():
            mock_milvus = MagicMock()
            mock_neo4j = MagicMock()
            mock_neo4j.driver = None
            mock_http = AsyncMock()

            custom_chunks = [
                StreamChunk(text="Phân tích câu hỏi...", is_thought=True),
                StreamChunk(text="Căn cứ Điều 10...", is_thought=False),
            ]
            mock_ai_client = MockAIGatewayClient()

            # Patch retrieval search to return dummy hit
            chat_service = ChatService(
                milvus_repo=mock_milvus,
                neo4j_repo=mock_neo4j,
                http_client=mock_http,
                ai_client=mock_ai_client,
            )

            with patch.object(chat_service.retrieval_service, "search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = {
                    "results": [{"doc_number": "QCVN 06:2022", "page": 1, "text": "Quy định an toàn cháy", "score": 0.95}],
                    "trace": {},
                }
                with patch.object(mock_ai_client, "stream") as mock_stream:
                    async def _stream_gen(*args, **kwargs):
                        for chunk in custom_chunks:
                            yield chunk

                    mock_stream.side_effect = _stream_gen

                    events = []
                    async for sse_line in chat_service.stream_response(query="Quy định an toàn cháy?", language="vi"):
                        events.append(sse_line)

                    # Verify events emitted
                    assert len(events) >= 4  # context event, thought event, token event, trace event, [DONE]
                    event_types = []
                    for ev in events:
                        if ev.startswith("data: ") and not ev.startswith("data: [DONE]"):
                            data_str = ev[6:].strip()
                            parsed = json.loads(data_str)
                            event_types.append(parsed.get("type"))

                    assert "context" in event_types
                    assert "thought" in event_types
                    assert "token" in event_types
                    assert "trace" in event_types

        asyncio.run(_test())

