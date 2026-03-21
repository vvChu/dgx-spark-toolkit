from unittest.mock import AsyncMock, Mock, patch

from core.database import (
    get_compliance_service,
    get_http_client,
    get_legal_analysis_service,
    get_milvus_repo,
    get_neo4j_repo,
    get_state_manager,
)
from main import app


class _FakeMilvusRepo:
    def __init__(self):
        self._client = AsyncMock()
        self._client.get_collection_stats = AsyncMock(return_value={"row_count": 42})


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


async def _override_milvus_repo():
    return _FakeMilvusRepo()


async def _override_neo4j_repo():
    return _FakeNeo4jRepo()


async def _override_http_client():
    return _FakeHttpClient(
        {
            "choices": [{"message": {"content": '{"faithfulness": 0.9, "relevancy": 0.8, "faithfulness_reason": "supported", "relevancy_reason": "relevant", "suggestions": ["none"]}'}}]
        }
    )


async def _override_state_manager():
    state_manager = Mock()
    state_manager.health_check.return_value = {"status": "healthy"}
    return state_manager


async def _override_legal_analysis_service():
    service = AsyncMock()
    service.analyze_conflicts.return_value = {"status": "ok", "conflicts": []}
    return service


async def _override_compliance_service():
    service = AsyncMock()
    service.check_compliance.return_value = {"status": "ok", "findings": []}
    return service


def _install_common_overrides():
    app.dependency_overrides[get_milvus_repo] = _override_milvus_repo
    app.dependency_overrides[get_neo4j_repo] = _override_neo4j_repo
    app.dependency_overrides[get_http_client] = _override_http_client
    app.dependency_overrides[get_state_manager] = _override_state_manager
    app.dependency_overrides[get_legal_analysis_service] = _override_legal_analysis_service
    app.dependency_overrides[get_compliance_service] = _override_compliance_service


def test_pipeline_health_endpoint(client):
    _install_common_overrides()

    # The refactored /health/pipeline reads singletons from app.state
    rq_mock = Mock()
    rq_mock.health_check.return_value = {"status": "healthy"}

    asm_mock = AsyncMock()
    asm_mock.health_check.return_value = {"status": "healthy"}
    asm_mock.get_status_summary.return_value = {"completed": 1}

    sm_mock = Mock()
    sm_mock.health_check.return_value = {"status": "healthy"}

    app.state.redis_queue = rq_mock
    app.state.async_state_manager = asm_mock
    app.state.state_manager = sm_mock

    try:
        response = client.get("/health/pipeline")
    finally:
        # Clean up app.state to avoid leaking into other tests
        for attr in ("redis_queue", "async_state_manager", "state_manager"):
            if hasattr(app.state, attr):
                delattr(app.state, attr)

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_status"] == "healthy"
    assert body["checks"]["redis_queue"]["status"] == "healthy"


def test_stats_endpoint(client):
    _install_common_overrides()

    response = client.get("/stats")

    assert response.status_code == 200
    assert response.json() == {
        "neo4j_docs": 7,
        "neo4j_rels": 3,
        "milvus_entities": 42,
        "total_target": 8870,
    }


def test_graph_data_endpoint(client):
    _install_common_overrides()

    response = client.get("/graph/data?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    assert body["links"][0]["type"] == "REFERENCES"


def test_graph_neighbors_endpoint(client):
    _install_common_overrides()

    response = client.get("/graph/neighbors/doc-1")

    assert response.status_code == 200
    body = response.json()
    assert body["nodes"][0]["id"] == "doc-2"
    assert body["links"][0]["type"] == "AMENDS"


def test_feedback_endpoint(client):
    response = client.post(
        "/feedback",
        json={
            "query": "test query",
            "answer": "test answer",
            "is_positive": True,
            "comment": "helpful",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_evaluate_endpoint(client):
    _install_common_overrides()

    response = client.post(
        "/evaluate",
        json={
            "query": "What does the law say?",
            "answer": "It says X",
            "context": ["ctx-1", "ctx-2"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["faithfulness"] == 0.9
    assert body["relevancy"] == 0.8


def test_admin_sync_status_endpoint(client):
    _install_common_overrides()

    with patch("api.routers.admin.LifecycleService") as service_cls:
        service = AsyncMock()
        service.sync_document_status.return_value = {"status": "ok", "doc_id": "doc-1", "new_status": "ACTIVE", "updates": {}}
        service_cls.return_value = service

        response = client.post(
            "/admin/sync-status",
            json={"doc_id": "doc-1", "new_status": "ACTIVE"},
            headers={"X-Admin-Key": "test-admin-key-for-ci"},
        )

    assert response.status_code == 200
    assert response.json()["doc_id"] == "doc-1"


def test_analysis_endpoints(client):
    _install_common_overrides()

    conflict_response = client.post(
        "/analysis/conflict",
        json={"doc_id": "doc-1", "query": "fire safety", "depth": 2},
    )
    compliance_response = client.post(
        "/analysis/compliance",
        json={"project_profile": "tower", "focus_area": "BIM"},
    )

    assert conflict_response.status_code == 200
    assert conflict_response.json()["status"] == "ok"
    assert compliance_response.status_code == 200
    assert compliance_response.json()["status"] == "ok"