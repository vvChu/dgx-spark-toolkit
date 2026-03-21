import os

# Set CI/test defaults so get_settings() doesn't crash when importing main.py
# outside Docker.  These are NOT real credentials — they only satisfy the
# @model_validator that rejects empty values.
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

import pytest
from starlette.testclient import TestClient
from main import app

@pytest.fixture
def client():
    """TestClient wired to the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client
