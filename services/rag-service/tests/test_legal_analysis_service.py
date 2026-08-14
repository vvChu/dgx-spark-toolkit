"""Unit tests for services.legal_analysis_service.LegalAnalysisService."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from services.legal_analysis_service import LegalAnalysisService
from retrieval.search_pipeline import InMemorySearchPipeline
from core.ai_gateway_client import MockAIGatewayClient


def _run(coro):
    return asyncio.run(coro)


def _make_service(search_pipeline=None):
    pipeline = search_pipeline or InMemorySearchPipeline()
    ai_client = MockAIGatewayClient()
    service = LegalAnalysisService(search_pipeline=pipeline, ai_client=ai_client)
    return service, pipeline, ai_client


class TestLegalAnalysisService:
    def test_no_predecessors_empty_timeline(self):
        pipeline = InMemorySearchPipeline()
        pipeline.get_legal_timeline = AsyncMock(return_value=[])
        service, _, _ = _make_service(search_pipeline=pipeline)
        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "no_predecessors"

    def test_no_predecessors_single_doc(self):
        pipeline = InMemorySearchPipeline()
        pipeline.get_legal_timeline = AsyncMock(return_value=[{"id": "doc/1"}])
        service, _, _ = _make_service(search_pipeline=pipeline)
        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "no_predecessors"

    def test_with_timeline(self):
        pipeline = InMemorySearchPipeline()
        pipeline.get_legal_timeline = AsyncMock(return_value=[
            {"id": "doc/1", "relation_to_next": "REPLACES"},
            {"id": "doc/0", "relation_to_next": None},
        ])
        service, _, ai_client = _make_service(search_pipeline=pipeline)
        ai_client.complete = AsyncMock(return_value="Delta analysis result")

        result = _run(service.analyze_conflicts("doc/1", "fire"))
        assert result["status"] == "success"
        assert len(result["comparisons"]) == 1
        assert result["comparisons"][0]["analysis"] == "Delta analysis result"

    def test_delta_analysis_success(self):
        service, _, ai_client = _make_service()
        ai_client.complete = AsyncMock(return_value="Analysis text")
        result = _run(service._generate_delta_analysis("new", "old", "q", "ctx_new", "ctx_old"))
        assert result == "Analysis text"

    def test_delta_analysis_failure(self):
        service, _, ai_client = _make_service()
        ai_client.complete = AsyncMock(side_effect=Exception("err"))
        result = _run(service._generate_delta_analysis("n", "o", "q", "cn", "co"))
        assert "Lỗi" in result

    def test_fetch_doc_context_parsing(self):
        pipeline = InMemorySearchPipeline()
        pipeline.search = AsyncMock(return_value={"results": [{"text": "Context for 01/2024/TT-BXD"}]})
        service, _, _ = _make_service(search_pipeline=pipeline)

        # Case 1: Raw doc number starting with digits
        ctx1 = _run(service._fetch_doc_context("01/2024/TT-BXD", "PCCC"))
        assert ctx1 == "Context for 01/2024/TT-BXD"
        assert pipeline.search.call_args[1]["doc_number"] == "01/2024/TT-BXD"

        # Case 2: Namespace prefixed doc_id
        ctx2 = _run(service._fetch_doc_context("VBPL/01/2024/TT-BXD", "PCCC"))
        assert ctx2 == "Context for 01/2024/TT-BXD"
        assert pipeline.search.call_args[1]["doc_number"] == "01/2024/TT-BXD"
