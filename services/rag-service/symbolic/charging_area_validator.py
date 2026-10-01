"""EV Charging Area and Battery Swap Cabinet Validator (QCVN 04:2021 + SĐ 01:2026).
=============================================================================
Verifies technical compliance of electric vehicle charging areas per Thông tư
31/2026/TT-BXD sửa đổi QCVN 04:2021/BXD Mục 2.10 & 2.11:
- Spot limits per zone in basements (<= 25 cars, <= 50 motorbikes).
- Fire compartment area caps (<= 300m² for motorbikes in basements, <= 1200m² for cars).
- Fire separation: Type 1 fire wall OR >= 6m clearance OR drencher curtain (>= 1 L/s/m).
- Compulsory active systems: 24/24 alarm, auto sprinkler, smoke extraction, CO/HF warning.
- Basement charger stand power rating limit (<= 22 kW).
- Statutory transitional review grace period until 2027-06-15.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- TT 31/2026/TT-BXD Verbatim Text
"""

from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field

from domain.compliance import (
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


class ChargingAreaParameters(BaseModel):
    """Tham số thiết kế khu vực sạc xe điện."""
    location: str = Field(..., description="basement, semi_basement, ground, outdoor")
    car_spots: int = 0
    motorcycle_spots: int = 0
    compartment_area_m2: float
    has_fire_wall_type_1: bool = False
    open_space_distance_m: float = 0.0
    has_drencher_curtain: bool = False
    drencher_flow_per_meter: float = 0.0
    has_auto_alarm_24h: bool = False
    has_auto_sprinkler: bool = False
    has_smoke_extraction: bool = False
    has_co_hf_warning: bool = False
    charger_power_kw: float = 7.4
    pccc_approval_date: Optional[date] = None


class ChargingAreaValidator:
    """Symbolic validator for EV charging stations in residential buildings."""

    def validate(
        self,
        project_name: str,
        params: ChargingAreaParameters,
        assessment_id: str = "ASM-EV-CHARGING",
    ) -> ComplianceAssessment:
        """Validate all technical predicates of Section 2.10 QCVN 04:2021 + SĐ 01:2026."""
        findings: List[Finding] = []
        warnings: List[LegalWarning] = []
        recommendations: List[Recommendation] = []
        is_basement = params.location in ("basement", "semi_basement")

        # 1. Số lượng chỗ sạc trong phân vùng (Mục 2.10.2.1b)
        if is_basement:
            car_pass = params.car_spots <= 25
            findings.append(Finding(
                regulation_reference="QCVN 04:2021/BXD (SĐ 01:2026) Mục 2.10.2.1b",
                check_description="Số lượng chỗ sạc ô tô điện trong phân vùng tầng hầm",
                status=FindingStatus.PASS if car_pass else FindingStatus.FAIL,
                actual_value=f"{params.car_spots} chỗ",
                required_value="≤ 25 chỗ/phân vùng tại tầng hầm",
                explanation="Đạt yêu cầu phân vùng ô tô điện." if car_pass else "Vượt quá định mức tối đa 25 chỗ.",
                regulatory_text="Số lượng chỗ sạc trong mỗi phân vùng khi bố trí trong tầng bán hầm và tầng hầm không lớn hơn 25 chỗ sạc cho ô tô điện.",
                clause_type=ClauseType.MANDATORY,
            ))

            moto_pass = params.motorcycle_spots <= 50
            findings.append(Finding(
                regulation_reference="QCVN 04:2021/BXD (SĐ 01:2026) Mục 2.10.2.1b",
                check_description="Số lượng chỗ sạc mô tô/xe gắn máy điện trong phân vùng tầng hầm",
                status=FindingStatus.PASS if moto_pass else FindingStatus.FAIL,
                actual_value=f"{params.motorcycle_spots} chỗ",
                required_value="≤ 50 chỗ/phân vùng tại tầng hầm",
                explanation="Đạt yêu cầu phân vùng mô tô điện." if moto_pass else "Vượt quá định mức tối đa 50 chỗ.",
                regulatory_text="...hoặc 50 chỗ sạc cho mô tô điện, xe gắn máy điện, xe đạp điện.",
                clause_type=ClauseType.MANDATORY,
            ))

        # 2. Diện tích khoang cháy (Mục 2.10.2.1g)
        if is_basement:
            max_area = 1200.0 if params.car_spots > 0 else 300.0
            area_type = "ô tô" if params.car_spots > 0 else "mô tô"
            area_pass = params.compartment_area_m2 <= max_area
            findings.append(Finding(
                regulation_reference="QCVN 04:2021/BXD (SĐ 01:2026) Mục 2.10.2.1g",
                check_description=f"Diện tích khoang cháy sạc {area_type} tại tầng hầm",
                status=FindingStatus.PASS if area_pass else FindingStatus.FAIL,
                actual_value=f"{params.compartment_area_m2} m²",
                required_value=f"≤ {max_area} m²",
                explanation=f"Diện tích khoang cháy trong hạn mức cho phép {max_area} m²." if area_pass else "Vượt diện tích tối đa cho phép.",
                regulatory_text="Diện tích lớn nhất cho phép của một tầng nhà trong phạm vi một khoang cháy không lớn hơn 300 m2 nếu bố trí trong tầng bán hầm hoặc tầng hầm (cho xe hai bánh) hoặc 1200 m2 (cho ô tô).",
                clause_type=ClauseType.MANDATORY,
            ))

        # 3. Ngăn cách khoang cháy (Mục 2.10.2.1f, 2.10.2.1g)
        sep_pass = (
            params.has_fire_wall_type_1
            or params.open_space_distance_m >= 6.0
            or (params.has_drencher_curtain and params.drencher_flow_per_meter >= 1.0)
        )
        findings.append(Finding(
            regulation_reference="QCVN 04:2021/BXD (SĐ 01:2026) Mục 2.10.2.1f & g",
            check_description="Ngăn cách khoang cháy khu vực sạc xe điện",
            status=FindingStatus.PASS if sep_pass else FindingStatus.FAIL,
            actual_value=(
                f"Tường loại 1: {params.has_fire_wall_type_1}, Khoảng cách: {params.open_space_distance_m}m, "
                f"Drencher: {params.has_drencher_curtain} ({params.drencher_flow_per_meter} L/s/m)"
            ),
            required_value="Tường ngăn cháy loại 1 HOẶC khoảng trống ≥ 6m HOẶC màn nước drencher (≥ 1 L/s/m)",
            explanation="Giải pháp ngăn cách khoang cháy hợp chuẩn." if sep_pass else "Thiếu giải pháp ngăn cách khoang cháy hợp chuẩn.",
            regulatory_text="Ngăn cách bằng tường ngăn cháy loại 1 hoặc khoảng cách an toàn không nhỏ hơn 6 m hoặc màn ngăn cháy drencher.",
            clause_type=ClauseType.MANDATORY,
        ))

        # 4. Hệ thống PCCC bắt buộc (Mục 2.10.2.1e)
        all_systems = (
            params.has_auto_alarm_24h
            and params.has_auto_sprinkler
            and params.has_smoke_extraction
            and params.has_co_hf_warning
        )
        findings.append(Finding(
            regulation_reference="QCVN 04:2021/BXD (SĐ 01:2026) Mục 2.10.2.1e",
            check_description="Trang bị đầy đủ 4 hệ thống PCCC bắt buộc cho khu vực sạc",
            status=FindingStatus.PASS if all_systems else FindingStatus.FAIL,
            actual_value=(
                f"Báo cháy 24h: {params.has_auto_alarm_24h}, Sprinkler: {params.has_auto_sprinkler}, "
                f"Hút khói: {params.has_smoke_extraction}, Cảnh báo CO/HF: {params.has_co_hf_warning}"
            ),
            required_value="Bắt buộc có đủ: (1) Báo cháy 24/24, (2) Chữa cháy tự động, (3) Thoát khói, (4) Cảnh báo CO/HF",
            explanation="Đầy đủ 4 hệ thống PCCC." if all_systems else "Thiếu ít nhất một hệ thống PCCC bắt buộc.",
            regulatory_text="Khu vực sạc phải có: Hệ thống báo cháy tự động, hệ thống camera giám sát có người trực 24/24; Hệ thống chữa cháy tự động; Hệ thống hút khói; Thiết bị cảnh báo rò rỉ CO, HF.",
            clause_type=ClauseType.MANDATORY,
        ))

        # 5. Công suất trụ sạc tại tầng hầm (Mục 2.10.2.1k)
        if is_basement:
            power_pass = params.charger_power_kw <= 22.0
            findings.append(Finding(
                regulation_reference="QCVN 04:2021/BXD (SĐ 01:2026) Mục 2.10.2.1k",
                check_description="Công suất danh định của trụ sạc tại tầng hầm",
                status=FindingStatus.PASS if power_pass else FindingStatus.FAIL,
                actual_value=f"{params.charger_power_kw} kW",
                required_value="≤ 22 kW/trụ sạc tại tầng hầm",
                explanation="Công suất trụ sạc an toàn trong tầng hầm." if power_pass else "Công suất trụ sạc vượt 22 kW tại tầng hầm.",
                regulatory_text="Công suất danh định của trụ sạc lắp đặt trong tầng bán hầm và tầng hầm không được vượt quá 22 kW.",
                clause_type=ClauseType.MANDATORY,
            ))

        # 6. Điều khoản chuyển tiếp (Mục 3.3)
        if params.pccc_approval_date and params.pccc_approval_date < date(2026, 12, 15):
            warnings.append(LegalWarning(
                warning_type=WarningType.GRACE_PERIOD,
                title="Ân hạn rà soát thiết kế trạm sạc xe điện",
                description="Hồ sơ PCCC/TKCS đã phê duyệt trước 15/12/2026 có thời hạn ân hạn đến 15/06/2027 để hoàn thành rà soát bổ sung trạm sạc.",
                deadline="2027-06-15",
                applicable_regulation="QCVN 04:2021/BXD Mục 3.3 (Thông tư 31/2026/TT-BXD)",
            ))
            recommendations.append(Recommendation(
                priority=PriorityLevel.HIGH,
                description="Hoàn thành hồ sơ điều chỉnh thiết kế khu vực sạc xe điện trước thời hạn 15/06/2027.",
                applicable_regulation="QCVN 04:2021/BXD Mục 3.3",
                responsible_party="Chủ đầu tư / Đơn vị tư vấn thiết kế",
            ))

        # Đánh giá trạng thái tổng thể
        failed_findings = [f for f in findings if f.status == FindingStatus.FAIL]
        overall = OverallStatus.COMPLIANT if not failed_findings else OverallStatus.NON_COMPLIANT

        return ComplianceAssessment(
            assessment_id=assessment_id,
            project_name=project_name,
            assessment_date=date.today().isoformat(),
            overall_status=overall,
            findings=findings,
            legal_warnings=warnings,
            recommendations=recommendations,
            traceability=TraceabilityInfo(
                version_at_assessment="QCVN 04:2021/BXD (Living Standard TT 31/2026/TT-BXD)",
            ),
        )
