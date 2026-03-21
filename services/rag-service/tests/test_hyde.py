"""Unit tests for retrieval.hyde.HyDEGenerator (mocked HTTP)."""
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure config doesn't crash
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")


def _run(coro):
    """Helper to run async code without pytest-asyncio."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestHyDEGeneratorUnit:
    def _make_generator(self):
        from retrieval.hyde import HyDEGenerator
        gen = HyDEGenerator()
        return gen

    def test_empty_query_returns_empty(self):
        gen = self._make_generator()
        result = _run(gen.generate_hypothetical_answer(""))
        assert result == ""

    def test_successful_generation(self):
        gen = self._make_generator()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hypothetical answer text"}}]
        }

        with patch("retrieval.hyde._get_hyde_http_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_fn.return_value = mock_client

            result = _run(gen.generate_hypothetical_answer("Quy định về PCCC?"))
            assert result == "Hypothetical answer text"
            mock_client.post.assert_called_once()

    def test_api_error_returns_original_query(self):
        gen = self._make_generator()

        with patch("retrieval.hyde._get_hyde_http_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection refused")
            mock_client_fn.return_value = mock_client

            result = _run(gen.generate_hypothetical_answer("some query"))
            assert result == "some query"

    def test_empty_content_returns_empty(self):
        gen = self._make_generator()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}]
        }

        with patch("retrieval.hyde._get_hyde_http_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_fn.return_value = mock_client

            result = _run(gen.generate_hypothetical_answer("test"))
            assert result == ""
