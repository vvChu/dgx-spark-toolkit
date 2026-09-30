"""Deterministic Gate Tests for QCVN 06:2022/BXD Master Consolidation.

Ensures that:
1. All core technical clauses of QCVN 06:2022/BXD Master match the verbatim legal text
   of Amendment 1:2023 (Thông tư 09/2023/TT-BXD, effective 2023-12-01).
2. Citation lines (> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD...]*) are present in every amended section.
3. Repealed sections (1.3, 7.4) are explicitly marked as repealed.
4. Un-nested Bảng 10 presents clean verbatim data table without blockquote interference.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding & Mandatory Acquisition Invariant
- Grok 4.7 xhigh Verdict: Living Standard Consolidation Gate
"""

import re
from pathlib import Path
import pytest

VAULT_DIR = Path("/home/vvc/ccba/ccba-legal-knowledge/legal_docs/02_qcvn/qcvn_06_2022_bxd")
MASTER_FILE = VAULT_DIR / "qcvn_06_2022_bxd.md"

CITATION_SUBSTR = "Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023)"
REPEAL_SUBSTR = "Bãi bỏ bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023)"


@pytest.fixture(scope="module")
def master_content() -> str:
    if not MASTER_FILE.exists():
        pytest.skip(f"Master file not found at {MASTER_FILE}")
    return MASTER_FILE.read_text(encoding="utf-8")


def _get_section_text(master_content: str, anchor_id: str) -> str:
    """Extracts text of a given section anchor up to the next anchor."""
    pattern = rf'(<a\s+id="{anchor_id}"[^>]*></a>.*?)(?=\n<a\s+id=|\n##\s+|\Z)'
    m = re.search(pattern, master_content, re.DOTALL)
    assert m is not None, f"Anchor '{anchor_id}' not found in master file"
    return m.group(1)


class TestQcvnConsolidationGate:
    """Deterministic Verification Suite for Living Standard Consolidation."""

    def test_loi_noi_dau_sđ1_provenance(self, master_content: str):
        """Verify Lời nói đầu includes SĐ1 promulgation info."""
        header_area = master_content[:6000]
        assert "Thông tư số 09/2023/TT-BXD" in header_area
        assert "Sửa đổi 1:2023" in header_area
        assert "01 tháng 12 năm 2023" in header_area

    def test_muc_1_1_2_scope_residential(self, master_content: str):
        """Verify Mục 1.1.2 reflects 7 floors, 25m, 5000m3 and basement thresholds."""
        sec = _get_section_text(master_content, "muc-1-1-2")
        assert CITATION_SUBSTR in sec
        assert "cao từ 7 tầng trở lên (hoặc có chiều cao PCCC từ 25 m trở lên)" in sec
        assert "hoặc có khối tích từ 5 000 m3 trở lên" in sec
        assert "hoặc có nhiều hơn 1 tầng hầm đến 3 tầng hầm" in sec
        assert "Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm" in sec

    def test_muc_1_1_4_partial_renovation(self, master_content: str):
        """Verify Mục 1.1.4 applies strictly to directly renovated parts and references 1.1.10."""
        sec = _get_section_text(master_content, "muc-1-1-4")
        assert CITATION_SUBSTR in sec
        assert "chỉ áp dụng đối với các bộ phận, khu vực trực tiếp được cải tạo sửa chữa" in sec
        assert "áp dụng 1.1.10" in sec
        # Old items e, f, g must not exist
        assert "e) Cải tạo" not in sec
        assert "f) Cải tạo" not in sec
        assert "g) Cải tạo" not in sec

    def test_muc_1_1_5_exclusions(self, master_content: str):
        """Verify Mục 1.1.5 excludes road tunnels and lighthouses."""
        sec = _get_section_text(master_content, "muc-1-1-5")
        assert CITATION_SUBSTR in sec
        assert "công trình hầm giao thông; tháp đèn biển" in sec

    def test_muc_1_1_7_foreign_standards(self, master_content: str):
        """Verify Mục 1.1.7 verbatim adoption of foreign standards clause."""
        sec = _get_section_text(master_content, "muc-1-1-7")
        assert CITATION_SUBSTR in sec
        assert "Cho phép sử dụng các tài liệu chuẩn của nước ngoài" in sec

    def test_muc_1_1_10_engineering_argumentation(self, master_content: str):
        """Verify Mục 1.1.10 engineering argumentation and replacement criteria."""
        sec = _get_section_text(master_content, "muc-1-1-10")
        assert CITATION_SUBSTR in sec
        assert "bổ sung, thay thế một số yêu cầu của quy chuẩn này đối với công trình cụ thể bằng các yêu cầu an toàn cháy phù hợp khác" in sec

    def test_muc_1_1_11_local_regulations(self, master_content: str):
        """Verify Mục 1.1.11 local technical regulation delegation."""
        sec = _get_section_text(master_content, "muc-1-1-11")
        assert CITATION_SUBSTR in sec
        assert "Các địa phương được ban hành quy chuẩn kỹ thuật địa phương" in sec

    def test_muc_1_3_repealed(self, master_content: str):
        """Verify Mục 1.3 is explicitly marked as repealed."""
        sec = _get_section_text(master_content, "muc-1-3")
        assert REPEAL_SUBSTR in sec
        assert "bãi bỏ theo quy định tại Thông tư số 09/2023/TT-BXD" in sec

    def test_muc_1_4_21a_gian_phong_chung(self, master_content: str):
        """Verify Mục 1.4.21a Gian phòng chung definition is present."""
        sec = _get_section_text(master_content, "muc-1-4-21a")
        assert CITATION_SUBSTR in sec
        assert "Gian phòng chung" in sec
        assert "diện tích không quá 300 m2" in sec

    def test_bang_10_clean_table(self, master_content: str):
        """Verify Bảng 10 is un-nested from blockquote and has SD1 flow rates."""
        sec = _get_section_text(master_content, "bang-10")
        assert CITATION_SUBSTR in sec
        # Must not be inside > blockquote
        for line in sec.splitlines():
            if "|" in line:
                assert not line.startswith(">"), f"Table line should not be blockquoted: {line}"
        # Check specific table values
        assert "| I và II | S0, S1 | A, B, C | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |" in sec
        assert "| I và II | S0 | D, E | 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 |" in sec

    def test_muc_3_4_13_smoke_free_stairs(self, master_content: str):
        """Verify Mục 3.4.13 updates (removes paragraph 2 and point a, updates note to 2.4.3.3)."""
        sec = _get_section_text(master_content, "muc-3-4-1-3")
        assert CITATION_SUBSTR in sec
        assert "2.4.3.3" in sec
        assert "Trong các nhà có nhiều công năng, các buồng thang bộ nối giữa các phần nhà" not in sec
        assert "a) Trong các nhà nhóm F1, F2" not in sec

    def test_muc_4_3_2_2_auto_suppression_exemption(self, master_content: str):
        """Verify Mục 4.3.2.2 auto fire extinguishing exemption."""
        sec = _get_section_text(master_content, "muc-4-3-2-2")
        assert CITATION_SUBSTR in sec
        assert "Cho phép không áp dụng các quy định tại 4.3.2.1 nếu nhà được trang bị chữa cháy tự động" in sec

    def test_muc_4_3_3_3_wall_openings(self, master_content: str):
        """Verify Mục 4.3.3.3 wall opening reference to 4.3.3.1."""
        sec = _get_section_text(master_content, "muc-4-3-3-3")
        assert CITATION_SUBSTR in sec
        assert "như quy định tại đoạn c) điểm 4.3.3.1" in sec

    def test_muc_4_3_3_4_wall_openings_exemption(self, master_content: str):
        """Verify Mục 4.3.3.4 wall opening exemption for low rise / auto suppression."""
        sec = _get_section_text(master_content, "muc-4-3-3-4")
        assert CITATION_SUBSTR in sec
        assert "ba tầng trở xuống hoặc có chiều cao PCCC dưới 15 m" in sec

    def test_muc_6_12_stair_clearance(self, master_content: str):
        """Verify Mục 6.12 stair gap width is 75 mm with dry riser fallback."""
        sec = _get_section_text(master_content, "muc-6-1-2")
        assert CITATION_SUBSTR in sec
        assert "75 mm" in sec
        assert "tại mỗi tầng cần bố trí ít nhất một họng khô để cấp nước chữa cháy cho tầng đó" in sec

    def test_muc_7_4_repealed(self, master_content: str):
        """Verify Mục 7.4 is explicitly marked as repealed."""
        sec = _get_section_text(master_content, "muc-7-4")
        assert REPEAL_SUBSTR in sec
        assert "bãi bỏ theo quy định tại Thông tư số 09/2023/TT-BXD" in sec
