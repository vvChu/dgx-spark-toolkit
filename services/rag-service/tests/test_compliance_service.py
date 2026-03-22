"""Unit tests for services.compliance_service.ComplianceService."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from services.compliance_service import ComplianceService


def _run(coro):
    return asyncio.run(coro)


def _make_service():
    milvus = AsyncMock()
    graph_rag = AsyncMock()
    graph_rag._get_client = AsyncMock(return_value=AsyncMock())
    http = AsyncMock()
    service = ComplianceService(milvus, graph_rag, http)
    return service, milvus, graph_rag


class TestComplianceService:
    def test_keyword_extraction_success(self):
        service, milvus, _ = _make_service()
        with patch("services.compliance_service.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"keywords": ["BIM", "fire safety"]}
            result = _run(service._extract_compliance_keywords("tower project", "BIM"))
            assert result == ["BIM", "fire safety"]

    def test_keyword_extraction_fallback(self):
        service, milvus, _ = _make_service()
        with patch("services.compliance_service.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("LLM error")
            result = _run(service._extract_compliance_keywords("profile", "Construction"))
            assert result == ["Construction"]

    def test_report_generation_success(self):
        service, milvus, _ = _make_service()
        with patch("services.compliance_service.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"compliant": [], "risks": [], "violations": []}
            context = [{"text": "some law", "source": "ND/1", "page": 1}]
            result = _run(service._generate_compliance_report("profile", context, "BIM"))
            assert "compliant" in result

    def test_report_generation_failure(self):
        service, milvus, _ = _make_service()
        with patch("services.compliance_service.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("fail")
            result = _run(service._generate_compliance_report("p", [], "BIM"))
            assert "error" in result

    def test_check_compliance_full(self):
        service, milvus, _ = _make_service()

        # Mock keyword extraction
        with patch("services.compliance_service.call_llm_json", new_callable=AsyncMock) as mock_json, \
             patch("services.retrieval_service.get_embedding_model") as mock_embed:
            mock_json.side_effect = [
                {"keywords": ["fire"]},  # keyword extraction
                {"compliant": ["ok"]},   # report generation
            ]
            mock_model = MagicMock()
            mock_model.embed_query.return_value = {"dense": [0.1] * 1024, "sparse": {}}
            mock_embed.return_value = mock_model

            hit = MagicMock()
            hit.entity = MagicMock()
            hit.entity.get = MagicMock(side_effect=lambda k, d=None: {"text": "law text", "doc_number": "ND/1", "source": "ND/1", "page": 1}.get(k, d))
            milvus.hybrid_search = AsyncMock(return_value=[[hit]])

            result = _run(service.check_compliance("tower project", "safety"))
            assert result["focus_area"] == "safety"
            assert "keywords_analyzed" in result
