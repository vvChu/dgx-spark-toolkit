import os
import sys
import types
from contextlib import asynccontextmanager

# Set CI/test defaults so get_settings() doesn't crash when importing main.py
# outside Docker.  These are NOT real credentials — they only satisfy the
# @model_validator that rejects empty values.
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

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
