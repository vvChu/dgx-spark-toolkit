"""Project Profile Domain Model (OKF Enterprise Standard).
=============================================================================
Encapsulates building physical, functional, fire protection, and statutory
temporal parameters to gate legal applicability and drive neuro-symbolic checks.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Statutory Cutoff: Luật Xây dựng 2025 (135/2025/QH15) effective 2026-07-01
- Grok 4.7 xhigh C2: Scope Gate & Project Profile Schema
- Hermes Deep Domain Response
"""

from datetime import date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

LUAT_XAY_DUNG_2025_EFFECTIVE_DATE = date(2026, 7, 1)


class ProjectLevel(str, Enum):
    """Cấp công trình xây dựng theo phân cấp pháp lý Việt Nam."""
    DAC_BIET = "Đặc_biệt"
    CAP_I = "Cấp_I"
    CAP_II = "Cấp_II"
    CAP_III = "Cấp_III"
    CAP_IV = "Cấp_IV"


class PrimaryFunction(str, Enum):
    """Phân nhóm công năng nguy hiểm cháy theo QCVN 06:2022/BXD Bảng 6."""
    F1_1 = "F1.1"  # Nhà ở tập thể, ký túc xá, mầm non
    F1_2 = "F1.2"  # Nhà chung cư
    F1_3 = "F1.3"  # Nhà công cộng đa năng, thương mại
    F2 = "F2"      # Nhà văn hóa, câu lạc bộ, thể thao
    F3 = "F3"      # Nhà thương mại, ăn uống, dịch vụ, khách sạn
    F4 = "F4"      # Cơ sở giáo dục, bệnh viện, hành chính
    F5 = "F5"      # Nhà sản xuất, nhà kho, công nghiệp


class StructureResistanceGrade(str, Enum):
    """Bậc chịu lửa của công trình theo QCVN 06:2022 Bảng 4."""
    BAC_I = "Bậc_I"
    BAC_II = "Bậc_II"
    BAC_III = "Bậc_III"
    BAC_IV = "Bậc_IV"
    BAC_V = "Bậc_V"


class SprinklerCoverage(str, Enum):
    """Phạm vi bảo vệ của hệ thống chữa cháy tự động Sprinkler."""
    WHOLE_BUILDING = "whole_building"
    PARTIAL = "partial"
    NONE = "none"


class GeometricParameters(BaseModel):
    """Thông số hình học và quy mô công trình."""
    fire_height_m: float = Field(..., description="Chiều cao PCCC (m) tính theo QCVN 06:2022 §3.1.1")
    above_ground_floors: int = Field(..., ge=1, description="Số tầng nổi")
    underground_floors: int = Field(default=0, ge=0, description="Số tầng hầm")
    total_floor_area_m2: float = Field(..., gt=0, description="Tổng diện tích sàn xây dựng (m²)")
    max_fire_compartment_area_m2: Optional[float] = Field(default=None, description="Diện tích khoang cháy lớn nhất (m²)")
    building_volume_m3: Optional[float] = Field(default=None, description="Khối tích công trình (m³)")
    floor_area_factor: Optional[float] = Field(default=None, description="Hệ số không gian sàn")

    @field_validator("fire_height_m")
    @classmethod
    def validate_height(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Chiều cao PCCC không được âm")
        return v


class ActiveFireProtection(BaseModel):
    """Hệ thống kỹ thuật phòng cháy chữa cháy chủ động."""
    has_sprinkler: bool = False
    sprinkler_coverage: SprinklerCoverage = SprinklerCoverage.NONE
    sprinkler_standard: Optional[str] = "TCVN 7336:2021"

    has_drencher: bool = False
    drencher_type: Optional[str] = None  # water_curtain, foam, deluge

    has_mechanical_smoke_extraction: bool = False
    smoke_extraction_standard: Optional[str] = "QCVN 06:2022/BXD §3.1.9 + Phụ lục D"

    has_auto_fire_alarm: bool = False
    alarm_type: Optional[str] = None  # conventional, addressable, voice_evacuation

    has_gaseous_suppression: bool = False


class LegalMilestones(BaseModel):
    """4 mốc thời gian pháp lý chủ chốt để khóa quy chuẩn áp dụng."""
    planning_approval: Optional[date] = Field(default=None, description="Mốc 1: Phê duyệt quy hoạch 1/500")
    cs_design_approval: Optional[date] = Field(default=None, description="Mốc 2: Thẩm định thiết kế cơ sở")
    pccc_approval: Optional[date] = Field(default=None, description="Mốc 3: Thẩm duyệt thiết kế PCCC")
    building_permit: Optional[date] = Field(default=None, description="Mốc 4: Cấp giấy phép xây dựng")
    renovation_submission: Optional[date] = Field(default=None, description="Mốc nộp hồ sơ cải tạo, điều chỉnh")

    def latest_anchor_date(self) -> Optional[date]:
        """Return the most decisive anchor date (prioritizing PCCC approval, then permit, then design)."""
        if self.pccc_approval:
            return self.pccc_approval
        if self.building_permit:
            return self.building_permit
        if self.cs_design_approval:
            return self.cs_design_approval
        if self.planning_approval:
            return self.planning_approval
        return None


class ProjectProfile(BaseModel):
    """Hồ sơ dự án chuẩn hóa phục vụ kiểm soát phạm vi và thẩm định tuân thủ."""
    project_name: str
    project_level: ProjectLevel
    primary_function: PrimaryFunction
    secondary_functions: List[PrimaryFunction] = Field(default_factory=list)

    mixed_use: bool = False
    dominant_function: Optional[PrimaryFunction] = None

    is_apartment_building: bool = False
    has_individual_houses: bool = False

    fire_hazard_category: Optional[str] = None
    structural_resistance_grade: StructureResistanceGrade = StructureResistanceGrade.BAC_I

    geometry: GeometricParameters
    fire_protection: ActiveFireProtection = Field(default_factory=ActiveFireProtection)
    milestones: LegalMilestones = Field(default_factory=LegalMilestones)

    is_renovation: bool = False
    renovation_scope: Optional[str] = None  # partial, entire_building

    @model_validator(mode="after")
    def infer_apartment_flag(self) -> "ProjectProfile":
        """Auto-set is_apartment_building if primary function is F1.2."""
        if self.primary_function == PrimaryFunction.F1_2:
            self.is_apartment_building = True
        return self

    def is_governed_by_luat_xay_dung_2025(self) -> bool:
        """Determines if the project is strictly governed by Luật Xây dựng 2025 (effective 2026-07-01)."""
        anchor = self.milestones.latest_anchor_date()
        if anchor and anchor >= LUAT_XAY_DUNG_2025_EFFECTIVE_DATE:
            return True
        return False

    def validate_regulatory_citations(self, citations: List[str]) -> List[str]:
        """Validate legal citations against temporal statutory constraints.

        Raises:
            ValueError: If Thông tư 06/2021/TT-BXD is cited for projects governed by Luật Xây dựng 2025.
        """
        is_new_law = self.is_governed_by_luat_xay_dung_2025()
        for citation in citations:
            norm = citation.upper()
            if "06/2021/TT-BXD" in norm and is_new_law:
                raise ValueError(
                    f"Vi phạm căn cứ pháp lý: Thông tư 06/2021/TT-BXD đã bị bãi bỏ/thay thế "
                    f"bởi Luật Xây dựng 2025 (135/2025/QH15) từ {LUAT_XAY_DUNG_2025_EFFECTIVE_DATE}. "
                    f"Cấm dẫn chiếu cho hồ sơ dự án '{self.project_name}'."
                )
        return citations
