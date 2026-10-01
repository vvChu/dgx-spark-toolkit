"""Scope Gate and Transitional Provisions Engine (OKF Standard).
=============================================================================
Evaluates whether legal regulations apply to a specific ProjectProfile before
retrieval, verifies statutory exclusions, resolves normative force, and locks
the exact historical edition based on project milestones.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- QCVN 06:2022/BXD §1.1.2, §1.1.3, §1.1.4 (SĐ1:2023)
- QCVN 04:2021/BXD (TT 31/2026/TT-BXD)
- Luật Xây dựng 2025 (135/2025/QH15) Cutoff: 2026-07-01
"""

from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from domain.normative_force import NormativeForce, resolve_normative_force
from domain.project_profile import (
    LUAT_XAY_DUNG_2025_EFFECTIVE_DATE,
    PrimaryFunction,
    ProjectLevel,
    ProjectProfile,
)

QCVN_06_AMENDMENT_CUTOFF = date(2023, 12, 1)
QCVN_04_AMENDMENT_CUTOFF = date(2026, 12, 15)
QCVN_04_GRACE_PERIOD_END = date(2027, 6, 15)

EXCLUDED_FACILITY_KEYWORDS = (
    "thuốc nổ",
    "kho đạn",
    "pháo hoa",
    "lọc dầu",
    "hóa dầu",
    "hạt nhân",
    "lò phản ứng",
    "công trình biển",
    "giàn khoan",
)


class ScopeDecision(BaseModel):
    """Quyết định kiểm soát phạm vi và định vị phiên bản quy chuẩn."""
    is_applicable: bool
    reject_reason: Optional[str] = None
    applicable_codes: List[str] = Field(default_factory=list)
    edition_map: Dict[str, str] = Field(default_factory=dict)
    special_clearance_required: bool = False
    special_clearance_reason: Optional[str] = None
    legal_era: str = "LUAT_XAY_DUNG_2014"
    normative_forces: Dict[str, NormativeForce] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)


class ScopeGate:
    """Kiểm tra điều kiện áp dụng quy chuẩn kỹ thuật cho dự án xây dựng."""

    def evaluate_scope(self, profile: ProjectProfile) -> ScopeDecision:
        """Thực hiện chu trình 5 bước kiểm định phạm vi pháp lý.

        1. Rà soát danh mục loại trừ luật định (QCVN 06 §1.1.3).
        2. Rà soát ngưỡng hình học & số tầng hầm vượt trần (§1.1.2).
        3. Phân định quy chuẩn chuyên ngành bắt buộc (QCVN 04 vs QCVN 06).
        4. Xác lập kỷ nguyên pháp lý & bãi bỏ TT 06/2021 (Luật 2025 vs Luật 2014).
        5. Định vị phiên bản quy chuẩn theo điều khoản chuyển tiếp.
        """
        # Bước 1: Loại trừ tuyệt đối
        name_lower = profile.project_name.lower()
        for kw in EXCLUDED_FACILITY_KEYWORDS:
            if kw in name_lower:
                return ScopeDecision(
                    is_applicable=False,
                    reject_reason=(
                        f"Công trình thuộc phạm vi loại trừ của QCVN 06:2022/BXD Mục 1.1.3 "
                        f"(từ khóa phát hiện: '{kw}'). Phải áp dụng quy chuẩn chuyên ngành riêng biệt."
                    ),
                    warnings=["Loại trừ toàn bộ quy chuẩn chung do tính chất công trình nguy hiểm đặc thù."],
                )

        # Bước 2: Ngưỡng hình học
        special_clearance = False
        special_reason = None
        if profile.is_apartment_building or profile.primary_function in (PrimaryFunction.F1_1, PrimaryFunction.F1_2):
            if profile.geometry.fire_height_m > 150.0 or profile.geometry.underground_floors > 3:
                special_clearance = True
                special_reason = (
                    f"Quy mô công trình (H={profile.geometry.fire_height_m}m, "
                    f"{profile.geometry.underground_floors} tầng hầm) vượt ngưỡng quy chuẩn thông thường "
                    f"của QCVN 06:2022 Mục 1.1.2 (≤150m, ≤3 hầm). Bắt buộc lập Luận chứng giải pháp "
                    f"kỹ thuật PCCC riêng và được Cục Cảnh sát PCCC & CNCH thẩm duyệt."
                )

        # Bước 3: Xác định quy chuẩn áp dụng & Normative Force
        applicable_codes: List[str] = ["QCVN 06:2022/BXD"]
        normative_map: Dict[str, NormativeForce] = {
            "QCVN 06:2022/BXD": NormativeForce.MANDATORY
        }

        # QCVN 04 áp dụng cho chung cư từ Cấp III trở lên
        is_apt = profile.is_apartment_building or profile.primary_function in (PrimaryFunction.F1_1, PrimaryFunction.F1_2)
        valid_level = profile.project_level in (
            ProjectLevel.DAC_BIET,
            ProjectLevel.CAP_I,
            ProjectLevel.CAP_II,
            ProjectLevel.CAP_III,
        )
        if is_apt and valid_level:
            applicable_codes.append("QCVN 04:2021/BXD")
            normative_map["QCVN 04:2021/BXD"] = NormativeForce.MANDATORY

        # Bổ sung các tiêu chuẩn viện dẫn bắt buộc theo giải pháp PCCC chủ động
        if profile.fire_protection.has_sprinkler:
            normative_map["TCVN 7336:2021"] = resolve_normative_force("TCVN 7336:2021", is_cited_in_clause=True)
        if profile.fire_protection.has_auto_fire_alarm:
            normative_map["TCVN 5738:2021"] = resolve_normative_force("TCVN 5738:2021", is_cited_in_clause=True)

        # Bước 4: Xác lập kỷ nguyên pháp lý
        anchor_date = profile.milestones.latest_anchor_date()
        warnings: List[str] = []
        if profile.is_governed_by_luat_xay_dung_2025():
            legal_era = "LUAT_XAY_DUNG_2025"
            warnings.append(
                f"Dự án áp dụng Luật Xây dựng 2025 (135/2025/QH15, hiệu lực {LUAT_XAY_DUNG_2025_EFFECTIVE_DATE}). "
                "Cấm tuyệt đối dẫn chiếu Thông tư 06/2021/TT-BXD."
            )
        else:
            legal_era = "LUAT_XAY_DUNG_2014"

        # Bước 5: Điều khoản chuyển tiếp khóa phiên bản (Edition Locking)
        edition_map: Dict[str, str] = {}

        # Khóa phiên bản QCVN 06
        pccc_date = profile.milestones.pccc_approval or anchor_date
        if pccc_date and pccc_date < QCVN_06_AMENDMENT_CUTOFF:
            edition_map["QCVN 06:2022/BXD"] = "QCVN 06:2022/BXD (Nguyên bản 2022)"
        else:
            edition_map["QCVN 06:2022/BXD"] = "QCVN 06:2022/BXD (Hợp nhất SĐ 1:2023)"

        # Khóa phiên bản QCVN 04
        if "QCVN 04:2021/BXD" in applicable_codes:
            if pccc_date and pccc_date < QCVN_04_AMENDMENT_CUTOFF:
                edition_map["QCVN 04:2021/BXD"] = "QCVN 04:2021/BXD (Nguyên bản 2021)"
                warnings.append(
                    f"Hồ sơ PCCC/TKCS duyệt trước ngày {QCVN_04_AMENDMENT_CUTOFF}. "
                    f"Áp dụng thời hạn ân hạn rà soát khu vực trạm sạc xe điện đến ngày {QCVN_04_GRACE_PERIOD_END} "
                    "(Thông tư 31/2026/TT-BXD)."
                )
            else:
                edition_map["QCVN 04:2021/BXD"] = "QCVN 04:2021/BXD (Living Standard TT 31/2026)"

        return ScopeDecision(
            is_applicable=True,
            applicable_codes=applicable_codes,
            edition_map=edition_map,
            special_clearance_required=special_clearance,
            special_clearance_reason=special_reason,
            legal_era=legal_era,
            normative_forces=normative_map,
            warnings=warnings,
        )
