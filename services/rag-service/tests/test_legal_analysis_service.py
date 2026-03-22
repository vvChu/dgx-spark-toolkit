"""Unit tests for services.legal_analysis_service.LegalAnalysisService."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from services.legal_analysis_service import LegalAnalysisService


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_service():
    milvus = AsyncMock()
    graph_rag = AsyncMock()
    graph_rag._get_client = AsyncMock(return_value=AsyncMock())
    http = AsyncMock()
    service = LegalAnalysisService(milvus, graph_rag, http)
    return service, milvus, graph_rag


class TestLegalAnalysisService:
    def test_no_predecessors_empty_timeline(self):
        service, milvus, graph_rag = _make_service()
        graph_rag.get_legal_timeline = AsyncMock(return_value=[])
        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "no_predecessors"

    def test_no_predecessors_single_doc(self):
        service, milvus, graph_rag = _make_service()
        graph_rag.get_legal_timeline = AsyncMock(return_value=[{"id": "doc/1"}])
        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "no_predecessors"

    def test_with_timeline(self):
        service, milvus, graph_rag = _make_service()
        graph_rag.get_legal_timeline = AsyncMock(return_value=[
            {"id": "doc/1", "relation_to_next": "REPLACES"},
            {"id": "doc/0", "relation_to_next": None},
        ])

        hit = MagicMock()
        hit.entity = MagicMock()
        hit.entity.get = MagicMock(return_value="some text")
        milvus.hybrid_search = AsyncMock(return_value=[[hit]])

        with patch("services.legal_analysis_service.call_llm", new_callable=AsyncMock) as mock_call, \
             patch("services.retrieval_service.get_embedding_model") as mock_embed:
            mock_call.return_value = "Delta analysis result"
            mock_model = MagicMock()
            mock_model.embed_query.return_value = {"dense": [0.1] * 1024}
            mock_embed.return_value = mock_model

            result = _run(service.analyze_conflicts("doc/1", "fire"))
            assert result["status"] == "success"
            assert len(result["comparisons"]) == 1

    def test_delta_analysis_success(self):
        service, milvus, graph_rag = _make_service()
        with patch("services.legal_analysis_service.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "Analysis text"
            result = _run(service._generate_delta_analysis("new", "old", "q", "ctx_new", "ctx_old"))
            assert result == "Analysis text"

    def test_delta_analysis_failure(self):
        service, milvus, graph_rag = _make_service()
        with patch("services.legal_analysis_service.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("err")
            result = _run(service._generate_delta_analysis("n", "o", "q", "cn", "co"))
            assert "Lỗi" in result
