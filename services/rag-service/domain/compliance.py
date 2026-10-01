"""Output Contract Domain Models (OKF Compliance Assessment Standard).
=============================================================================
Schema-locked structures for field engineers and regulatory submission.
Provides deterministic structured assessment and printable Markdown defense dossier.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Hermes Output Contract & Grok 4.7 xhigh Verification
"""

from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class OverallStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    CONDITIONAL = "CONDITIONAL"


class FindingStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "N/A"


class ClauseType(str, Enum):
    MANDATORY = "mandatory"
    CONDITIONAL = "conditional"
    ADVISORY = "advisory"
    FOOTNOTE_EXCEPTION = "footnote_exception"


class WarningType(str, Enum):
    GRACE_PERIOD = "grace_period"
    SCOPE_CHANGE = "scope_change"
    CONFLICT = "conflict"
    NEW_REQUIREMENT = "new_requirement"
    STATUTORY_REPEAL = "statutory_repeal"


class PriorityLevel(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Finding(BaseModel):
    """Một kết quả kiểm tra điều khoản cụ thể."""
    regulation_reference: str = Field(..., description="e.g. QCVN 06:2022/BXD §3.1.7, Bảng 4")
    check_description: str
    status: FindingStatus
    actual_value: Optional[str] = None
    required_value: Optional[str] = None
    explanation: str
    regulatory_text: str = Field(..., description="Trích dẫn nguyên văn điều khoản pháp lý")
    clause_type: ClauseType = ClauseType.MANDATORY


class LegalWarning(BaseModel):
    """Cảnh báo pháp lý chuyển tiếp hoặc xung đột hiệu lực."""
    warning_type: WarningType
    title: str
    description: str
    deadline: Optional[str] = None
    applicable_regulation: str


class Recommendation(BaseModel):
    """Khuyến nghị hành động kỹ thuật cho chủ đầu tư/tư vấn."""
    priority: PriorityLevel
    description: str
    applicable_regulation: str
    responsible_party: Optional[str] = None


class DocumentRef(BaseModel):
    doc_id: str
    version: str
    amendments: List[str] = Field(default_factory=list)


class TableRef(BaseModel):
    table_id: str
    title: str


class FootnoteRef(BaseModel):
    table_id: str
    footnote_number: int
    content: str


class TraceabilityInfo(BaseModel):
    """Dữ liệu truy xuất nguồn gốc điều khoản, bảng số liệu và chú thích."""
    documents_used: List[DocumentRef] = Field(default_factory=list)
    tables_referenced: List[TableRef] = Field(default_factory=list)
    footnotes_applied: List[FootnoteRef] = Field(default_factory=list)
    version_at_assessment: str


class ComplianceAssessment(BaseModel):
    """Bản giao kèo kết quả thẩm định tuân thủ toàn diện (Output Contract)."""
    assessment_id: str
    project_name: str
    assessment_date: str
    assessor: str = "Hệ thống RAG OKF"
    overall_status: OverallStatus
    findings: List[Finding] = Field(default_factory=list)
    legal_warnings: List[LegalWarning] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    traceability: TraceabilityInfo

    def to_markdown(self) -> str:
        """Render markdown defense dossier for construction engineers."""
        status_icons = {
            OverallStatus.COMPLIANT: "✅ ĐẠT (COMPLIANT)",
            OverallStatus.NON_COMPLIANT: "❌ KHÔNG ĐẠT (NON_COMPLIANT)",
            OverallStatus.CONDITIONAL: "⚠️ ĐẠT CÓ ĐIỀU KIỆN (CONDITIONAL)",
        }
        finding_icons = {
            FindingStatus.PASS: "PASS ✅",
            FindingStatus.FAIL: "FAIL ❌",
            FindingStatus.CONDITIONAL: "CONDITIONAL ⚠️",
            FindingStatus.NOT_APPLICABLE: "N/A ⚪",
        }

        lines = [
            "# BÁO CÁO THẨM ĐỊNH TUÂN THỦ QUY CHUẨN XÂY DỰNG & PCCC",
            f"**DỰ ÁN**: {self.project_name}",
            "",
            "## 1. THÔNG TIN TỔNG QUAN",
            f"- **Mã hồ sơ**: {self.assessment_id}",
            f"- **Ngày thẩm định**: {self.assessment_date}",
            f"- **Đơn vị thẩm định**: {self.assessor}",
            f"- **Phiên bản quy chuẩn**: {self.traceability.version_at_assessment}",
            f"- **Kết luận tổng thể**: {status_icons.get(self.overall_status, str(self.overall_status))}",
            "",
            "## 2. KẾT QUẢ CHI TIẾT THEO TỪNG ĐIỀU KHOẢN",
        ]

        for i, f in enumerate(self.findings, 1):
            lines.extend([
                f"### 2.{i} {f.check_description} — {finding_icons.get(f.status, str(f.status))}",
                f"- **Căn cứ**: `{f.regulation_reference}` ({f.clause_type.value})",
                f"- **Giá trị thực tế dự án**: {f.actual_value or 'Chưa xác định'}",
                f"- **Yêu cầu quy chuẩn**: {f.required_value or 'Theo quy định hiện hành'}",
                f"- **Giải trình đánh giá**: {f.explanation}",
                f"- **Trích dẫn nguyên văn**: *\"{f.regulatory_text}\"*",
                "",
            ])

        if self.legal_warnings:
            lines.extend(["## 3. CẢNH BÁO PHÁP LÝ & ĐIỀU KHOẢN CHUYỂN TIẾP"])
            for w in self.legal_warnings:
                deadline_str = f" (Hạn chót: **{w.deadline}**)" if w.deadline else ""
                lines.extend([
                    f"⚠️ **[{w.warning_type.value.upper()}] {w.title}**{deadline_str}",
                    f"- Căn cứ: `{w.applicable_regulation}`",
                    f"- Nội dung: {w.description}",
                    "",
                ])

        if self.recommendations:
            lines.extend(["## 4. KHUYẾN NGHỊ HÀNH ĐỘNG"])
            for r in self.recommendations:
                lines.append(
                    f"- **[{r.priority.value.upper()}]** {r.description} "
                    f"*(Theo `{r.applicable_regulation}`, trách nhiệm: {r.responsible_party or 'Chủ đầu tư/Tư vấn'})*"
                )
            lines.append("")

        lines.extend([
            "---",
            "*Báo cáo này được kết xuất tự động từ hệ thống RAG OKF có khóa bảo đảm căn cứ nguyên văn. "
            "Kỹ sư chủ trì đối soát trực tiếp với hồ sơ thiết kế kỹ thuật trước khi trình cơ quan thẩm duyệt.*",
        ])

        return "\n".join(lines)
