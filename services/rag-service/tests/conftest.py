import pytest
from starlette.testclient import TestClient
from main import app

@pytest.fixture
def client():
    """TestClient wired to the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client
