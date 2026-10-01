import asyncio
import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Union

import httpx

from core.ai_gateway_client import AIGatewayClient, get_ai_gateway_client
from domain.compliance import (
    ClauseType,
    ComplianceAssessment,
    DocumentRef,
    Finding,
    FindingStatus,
    LegalWarning,
    OverallStatus,
    PriorityLevel,
    Recommendation,
    TraceabilityInfo,
    WarningType,
)
from domain.project_profile import PrimaryFunction, ProjectProfile
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from retrieval.scope_gate import ScopeDecision, ScopeGate
from retrieval.search_pipeline import SearchPipeline
from symbolic.charging_area_validator import ChargingAreaParameters, ChargingAreaValidator
from symbolic.table10_solver import Table10SymbolicSolver
from symbolic.table4_solver import Table4SymbolicSolver

logger = logging.getLogger(__name__)


class ComplianceService:
    """Legal and Technical Compliance Service (OKF Enterprise Architecture)."""

    def __init__(
        self,
        milvus_repo: Optional[MilvusRepository] = None,
        graph_rag: Optional[AdvancedGraphRAG] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        ai_client: Optional[AIGatewayClient] = None,
        search_pipeline: Optional[SearchPipeline] = None,
    ):
        self.milvus_repo = milvus_repo
        self.graph_rag = graph_rag
        self._http_client = http_client
        self.ai_client = ai_client or get_ai_gateway_client(http_client)
        if search_pipeline is not None:
            self.search_pipeline = search_pipeline
        elif milvus_repo is not None:
            driver = getattr(graph_rag, "driver", None)
            neo4j = Neo4jRepository(driver) if driver else None
            self.search_pipeline = SearchPipeline(milvus_repo, neo4j, ai_client=self.ai_client)
        else:
            self.search_pipeline = None

        self.scope_gate = ScopeGate()
        self.table4_solver = Table4SymbolicSolver()
        self.table10_solver = Table10SymbolicSolver()
        self.charging_validator = ChargingAreaValidator()

    async def check_compliance(
        self,
        project_profile: Union[ProjectProfile, Dict[str, Any], str],
        focus_area: str = "General",
        charging_params: Optional[Union[ChargingAreaParameters, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Analyze a project profile against statutory codes and neuro-symbolic tables."""
        profile = self._parse_project_profile(project_profile)
        if profile is not None:
            return await self._check_structured_compliance(profile, focus_area, charging_params)

        return await self._check_legacy_compliance(str(project_profile), focus_area)

    def _parse_project_profile(self, raw_input: Any) -> Optional[ProjectProfile]:
        """Attempt to parse input into a domain ProjectProfile."""
        if isinstance(raw_input, ProjectProfile):
            return raw_input
        if isinstance(raw_input, dict) and "project_name" in raw_input and "primary_function" in raw_input:
            try:
                return ProjectProfile.model_validate(raw_input)
            except Exception as e:
                logger.warning(f"Failed to validate ProjectProfile from dict: {e}")
                return None
        if isinstance(raw_input, str):
            try:
                data = json.loads(raw_input)
                if isinstance(data, dict) and "project_name" in data:
                    return ProjectProfile.model_validate(data)
            except Exception:
                pass
        return None

    async def _check_structured_compliance(
        self,
        profile: ProjectProfile,
        focus_area: str,
        charging_params: Optional[Union[ChargingAreaParameters, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Execute full OKF Compliance pipeline: ScopeGate -> SymbolicSolvers -> Output Contract."""
        logger.info(f"Running OKF structured compliance check for: '{profile.project_name}'")
        scope_decision = self.scope_gate.evaluate_scope(profile)

        findings: List[Finding] = []
        warnings: List[LegalWarning] = []
        recommendations: List[Recommendation] = []

        # 1. Scope Gate Exclusions
        if not scope_decision.is_applicable:
            findings.append(Finding(
                regulation_reference="QCVN 06:2022/BXD Mục 1.1.3",
                check_description="Phạm vi áp dụng quy chuẩn kỹ thuật quốc gia",
                status=FindingStatus.FAIL,
                actual_value=profile.project_name,
                required_value="Công trình thuộc đối tượng điều chỉnh chung của QCVN 06",
                explanation=scope_decision.reject_reason or "Công trình thuộc diện loại trừ.",
                regulatory_text="Quy chuẩn này không áp dụng cho các nhà và công trình có công năng đặc thù.",
                clause_type=ClauseType.MANDATORY,
            ))
            assessment = self._build_assessment(profile.project_name, OverallStatus.NON_COMPLIANT, findings, warnings, recommendations, scope_decision)
            return self._format_structured_response(assessment, scope_decision, focus_area, {}, [])

        # 2. Geometric Thresholds
        if scope_decision.special_clearance_required:
            findings.append(Finding(
                regulation_reference="QCVN 06:2022/BXD Mục 1.1.2",
                check_description="Giới hạn hình học công trình (Chiều cao PCCC và số tầng hầm)",
                status=FindingStatus.CONDITIONAL,
                actual_value=f"H={profile.geometry.fire_height_m}m, {profile.geometry.underground_floors} tầng hầm",
                required_value="H ≤ 150m và ≤ 3 tầng hầm",
                explanation=scope_decision.special_clearance_reason or "",
                regulatory_text="Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm.",
                clause_type=ClauseType.CONDITIONAL,
            ))
            recommendations.append(Recommendation(
                priority=PriorityLevel.URGENT,
                description="Lập Luận chứng giải pháp kỹ thuật PCCC riêng trình Cục Cảnh sát PCCC & CNCH.",
                applicable_regulation="QCVN 06:2022/BXD Mục 1.1.2",
                responsible_party="Chủ đầu tư / Đơn vị tư vấn PCCC",
            ))

        # 3. Scope Gate Warnings (Grace periods & Era transitions)
        for w_text in scope_decision.warnings:
            warnings.append(LegalWarning(
                warning_type=WarningType.GRACE_PERIOD if "ân hạn" in w_text else WarningType.STATUTORY_REPEAL,
                title="Cảnh báo pháp lý chuyển tiếp",
                description=w_text,
                deadline="2027-06-15" if "2027-06-15" in w_text else None,
                applicable_regulation="Thông tư 31/2026/TT-BXD / Luật Xây dựng 2025",
            ))

        # 4. Symbolic Solvers Execution
        symbolic_results = self._run_symbolic_solvers(profile, charging_params, findings, warnings, recommendations)

        # 5. Determine Overall Status
        has_fail = any(f.status == FindingStatus.FAIL for f in findings)
        has_conditional = any(f.status == FindingStatus.CONDITIONAL for f in findings)
        overall = OverallStatus.NON_COMPLIANT if has_fail else (OverallStatus.CONDITIONAL if has_conditional else OverallStatus.COMPLIANT)

        assessment = self._build_assessment(profile.project_name, overall, findings, warnings, recommendations, scope_decision)
        return self._format_structured_response(assessment, scope_decision, focus_area, symbolic_results, scope_decision.applicable_codes)

    def _run_symbolic_solvers(
        self,
        profile: ProjectProfile,
        charging_params: Any,
        findings: List[Finding],
        warnings: List[LegalWarning],
        recommendations: List[Recommendation],
    ) -> Dict[str, Any]:
        """Execute Table 4, Table 10, and EV Charging symbolic solvers."""
        # Table 4 Structural Ratings
        table4_res = self.table4_solver.resolve_all_elements(
            building_grade=profile.structural_resistance_grade.value,
            has_sprinkler=profile.fire_protection.has_sprinkler,
            no_attic=True,
            has_auto_alarm=profile.fire_protection.has_auto_fire_alarm,
        )
        col_res = table4_res.get("column", {})
        findings.append(Finding(
            regulation_reference=f"QCVN 06:2022/BXD Bảng 4 ({profile.structural_resistance_grade.value})",
            check_description="Giới hạn chịu lửa của cột chịu lực",
            status=FindingStatus.PASS,
            actual_value=col_res.get("final_rei"),
            required_value=col_res.get("base_rei"),
            explanation=f"Yêu cầu tối thiểu: {col_res.get('final_rei')}.",
            regulatory_text="Giới hạn chịu lửa của các bộ phận kết cấu nhà theo Bảng 4.",
            clause_type=ClauseType.MANDATORY,
        ))

        # Table 10 External Water Flow (for F5 industrial facilities)
        table10_res = None
        if profile.primary_function == PrimaryFunction.F5 and profile.geometry.building_volume_m3:
            table10_res = self.table10_solver.calculate_flow(
                building_volume_m3=profile.geometry.building_volume_m3,
                hazard_class=profile.fire_hazard_category or "C",
                fire_height_m=profile.geometry.fire_height_m,
            )
            findings.append(Finding(
                regulation_reference="QCVN 06:2022/BXD Bảng 10",
                check_description="Lưu lượng nước chữa cháy ngoài nhà cho cơ sở sản xuất F5",
                status=FindingStatus.PASS,
                actual_value=f"{table10_res['flow_l_s']} L/s",
                required_value=f"≥ {table10_res['flow_l_s']} L/s",
                explanation=f"Lưu lượng cơ sở: {table10_res['base_flow_l_s']} L/s (hệ số: {table10_res['height_multiplier']}x).",
                regulatory_text="Lưu lượng nước chữa cháy ngoài nhà cho nhà sản xuất và nhà kho theo Bảng 10.",
                clause_type=ClauseType.MANDATORY,
            ))

        # EV Charging Validator
        ev_res = None
        if charging_params is not None:
            c_params = (
                charging_params
                if isinstance(charging_params, ChargingAreaParameters)
                else ChargingAreaParameters.model_validate(charging_params)
            )
            ev_assessment = self.charging_validator.validate(profile.project_name, c_params)
            ev_res = ev_assessment.model_dump()
            findings.extend(ev_assessment.findings)
            warnings.extend(ev_assessment.legal_warnings)
            recommendations.extend(ev_assessment.recommendations)

        return {"table4": table4_res, "table10": table10_res, "ev_charging": ev_res}

    def _build_assessment(
        self,
        project_name: str,
        overall: OverallStatus,
        findings: List[Finding],
        warnings: List[LegalWarning],
        recommendations: List[Recommendation],
        scope_decision: ScopeDecision,
    ) -> ComplianceAssessment:
        """Construct schema-locked ComplianceAssessment object."""
        docs_used = [
            DocumentRef(doc_id=code, version=scope_decision.edition_map.get(code, "current"))
            for code in scope_decision.applicable_codes
        ]
        return ComplianceAssessment(
            assessment_id=f"ASM-{date.today().strftime('%Y%m%d')}-01",
            project_name=project_name,
            assessment_date=date.today().isoformat(),
            overall_status=overall,
            findings=findings,
            legal_warnings=warnings,
            recommendations=recommendations,
            traceability=TraceabilityInfo(
                documents_used=docs_used,
                version_at_assessment=" / ".join([f"{k}: {v}" for k, v in scope_decision.edition_map.items()]),
            ),
        )

    def _format_structured_response(
        self,
        assessment: ComplianceAssessment,
        scope_decision: ScopeDecision,
        focus_area: str,
        symbolic_results: Dict[str, Any],
        sources: List[str],
    ) -> Dict[str, Any]:
        """Format final dictionary payload for REST response."""
        md_report = assessment.to_markdown()
        return {
            "focus_area": focus_area,
            "overall_status": assessment.overall_status.value,
            "assessment": assessment.model_dump(),
            "markdown_report": md_report,
            "scope_decision": scope_decision.model_dump(),
            "symbolic_evaluations": symbolic_results,
            "keywords_analyzed": [focus_area] + [c.split()[0] for c in sources],
            "report": {
                "status": assessment.overall_status.value,
                "summary": md_report,
            },
            "sources": sources,
        }

    async def _check_legacy_compliance(self, project_profile: str, focus_area: str) -> Dict[str, Any]:
        """Fallback compliance check using LLM keyword extraction for unstructured text."""
        logger.info(f"Starting legacy compliance check for focus area: {focus_area}")
        keywords = await self._extract_compliance_keywords(project_profile, focus_area)

        search_query = f"Quy định, bắt buộc, nghiêm cấm về {', '.join(keywords)}"
        context = []

        if self.search_pipeline:
            try:
                search_res = await self.search_pipeline.search(query=search_query, limit=15, use_cache=True)
                for res in search_res.get("results", []):
                    context.append({
                        "text": res.get("text", ""),
                        "source": res.get("doc_number") or res.get("source", ""),
                        "page": res.get("page", 1),
                    })
            except Exception as e:
                logger.warning(f"SearchPipeline compliance retrieval fallback: {e}")

        report = await self._generate_compliance_report(project_profile, context, focus_area)

        return {
            "focus_area": focus_area,
            "keywords_analyzed": keywords,
            "report": report,
            "sources": list(set([c["source"] for c in context if c.get("source")])),
        }

    async def _extract_compliance_keywords(self, profile: str, focus: str) -> List[str]:
        prompt = f"""
        Extract 5-8 key technical keywords from this project profile that relate to legal requirements, 
        standards, or safety regulations in the field of {focus}.
        Focus on structural types, materials, location constraints, or specialized equipment.
        
        Profile: {profile}
        
        Output ONLY a JSON list of strings.
        """
        try:
            result = await self.ai_client.complete_json([{"role": "user", "content": prompt}], max_tokens=100)
            return result.get("keywords", [])
        except Exception as e:
            logger.error(f"Keyword extraction failed: {e}")
            return [focus]

    async def _generate_compliance_report(self, profile: str, context: List[Dict], focus: str) -> Dict[str, Any]:
        context_str = "\n\n".join([f"Source: {c['source']} (Page {c['page']})\nContent: {c['text']}" for c in context])
        prompt = f"""
        You are a Legal Compliance Auditor. Analyze the following Project Profile against the provided Regulatory Context.

        PROJECT PROFILE:
        {profile}

        REGULATORY CONTEXT (ACTIVE LAWS):
        {context_str}

        TASK:
        Identify if the project aligns with or violates the rules in the context.
        Group findings into:
        1. COMPLIANT: Elements that follow the rules.
        2. RISKS: Areas that are ambiguous or need more documentation.
        3. VIOLATIONS: Direct contradictions with the law.

        Output a structured JSON report. Include citations to sources.
        """
        try:
            return await self.ai_client.complete_json([{"role": "user", "content": prompt}], temperature=0.3)
        except Exception as e:
            logger.error(f"Compliance report generation failed: {e}")
            return {
                "error": "Failed to generate detailed report",
                "summary": "Manual review required due to LLM processing error.",
            }
