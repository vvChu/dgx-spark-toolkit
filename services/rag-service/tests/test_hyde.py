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
        gen = HyDEGenerator(http_client=AsyncMock())
        return gen

    def test_empty_query_returns_empty(self):
        gen = self._make_generator()
        result = _run(gen.generate_hypothetical_answer(""))
        assert result == ""

    def test_successful_generation(self):
        gen = self._make_generator()

        with patch("retrieval.hyde.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Hypothetical answer text"

            result = _run(gen.generate_hypothetical_answer("Quy định về PCCC?"))
            assert result == "Hypothetical answer text"
            mock_call.assert_called_once()

    def test_api_error_returns_original_query(self):
        gen = self._make_generator()

        with patch("retrieval.hyde.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("Connection refused")

            result = _run(gen.generate_hypothetical_answer("some query"))
            assert result == "some query"

    def test_empty_content_returns_empty(self):
        gen = self._make_generator()

        with patch("retrieval.hyde.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = ""

            result = _run(gen.generate_hypothetical_answer("test"))
            assert result == ""
