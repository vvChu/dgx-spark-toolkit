from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.database import get_http_client, get_milvus_repo, get_neo4j_repo
from main import app


async def _override_milvus_repo():
    return object()


async def _override_neo4j_repo():
    return object()


async def _override_http_client():
    return AsyncMock()


def _install_router_overrides():
    app.dependency_overrides[get_milvus_repo] = _override_milvus_repo
    app.dependency_overrides[get_neo4j_repo] = _override_neo4j_repo
    app.dependency_overrides[get_http_client] = _override_http_client


def test_search_endpoint_success(client):
    _install_router_overrides()

    fake_service = AsyncMock()
    fake_service.search.return_value = {
        "results": [{"text": "hello", "page": 1, "bbox": [0, 0, 10, 10]}],
        "cached": False,
    }

    with patch("api.routers.search.RetrievalService", return_value=fake_service):
        response = client.post(
            "/search",
            json={"query": "quy chuẩn phòng cháy", "limit": 3, "use_hyde": False, "use_cache": False},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["text"] == "hello"
    fake_service.search.assert_awaited_once()


def test_search_endpoint_validation_error(client):
    _install_router_overrides()

    response = client.post("/search", json={"limit": 3})

    assert response.status_code == 422


def test_chat_endpoint_success(client):
    _install_router_overrides()

    fake_service = AsyncMock()
    fake_service.search.return_value = {
        "results": [{"text": "chunk text", "page": 1, "bbox": [1, 2, 3, 4], "doc_number": "01/2024/QD-TTg"}]
    }
    fake_http_client = AsyncMock()
    fake_http_client.post.return_value = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "choices": [{"message": {"content": "generated answer"}}],
            "usage": {"total_tokens": 12},
        },
    )
    app.dependency_overrides[get_http_client] = lambda: fake_http_client

    with patch("api.routers.chat.RetrievalService", return_value=fake_service), \
         patch("api.routers.chat.rewrite_query", new=AsyncMock(return_value="rewritten query")), \
         patch("api.routers.chat.get_system_prompt", return_value="system prompt"), \
         patch("api.routers.chat.get_settings", return_value=SimpleNamespace(VLLM_MODEL="rag-light", VLLM_API_BASE="http://gateway", LITELLM_MASTER_KEY=SimpleNamespace(get_secret_value=lambda: "sk-test"))):
        response = client.post(
            "/chat",
            json={
                "query": "Tóm tắt quy định",
                "history": [{"role": "user", "content": "old"}],
                "language": "vi",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "generated answer"
    assert body["context"][0]["doc_number"] == "01/2024/QD-TTg"


def test_chat_endpoint_server_error(client):
    _install_router_overrides()

    with patch("api.routers.chat.RetrievalService", side_effect=RuntimeError("boom")):
        response = client.post("/chat", json={"query": "anything"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"