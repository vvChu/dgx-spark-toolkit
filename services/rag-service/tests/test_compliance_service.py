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

    def test_structured_compliance_apartment_and_ev_charging(self):
        from domain.project_profile import (
            ProjectProfile, ProjectLevel, PrimaryFunction, GeometricParameters,
            ActiveFireProtection, LegalMilestones, SprinklerCoverage
        )
        from datetime import date

        service, _, _ = _make_service()
        profile = ProjectProfile(
            project_name="Chung cư Tân Bình Grand",
            project_level=ProjectLevel.CAP_I,
            primary_function=PrimaryFunction.F1_2,
            geometry=GeometricParameters(
                fire_height_m=74.5,
                above_ground_floors=24,
                underground_floors=3,
                total_floor_area_m2=45000.0,
            ),
            fire_protection=ActiveFireProtection(
                has_sprinkler=True,
                sprinkler_coverage=SprinklerCoverage.WHOLE_BUILDING,
                has_auto_fire_alarm=True,
            ),
            milestones=LegalMilestones(pccc_approval=date(2027, 3, 1)),
        )

        charging_params = {
            "location": "basement",
            "car_spots": 20,
            "motorcycle_spots": 40,
            "compartment_area_m2": 280.0,
            "has_fire_wall_type_1": True,
            "has_auto_alarm_24h": True,
            "has_auto_sprinkler": True,
            "has_smoke_extraction": True,
            "has_co_hf_warning": True,
            "charger_power_kw": 11.0,
            "pccc_approval_date": "2027-03-01",
        }

        res = _run(service.check_compliance(profile, focus_area="PCCC", charging_params=charging_params))
        assert res["overall_status"] == "COMPLIANT"
        assert "assessment" in res
        assert "markdown_report" in res
        assert "# BÁO CÁO THẨM ĐỊNH TUÂN THỦ" in res["markdown_report"]
        assert "QCVN 04:2021/BXD" in res["sources"]
        assert "QCVN 06:2022/BXD" in res["sources"]

    def test_structured_compliance_excluded_facility(self):
        from domain.project_profile import (
            ProjectProfile, ProjectLevel, PrimaryFunction, GeometricParameters
        )

        service, _, _ = _make_service()
        profile = ProjectProfile(
            project_name="Nhà máy lọc dầu Dung Quất mở rộng",
            project_level=ProjectLevel.CAP_I,
            primary_function=PrimaryFunction.F5,
            geometry=GeometricParameters(
                fire_height_m=30.0,
                above_ground_floors=3,
                total_floor_area_m2=10000.0,
            ),
        )

        res = _run(service.check_compliance(profile, focus_area="PCCC"))
        assert res["overall_status"] == "NON_COMPLIANT"
        assert res["scope_decision"]["is_applicable"] is False
        assert "loại trừ" in res["markdown_report"]
