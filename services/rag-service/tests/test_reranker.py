"""Unit tests for retrieval.reranker.Reranker (no GPU / real model required)."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock


class TestRerankerUnit:
    """Test Reranker logic without loading a real CrossEncoder model."""

    def _make_reranker(self):
        """Import Reranker fresh with CrossEncoder mocked out."""
        with patch("retrieval.reranker.CrossEncoder") as MockCE:
            mock_model = MagicMock()
            MockCE.return_value = mock_model
            from retrieval.reranker import Reranker
            r = Reranker.__new__(Reranker)
            r.model_name = "BAAI/bge-reranker-v2-m3"
            r.model = mock_model
            r._load_lock = __import__("threading").Lock()
            r.device = "cpu"
            r.force_cpu = True
            return r, mock_model

    def test_empty_docs_returns_empty(self):
        r, _ = self._make_reranker()
        result = r.rerank_sync("test query", [], top_k=5)
        assert result == []

    def test_results_sorted_descending(self):
        r, mock_model = self._make_reranker()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]
        result = r.rerank_sync("q", ["a", "b", "c"], top_k=3)
        assert result[0] == ("b", 0.9)
        assert result[1] == ("c", 0.5)
        assert result[2] == ("a", 0.1)

    def test_top_k_overflow_returns_all(self):
        r, mock_model = self._make_reranker()
        mock_model.predict.return_value = [0.8, 0.2]
        result = r.rerank_sync("q", ["x", "y"], top_k=10)
        assert len(result) == 2

    def test_cpu_fallback_on_gpu_error(self):
        """If GPU loading fails, Reranker should retry on CPU."""
        with patch("retrieval.reranker.CrossEncoder") as MockCE:
            call_count = 0

            def side_effect(name, device="cpu"):
                nonlocal call_count
                call_count += 1
                if device != "cpu":
                    raise RuntimeError("CUDA not available")
                return MagicMock()

            MockCE.side_effect = side_effect

            with patch.dict("os.environ", {"GPU_ENABLED": "1", "FORCE_CPU_RERANKER": "0"}):
                from retrieval.reranker import Reranker
                r = Reranker.__new__(Reranker)
                r.model_name = "test"
                r.model = None
                r._load_lock = __import__("threading").Lock()
                r.device = "cuda"
                r.load_model()
                assert r.device == "cpu"
                assert r.model is not None

    def test_async_rerank_delegates_to_sync(self):
        r, mock_model = self._make_reranker()
        mock_model.predict.return_value = [0.5]

        result = asyncio.run(
            r.rerank("q", ["doc"], top_k=1)
        )
        assert len(result) == 1
