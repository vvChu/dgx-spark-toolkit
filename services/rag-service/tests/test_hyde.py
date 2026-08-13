"""Unit tests for retrieval.hyde.HyDEGenerator (mocked HTTP)."""
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure config doesn't crash
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")


def _run(coro):
    """Helper to run async code without pytest-asyncio."""
    return asyncio.run(coro)


class TestHyDEGeneratorUnit:
    def _make_generator(self):
        from retrieval.hyde import HyDEGenerator
        from core.ai_gateway_client import MockAIGatewayClient
        ai_client = MockAIGatewayClient()
        gen = HyDEGenerator(http_client=AsyncMock(), ai_client=ai_client)
        return gen, ai_client

    def test_empty_query_returns_empty(self):
        gen, _ = self._make_generator()
        result = _run(gen.generate_hypothetical_answer(""))
        assert result == ""

    def test_successful_generation(self):
        gen, ai_client = self._make_generator()
        ai_client.complete = AsyncMock(return_value="Hypothetical answer text")

        result = _run(gen.generate_hypothetical_answer("Quy định về PCCC?"))
        assert result == "Hypothetical answer text"

    def test_api_error_returns_original_query(self):
        gen, ai_client = self._make_generator()
        ai_client.complete = AsyncMock(side_effect=Exception("Connection refused"))

        result = _run(gen.generate_hypothetical_answer("some query"))
        assert result == "some query"

    def test_empty_content_returns_empty(self):
        gen, ai_client = self._make_generator()
        ai_client.complete = AsyncMock(return_value="")

        result = _run(gen.generate_hypothetical_answer("test"))
        assert result == ""
