"""Unit tests for services.legal_analysis_service.LegalAnalysisService."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from services.legal_analysis_service import LegalAnalysisService
from core.ai_gateway_client import MockAIGatewayClient


def _run(coro):
    return asyncio.run(coro)


def _make_service():
    milvus = AsyncMock()
    graph_rag = AsyncMock()
    graph_rag._get_client = AsyncMock(return_value=AsyncMock())
    http = AsyncMock()
    ai_client = MockAIGatewayClient()
    service = LegalAnalysisService(milvus, graph_rag, http, ai_client=ai_client)
    return service, milvus, graph_rag, ai_client


class TestLegalAnalysisService:
    def test_no_predecessors_empty_timeline(self):
        service, milvus, graph_rag, _ = _make_service()
        graph_rag.get_legal_timeline = AsyncMock(return_value=[])
        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "no_predecessors"

    def test_no_predecessors_single_doc(self):
        service, milvus, graph_rag, _ = _make_service()
        graph_rag.get_legal_timeline = AsyncMock(return_value=[{"id": "doc/1"}])
        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "no_predecessors"

    def test_with_timeline(self):
        service, milvus, graph_rag, ai_client = _make_service()
        graph_rag.get_legal_timeline = AsyncMock(return_value=[
            {"id": "doc/1", "relation_to_next": "REPLACES"},
            {"id": "doc/0", "relation_to_next": None},
        ])

        hit = MagicMock()
        hit.entity = MagicMock()
        hit.entity.get = MagicMock(return_value="some text")
        milvus.hybrid_search = AsyncMock(return_value=[[hit]])

        ai_client.complete = AsyncMock(return_value="Delta analysis result")
        with patch("retrieval.search_pipeline.get_embedding_model") as mock_embed:
            mock_model = MagicMock()
            mock_model.embed_query.return_value = {"dense": [0.1] * 1024}
            mock_embed.return_value = mock_model

            result = _run(service.analyze_conflicts("doc/1", "fire"))
            assert result["status"] == "success"
            assert len(result["comparisons"]) == 1

    def test_delta_analysis_success(self):
        service, milvus, graph_rag, ai_client = _make_service()
        ai_client.complete = AsyncMock(return_value="Analysis text")
        result = _run(service._generate_delta_analysis("new", "old", "q", "ctx_new", "ctx_old"))
        assert result == "Analysis text"

    def test_delta_analysis_failure(self):
        service, milvus, graph_rag, ai_client = _make_service()
        ai_client.complete = AsyncMock(side_effect=Exception("err"))
        result = _run(service._generate_delta_analysis("n", "o", "q", "cn", "co"))
        assert "Lỗi" in result
