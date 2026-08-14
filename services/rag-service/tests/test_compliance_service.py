"""Unit tests for services.compliance_service.ComplianceService."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from services.compliance_service import ComplianceService
from retrieval.search_pipeline import InMemorySearchPipeline
from core.ai_gateway_client import MockAIGatewayClient


def _run(coro):
    return asyncio.run(coro)


def _make_service(search_pipeline=None):
    pipeline = search_pipeline or InMemorySearchPipeline(custom_results=[
        {"text": "law text", "doc_number": "ND/1", "source": "ND/1", "page": 1}
    ])
    ai_client = MockAIGatewayClient()
    service = ComplianceService(search_pipeline=pipeline, ai_client=ai_client)
    return service, pipeline, ai_client


class TestComplianceService:
    def test_keyword_extraction_success(self):
        service, _, ai_client = _make_service()
        ai_client.complete_json = AsyncMock(return_value={"keywords": ["BIM", "fire safety"]})
        result = _run(service._extract_compliance_keywords("tower project", "BIM"))
        assert result == ["BIM", "fire safety"]

    def test_keyword_extraction_fallback(self):
        service, _, ai_client = _make_service()
        ai_client.complete_json = AsyncMock(side_effect=Exception("LLM error"))
        result = _run(service._extract_compliance_keywords("profile", "Construction"))
        assert result == ["Construction"]

    def test_report_generation_success(self):
        service, _, ai_client = _make_service()
        ai_client.complete_json = AsyncMock(return_value={"compliant": [], "risks": [], "violations": []})
        context = [{"text": "some law", "source": "ND/1", "page": 1}]
        result = _run(service._generate_compliance_report("profile", context, "BIM"))
        assert "compliant" in result

    def test_report_generation_failure(self):
        service, _, ai_client = _make_service()
        ai_client.complete_json = AsyncMock(side_effect=Exception("fail"))
        result = _run(service._generate_compliance_report("p", [], "BIM"))
        assert "error" in result

    def test_check_compliance_full(self):
        service, pipeline, ai_client = _make_service()

        ai_client.complete_json = AsyncMock(side_effect=[
            {"keywords": ["fire"]},  # keyword extraction
            {"compliant": ["ok"]},   # report generation
        ])
        result = _run(service.check_compliance("tower project", "safety"))
        assert result["focus_area"] == "safety"
        assert "keywords_analyzed" in result
        assert result["keywords_analyzed"] == ["fire"]
        assert "ND/1" in result["sources"]
