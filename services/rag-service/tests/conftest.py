import pytest
from starlette.testclient import TestClient
from rag_api import app

@pytest.fixture
def client():
    # Mock Milvus connection if needed or assume test env
    # For now, we test endpoints that don't hit Milvus heavily or mock them
    with TestClient(app) as test_client:
        yield test_client
