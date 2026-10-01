"""Tests for ProjectProfile, Normative Force, Scope Gate, and Output Contract.
=============================================================================
Validates:
1. Normative Force classification (QCVN mandatory, TCVN voluntary/referenced, contract-adopted).
2. ProjectProfile domain models, geometric validations, and temporal anchor detection.
3. Strict enforcement: Cấm dẫn chiếu Thông tư 06/2021/TT-BXD cho hồ sơ sau 01/07/2026.
4. Scope Gate: loại trừ công trình nguy hiểm đặc thù (§1.1.3), kiểm soát H>150m (§1.1.2),
   và khóa phiên bản quy chuẩn chuyển tiếp.
5. ComplianceAssessment output contract and markdown rendering.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Luật Xây dựng 2025 Cutoff (2026-07-01)
"""

import sys
from datetime import date
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAG_SERVICE_DIR = REPO_ROOT / "services/rag-service"
if str(RAG_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_SERVICE_DIR))

from domain.compliance import (  # noqa: E402
    ClauseType,
    ComplianceAssessment,
    Finding,
    FindingStatus,
    LegalWarning,
    OverallStatus,
    PriorityLevel,
    Recommendation,
    TraceabilityInfo,
    WarningType,
)
from domain.normative_force import NormativeForce, resolve_normative_force  # noqa: E402
from domain.project_profile import (  # noqa: E402
    ActiveFireProtection,
    GeometricParameters,
    LegalMilestones,
    PrimaryFunction,
    ProjectLevel,
    ProjectProfile,
    SprinklerCoverage,
    StructureResistanceGrade,
)
from retrieval.scope_gate import ScopeGate  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Normative Force Tests
# ---------------------------------------------------------------------------

def test_normative_force_qcvn_mandatory():
    """QCVN must always be classified as mandatory."""
    assert resolve_normative_force("QCVN 06:2022/BXD") == NormativeForce.MANDATORY
    assert resolve_normative_force("QCVN 04:2021/BXD") == NormativeForce.MANDATORY
    assert resolve_normative_force("QCXDVN 01:2008") == NormativeForce.MANDATORY


def test_normative_force_statutory_laws():
    """Laws, decrees, circulars are strictly mandatory."""
    assert resolve_normative_force("Luật 135/2025/QH15") == NormativeForce.MANDATORY
    assert resolve_normative_force("15/2021/NĐ-CP") == NormativeForce.MANDATORY
    assert resolve_normative_force("31/2026/TT-BXD") == NormativeForce.MANDATORY


def test_normative_force_tcvn_voluntary_vs_referenced():
    """TCVN without citation is voluntary; cited or known referenced is mandatory by reference."""
    assert resolve_normative_force("TCVN 9999:2025") == NormativeForce.VOLUNTARY
    assert resolve_normative_force("TCVN 7336:2021") == NormativeForce.MANDATORY_BY_REFERENCE
    assert resolve_normative_force("TCVN 5738:2021") == NormativeForce.MANDATORY_BY_REFERENCE
    assert resolve_normative_force("TCVN 9999:2025", is_cited_in_clause=True) == NormativeForce.MANDATORY_BY_REFERENCE


def test_normative_force_contract_adoption():
    """Explicit contractual agreement makes any standard contract-adopted."""
    assert resolve_normative_force("TCVN 9999:2025", contract_stipulated=True) == NormativeForce.CONTRACT_ADOPTED


# ---------------------------------------------------------------------------
# 2. ProjectProfile & Statutory Cutoff Tests
# ---------------------------------------------------------------------------

def test_project_profile_creation_and_inference():
    """Verify apartment building flag inference and geometric attributes."""
    profile = ProjectProfile(
        project_name="Chung cư Tân Bình",
        project_level=ProjectLevel.CAP_I,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(
            fire_height_m=74.5,
            above_ground_floors=24,
            underground_floors=3,
            total_floor_area_m2=45000.0,
        ),
    )
    assert profile.is_apartment_building is True
    assert profile.geometry.fire_height_m == 74.5
    assert profile.is_governed_by_luat_xay_dung_2025() is False


def test_project_profile_invalid_negative_height():
    """Verify negative fire height raises validation error."""
    with pytest.raises(ValueError, match="không được âm"):
        GeometricParameters(
            fire_height_m=-5.0,
            above_ground_floors=10,
            total_floor_area_m2=1000.0,
        )


def test_project_profile_luat_xay_dung_2025_detection():
    """Milestone on or after 2026-07-01 activates Luật Xây dựng 2025."""
    profile_old = ProjectProfile(
        project_name="Dự án 2024",
        project_level=ProjectLevel.CAP_II,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(fire_height_m=50.0, above_ground_floors=15, total_floor_area_m2=20000.0),
        milestones=LegalMilestones(pccc_approval=date(2024, 5, 20)),
    )
    assert profile_old.is_governed_by_luat_xay_dung_2025() is False

    profile_new = ProjectProfile(
        project_name="Dự án 2026 Sau Luật Mới",
        project_level=ProjectLevel.CAP_I,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(fire_height_m=75.0, above_ground_floors=25, total_floor_area_m2=35000.0),
        milestones=LegalMilestones(pccc_approval=date(2026, 8, 15)),
    )
    assert profile_new.is_governed_by_luat_xay_dung_2025() is True


def test_strict_repeal_citation_validation():
    """Verify citing TT 06/2021/TT-BXD is prohibited for projects under Luật 2025."""
    profile_new = ProjectProfile(
        project_name="Dự án Hạ Long 2026",
        project_level=ProjectLevel.CAP_I,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(fire_height_m=75.0, above_ground_floors=25, total_floor_area_m2=35000.0),
        milestones=LegalMilestones(pccc_approval=date(2026, 9, 1)),
    )

    # Valid citations
    valid_citations = ["135/2025/QH15", "QCVN 06:2022/BXD", "31/2026/TT-BXD"]
    assert profile_new.validate_regulatory_citations(valid_citations) == valid_citations

    # Prohibited citation of repealed circular
    invalid_citations = ["135/2025/QH15", "Thông tư 06/2021/TT-BXD"]
    with pytest.raises(ValueError, match="06/2021/TT-BXD đã bị bãi bỏ/thay thế"):
        profile_new.validate_regulatory_citations(invalid_citations)


# ---------------------------------------------------------------------------
# 3. Scope Gate Tests
# ---------------------------------------------------------------------------

def test_scope_gate_statutory_exclusions():
    """Scope gate rejects facilities excluded by QCVN 06 §1.1.3."""
    gate = ScopeGate()
    explosive_facility = ProjectProfile(
        project_name="Nhà máy sản xuất thuốc nổ công nghiệp",
        project_level=ProjectLevel.CAP_I,
        primary_function=PrimaryFunction.F5,
        geometry=GeometricParameters(fire_height_m=12.0, above_ground_floors=2, total_floor_area_m2=5000.0),
    )
    decision = gate.evaluate_scope(explosive_facility)
    assert decision.is_applicable is False
    assert "thuốc nổ" in decision.reject_reason


def test_scope_gate_height_and_basement_threshold():
    """Special fire clearance required when H > 150m or underground floors > 3."""
    gate = ScopeGate()
    super_tall_apt = ProjectProfile(
        project_name="Chung cư Landmark Supertall",
        project_level=ProjectLevel.DAC_BIET,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(
            fire_height_m=175.0,
            above_ground_floors=50,
            underground_floors=4,
            total_floor_area_m2=120000.0,
        ),
        milestones=LegalMilestones(pccc_approval=date(2024, 10, 1)),
    )
    decision = gate.evaluate_scope(super_tall_apt)
    assert decision.is_applicable is True
    assert decision.special_clearance_required is True
    assert "Luận chứng giải pháp kỹ thuật PCCC riêng" in decision.special_clearance_reason


def test_scope_gate_edition_locking_2022():
    """PCCC approval before 2023-12-01 locks original QCVN 06:2022."""
    gate = ScopeGate()
    profile = ProjectProfile(
        project_name="Chung cư An Lạc",
        project_level=ProjectLevel.CAP_II,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(fire_height_m=45.0, above_ground_floors=15, underground_floors=1, total_floor_area_m2=18000.0),
        milestones=LegalMilestones(pccc_approval=date(2022, 11, 15)),
    )
    decision = gate.evaluate_scope(profile)
    assert decision.is_applicable is True
    assert "QCVN 04:2021/BXD" in decision.applicable_codes
    assert "QCVN 06:2022/BXD" in decision.applicable_codes
    assert "Nguyên bản 2022" in decision.edition_map["QCVN 06:2022/BXD"]
    assert "Nguyên bản 2021" in decision.edition_map["QCVN 04:2021/BXD"]
    assert any("2027-06-15" in w for w in decision.warnings)


def test_scope_gate_edition_locking_post_2026():
    """Projects after 2026-12-15 use living standards and Luật 2025 era."""
    gate = ScopeGate()
    profile = ProjectProfile(
        project_name="Chung cư Hiện Đại 2027",
        project_level=ProjectLevel.CAP_I,
        primary_function=PrimaryFunction.F1_2,
        geometry=GeometricParameters(fire_height_m=80.0, above_ground_floors=26, underground_floors=2, total_floor_area_m2=50000.0),
        milestones=LegalMilestones(pccc_approval=date(2027, 2, 1)),
        fire_protection=ActiveFireProtection(
            has_sprinkler=True,
            sprinkler_coverage=SprinklerCoverage.WHOLE_BUILDING,
            has_auto_fire_alarm=True,
        ),
    )
    decision = gate.evaluate_scope(profile)
    assert decision.is_applicable is True
    assert decision.legal_era == "LUAT_XAY_DUNG_2025"
    assert "Living Standard TT 31/2026" in decision.edition_map["QCVN 04:2021/BXD"]
    assert "Hợp nhất SĐ 1:2023" in decision.edition_map["QCVN 06:2022/BXD"]
    assert decision.normative_forces["TCVN 7336:2021"] == NormativeForce.MANDATORY_BY_REFERENCE
    assert decision.normative_forces["TCVN 5738:2021"] == NormativeForce.MANDATORY_BY_REFERENCE


# ---------------------------------------------------------------------------
# 4. ComplianceAssessment Output Contract Tests
# ---------------------------------------------------------------------------

def test_compliance_assessment_serialization_and_markdown():
    """Verify ComplianceAssessment contract and Markdown report generation."""
    assessment = ComplianceAssessment(
        assessment_id="ASM-2026-TEST",
        project_name="Tòa nhà Hải Phòng Riverside",
        assessment_date="2026-10-01",
        overall_status=OverallStatus.CONDITIONAL,
        findings=[
            Finding(
                regulation_reference="QCVN 04:2021/BXD §2.10.2.1b",
                check_description="Số lượng chỗ sạc xe điện trong phân vùng tầng hầm",
                status=FindingStatus.PASS,
                actual_value="10 chỗ (mô tô điện)",
                required_value="≤ 50 chỗ",
                explanation="10 chỗ sạc nằm trong hạn mức 50 chỗ.",
                regulatory_text="Số lượng chỗ sạc trong mỗi phân vùng khi bố trí trong tầng bán hầm và tầng hầm không lớn hơn 50 chỗ sạc cho mô tô điện.",
                clause_type=ClauseType.MANDATORY,
            )
        ],
        legal_warnings=[
            LegalWarning(
                warning_type=WarningType.NEW_REQUIREMENT,
                title="Bổ sung yêu cầu trạm sạc xe điện",
                description="Hồ sơ cần cập nhật theo Thông tư 31/2026/TT-BXD trước 15/06/2027.",
                deadline="2027-06-15",
                applicable_regulation="QCVN 04:2021/BXD Mục 3.3",
            )
        ],
        recommendations=[
            Recommendation(
                priority=PriorityLevel.URGENT,
                description="Bố trí khoang cháy riêng với tường ngăn cháy loại 1 cho khu vực sạc.",
                applicable_regulation="QCVN 04:2021/BXD Mục 2.10.2.1e",
                responsible_party="Đơn vị tư vấn PCCC",
            )
        ],
        traceability=TraceabilityInfo(
            version_at_assessment="QCVN-04-2021-BXD (Living Standard TT 31/2026)",
        ),
    )

    md = assessment.to_markdown()
    assert "# BÁO CÁO THẨM ĐỊNH TUÂN THỦ" in md
    assert "Tòa nhà Hải Phòng Riverside" in md
    assert "PASS ✅" in md
    assert "2027-06-15" in md
    assert "[URGENT]" in md
    assert "Bố trí khoang cháy riêng" in md
