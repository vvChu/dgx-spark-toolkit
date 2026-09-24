"""Unit and integration tests for Container Startup Warmup (Resilient Architecture, Hardened v2).

Validates:
1. Hermetic Isolation: Tests run with 0s overhead without loading real ML models.
2. Warmup Success: Forced warmup initializes BGE-M3 and Reranker, health probe returns 200 OK.
3. Degraded Soft-Fail: Model failure sets failed state, returns 503, app does not crash.
4. Admin Recovery: POST /admin/warmup authentication, concurrency locking (409), and 200/503 responses.
5. Self-Healing: Late worker completion automatically transitions health status to 200 OK.
6. Disabled Config: WARMUP_ON_STARTUP=False skips warmup cleanly and maps to health 'ok'.
7. Lock Contention Stale State Prevention: In-progress response returned without stale failure state.
8. Admin In-Progress Conflict: 409 returned when perform_warmup returns in_progress.
9. Admin Concurrent Race: Rapid simultaneous requests return 200 and 409 without crashing.
10. Health Status Resilience: None or malformed app.state.warmup_status gracefully handled.
11. Test Environment Detection: All truthy boolean representations parsed correctly.
12. Lifespan Exception Soft-Fail: Unhandled exception during startup warmup does not abort server.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.config import get_settings
from core.warmup import (
    _warmup_thread_lock,
    is_test_environment,
    perform_warmup,
)
from main import app


def _run(coro):
    """Run an async coroutine to completion using asyncio.run."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _ensure_lock_released():
    """Ensure warmup lock is always released before and after every test."""
    if _warmup_thread_lock.locked():
        try:
            _warmup_thread_lock.release()
        except RuntimeError:
            pass
    yield
    if _warmup_thread_lock.locked():
        try:
            _warmup_thread_lock.release()
        except RuntimeError:
            pass


@pytest.fixture
def mock_db_connected():
    """Mock connected Milvus and Neo4j on app.state for health checks."""
    old_milvus = getattr(app.state, "milvus_client", None)
    old_neo4j = getattr(app.state, "neo4j_driver", None)
    old_warmup = getattr(app.state, "warmup_status", None)

    mock_milvus = MagicMock()
    mock_milvus.list_collections = AsyncMock(return_value=["col1"])

    mock_neo4j = MagicMock()
    mock_neo4j.verify_connectivity = AsyncMock(return_value=None)

    app.state.milvus_client = mock_milvus
    app.state.neo4j_driver = mock_neo4j

    yield

    app.state.milvus_client = old_milvus
    app.state.neo4j_driver = old_neo4j
    app.state.warmup_status = old_warmup if old_warmup else {"status": "skipped", "reason": "test_env"}


def test_is_test_environment():
    """Verify test environment detector returns True during pytest execution."""
    assert is_test_environment() is True


def test_hermetic_isolation(client, mock_db_connected):
    """Scenario 1: Default execution skips warmup with zero overhead (Hermetic Isolation)."""
    t0 = time.perf_counter()
    res = _run(perform_warmup(app, force=False))
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.05, f"Warmup check took too long: {elapsed:.4f}s"
    assert res["status"] == "skipped"
    assert res["reason"] == "test_env"
    assert app.state.warmup_status["status"] == "skipped"

    # Health check maps 'skipped' to 'ok'
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["warmup"] == "ok"
    assert body["warmup"]["status"] == "skipped"


def test_warmup_success_forced(client, mock_db_connected):
    """Scenario 2: Forced warmup with mocked models succeeds and marks warmup ready."""
    mock_emb = MagicMock()
    mock_emb.embed_query.return_value = {"dense": [0.1] * 1024, "sparse": {}}

    mock_reranker = MagicMock()
    mock_reranker.rerank_sync.return_value = [("warmup doc", 0.99)]

    with patch("retrieval.search_pipeline.get_embedding_model", return_value=mock_emb), \
         patch("retrieval.reranker.get_reranker", return_value=mock_reranker):
        res = _run(perform_warmup(app, timeout=5.0, force=True))

    assert res["status"] == "ready"
    assert "duration_seconds" in res
    assert app.state.warmup_status["status"] == "ready"
    mock_emb.embed_query.assert_called_once_with("warmup query")
    mock_reranker.rerank_sync.assert_called_once_with("warmup query", ["warmup doc"])

    # Health probe verifies 200 OK
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["warmup"] == "ok"
    assert body["warmup"]["status"] == "ready"


def test_warmup_degraded_soft_fail(client, mock_db_connected):
    """Scenario 3: Model warmup failure enters degraded mode without crashing FastAPI."""
    mock_emb = MagicMock()
    mock_emb.embed_query.return_value = {"dense": [0.1] * 1024, "sparse": {}}

    mock_reranker = MagicMock()
    mock_reranker.rerank_sync.side_effect = RuntimeError("CUDA out of memory")

    with patch("retrieval.search_pipeline.get_embedding_model", return_value=mock_emb), \
         patch("retrieval.reranker.get_reranker", return_value=mock_reranker):
        res = _run(perform_warmup(app, timeout=5.0, force=True))

    assert res["status"] == "failed"
    assert "CUDA out of memory" in res["error"]
    assert app.state.warmup_status["status"] == "failed"

    # Health probe returns 503 degraded
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert "failed: CUDA out of memory" in body["checks"]["warmup"]
    assert body["warmup"]["status"] == "failed"


def test_admin_warmup_endpoints(client, mock_db_connected):
    """Scenario 4: POST /admin/warmup auth, concurrency 409 conflict, and 200 recovery."""
    admin_secret = get_settings().ADMIN_SECRET.get_secret_value()
    headers = {"X-Admin-Key": admin_secret}

    # 1. Missing header returns 422, invalid secret returns 403
    resp = client.post("/admin/warmup")
    assert resp.status_code == 422

    resp = client.post("/admin/warmup", headers={"X-Admin-Key": "wrong-secret"})
    assert resp.status_code == 403

    # 2. Concurrency lock contention returns 409 Conflict
    _warmup_thread_lock.acquire()
    try:
        resp = client.post("/admin/warmup", headers=headers)
        assert resp.status_code == 409
        assert "Warmup is already in progress" in resp.json()["detail"]
    finally:
        _warmup_thread_lock.release()

    # 3. Successful warmup via admin endpoint
    mock_emb = MagicMock()
    mock_emb.embed_query.return_value = {"dense": [0.1] * 1024, "sparse": {}}
    mock_reranker = MagicMock()
    mock_reranker.rerank_sync.return_value = [("warmup doc", 0.99)]

    with patch("retrieval.search_pipeline.get_embedding_model", return_value=mock_emb), \
         patch("retrieval.reranker.get_reranker", return_value=mock_reranker):
        resp = client.post("/admin/warmup", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

    # 4. Failure via admin endpoint returns 503
    mock_fail_reranker = MagicMock()
    mock_fail_reranker.rerank_sync.side_effect = RuntimeError("VRAM allocation error")

    with patch("retrieval.search_pipeline.get_embedding_model", return_value=mock_emb), \
         patch("retrieval.reranker.get_reranker", return_value=mock_fail_reranker):
        resp = client.post("/admin/warmup", headers=headers)

    assert resp.status_code == 503
    assert resp.json()["status"] == "failed"


def test_warmup_timeout_and_self_healing(client, mock_db_connected):
    """Scenario 5: Warmup exceeding timeout yields in_progress, thread heals to ready."""
    async def _test():
        def slow_worker(*args, **kwargs):
            time.sleep(0.15)
            return {"dense": [0.1] * 1024, "sparse": {}}

        mock_emb = MagicMock()
        mock_emb.embed_query.side_effect = slow_worker
        mock_reranker = MagicMock()
        mock_reranker.rerank_sync.return_value = []

        with patch("retrieval.search_pipeline.get_embedding_model", return_value=mock_emb), \
             patch("retrieval.reranker.get_reranker", return_value=mock_reranker):
            res = await perform_warmup(app, timeout=0.04, force=True)
            assert res["status"] == "in_progress"

            # While running in thread, /health probe returns 503
            resp = client.get("/health")
            assert resp.status_code == 503
            assert resp.json()["checks"]["warmup"] == "in_progress"

            # Wait for background worker to complete
            await asyncio.sleep(0.20)

            # Self-healing: thread finished and updated app.state.warmup_status to 'ready'
            assert app.state.warmup_status["status"] == "ready"

            # Subsequent /health probe returns 200 OK
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["checks"]["warmup"] == "ok"
            assert resp.json()["warmup"]["status"] == "ready"

    _run(_test())


def test_warmup_disabled_configuration(client, mock_db_connected):
    """Scenario 6: WARMUP_ON_STARTUP=False disables warmup cleanly."""
    mock_settings = MagicMock()
    mock_settings.WARMUP_ON_STARTUP = False
    with patch("core.warmup.is_test_environment", return_value=False), \
         patch("core.config.get_settings", return_value=mock_settings):
        res = _run(perform_warmup(app, force=False))

    assert res["status"] == "disabled"
    assert res["reason"] == "config_disabled"

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["checks"]["warmup"] == "ok"
    assert resp.json()["warmup"]["status"] == "disabled"


def test_warmup_lock_contention_returns_in_progress_not_stale():
    """Scenario 7: When lock is held, perform_warmup returns in_progress without returning stale failed state."""
    app.state.warmup_status = {"status": "failed", "error": "Stale CUDA OOM from earlier"}
    _warmup_thread_lock.acquire()
    try:
        res = _run(perform_warmup(app, force=True))
        assert res["status"] == "in_progress"
        assert res["reason"] == "already_in_progress"
        # Confirm it did NOT return stale failed status
        assert res.get("status") != "failed"
    finally:
        _warmup_thread_lock.release()


def test_admin_warmup_in_progress_returns_409(client):
    """Scenario 8: If perform_warmup returns in_progress, admin endpoint returns 409 Conflict."""
    admin_secret = get_settings().ADMIN_SECRET.get_secret_value()
    headers = {"X-Admin-Key": admin_secret}

    with patch("core.warmup.perform_warmup", new=AsyncMock(return_value={"status": "in_progress", "reason": "already_in_progress"})):
        resp = client.post("/admin/warmup", headers=headers)
        assert resp.status_code == 409
        assert "Warmup is already in progress" in resp.json()["detail"]


def test_admin_warmup_concurrent_requests(client):
    """Scenario 9: Rapid concurrent requests to /admin/warmup acquire lock safely and return 409."""
    import concurrent.futures
    admin_secret = get_settings().ADMIN_SECRET.get_secret_value()
    headers = {"X-Admin-Key": admin_secret}

    def slow_rerank(*args, **kwargs):
        time.sleep(0.1)
        return []

    mock_emb = MagicMock()
    mock_reranker = MagicMock()
    mock_reranker.rerank_sync.side_effect = slow_rerank

    with patch("retrieval.search_pipeline.get_embedding_model", return_value=mock_emb), \
         patch("retrieval.reranker.get_reranker", return_value=mock_reranker):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(lambda: client.post("/admin/warmup", headers=headers))
            time.sleep(0.01)
            f2 = executor.submit(lambda: client.post("/admin/warmup", headers=headers))
            r1 = f1.result()
            r2 = f2.result()

    statuses = {r1.status_code, r2.status_code}
    assert 200 in statuses, "One request must succeed with 200"
    assert 409 in statuses, "The concurrent request must receive 409 Conflict"


def test_health_check_handles_none_or_malformed_warmup_status(client, mock_db_connected):
    """Scenario 10: None or malformed app.state.warmup_status does not crash /health with 500."""
    # 1. Test None value
    app.state.warmup_status = None
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["warmup"] == "in_progress"
    assert body["warmup"] == {"status": "pending"}

    # 2. Test non-dict string value
    app.state.warmup_status = "corrupted_state_string"
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["warmup"] == "in_progress"
    assert body["warmup"] == {"status": "pending"}


def test_is_test_environment_various_flags():
    """Scenario 11: is_test_environment parses various boolean representations correctly."""
    with patch.dict("os.environ", {"SKIP_MODEL_WARMUP": "true", "CI": "", "PYTEST_CURRENT_TEST": ""}):
        assert is_test_environment() is True

    with patch.dict("os.environ", {"SKIP_MODEL_WARMUP": "yes", "CI": "", "PYTEST_CURRENT_TEST": ""}):
        assert is_test_environment() is True

    with patch.dict("os.environ", {"SKIP_MODEL_WARMUP": "1", "CI": "", "PYTEST_CURRENT_TEST": ""}):
        assert is_test_environment() is True

    with patch.dict("os.environ", {"SKIP_MODEL_WARMUP": "0", "CI": "", "PYTEST_CURRENT_TEST": ""}):
        assert is_test_environment() is False


def test_lifespan_warmup_exception_soft_fail():
    """Scenario 12: Unhandled exception in perform_warmup does not crash lifespan startup."""
    from core.database import lifespan

    class DummyState:
        pass

    class DummyApp:
        def __init__(self):
            self.state = DummyState()

    dummy_app = DummyApp()

    with patch("core.warmup.perform_warmup", new=AsyncMock(side_effect=RuntimeError("Unexpected startup crash"))):
        async def _run_lifespan():
            async with lifespan(dummy_app):
                assert dummy_app.state.warmup_status["status"] == "failed"
                assert "Unexpected startup crash" in dummy_app.state.warmup_status["error"]

        _run(_run_lifespan())


def test_warmup_invalid_timeout_does_not_leak_lock():
    """Scenario 13: Invalid timeout value returns error and does not leave lock held."""
    res = _run(perform_warmup(app, timeout="invalid_timeout", force=True))
    assert res["status"] == "failed"
    assert "Invalid timeout" in res["error"]
    assert _warmup_thread_lock.locked() is False


def test_admin_warmup_timeout_returns_202(client):
    """Scenario 14: When admin warmup exceeds timeout, it returns 202 Accepted (Background Self-Healing)."""
    admin_secret = get_settings().ADMIN_SECRET.get_secret_value()
    headers = {"X-Admin-Key": admin_secret}

    with patch("core.warmup.perform_warmup", new=AsyncMock(return_value={"status": "in_progress"})):
        resp = client.post("/admin/warmup", headers=headers)
        assert resp.status_code == 202
        assert resp.json()["status"] == "in_progress"


