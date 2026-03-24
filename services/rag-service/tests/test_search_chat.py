from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from core.database import get_http_client, get_milvus_repo, get_neo4j_repo, get_retrieval_service, get_chat_service
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

    async def _override_retrieval():
        return fake_service

    app.dependency_overrides[get_retrieval_service] = _override_retrieval

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

    fake_service = AsyncMock()
    fake_service.search.return_value = {"results": [], "cached": False}

    async def _override_retrieval():
        return fake_service

    app.dependency_overrides[get_retrieval_service] = _override_retrieval

    response = client.post("/search", json={"limit": 3})

    assert response.status_code == 422


def test_chat_endpoint_success(client):
    _install_router_overrides()

    fake_chat_service = AsyncMock()
    fake_chat_service.generate_response.return_value = {
        "answer": "generated answer",
        "context": [{"text": "chunk text", "page": 1, "bbox": [1, 2, 3, 4], "doc_number": "01/2024/QD-TTg"}],
        "usage": None,
        "cached": False
    }

    async def _override_chat():
        return fake_chat_service

    app.dependency_overrides[get_chat_service] = _override_chat

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
    fake_chat_service.generate_response.assert_awaited_once()


def test_chat_endpoint_server_error(client):
    _install_router_overrides()

    async def _override_chat_error():
        raise RuntimeError("boom")

    app.dependency_overrides[get_chat_service] = _override_chat_error

    # Use raise_server_exceptions=False so the global exception handler
    # returns a JSON 500 instead of re-raising through TestClient.
    no_raise_client = TestClient(app, raise_server_exceptions=False)

    response = no_raise_client.post("/chat", json={"query": "anything"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
