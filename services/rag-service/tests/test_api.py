def test_health_check_endpoint(client):
    """GET /health returns status and checks dict."""
    response = client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body


def test_root_endpoint(client):
    """GET / returns service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "docs" in data
