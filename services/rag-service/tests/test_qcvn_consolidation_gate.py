"""Deterministic Gate Tests for QCVN 06:2022/BXD Master Consolidation.

Ensures that:
1. All core technical clauses of QCVN 06:2022/BXD Master match the verbatim legal text
   of Amendment 1:2023 (Thông tư 09/2023/TT-BXD, effective 2023-12-01).
2. Citation lines (> *[Sửa đổi bởi Thông tư 09/2023/TT-BXD...]*) are present in every amended section.
3. Repealed sections (1.3, 7.4, A.4, A.1.3.12, H.2.10.3) are explicitly marked as repealed.
4. Un-nested Bảng 10 presents clean verbatim data table without blockquote interference.
5. All dot-swallowed numbers (4.32.2, 4.33.3, 6.12, 3.4.13) resolve deterministically.
6. Zero synthetic/hallucinated text (no 300 m2 in 1.4.21a, no 150m in 1.1.5, no old procedures in 1.1.10).

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding & Mandatory Acquisition Invariant
- Grok 4.7 xhigh Verdict: Living Standard Consolidation Gate
"""

import re
import sys
from pathlib import Path
import pytest

# Ensure repository root is in sys.path to import consolidation components
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.consolidate_qcvn_06 import (  # noqa: E402
    DOT_SWALLOW_MAP,
    ANNEXES_DIR,
    MASTER_FILE,
    AMENDMENT_FILE,
)

CITATION_SUBSTR = "Sửa đổi bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023)"
REPEAL_SUBSTR = "Bãi bỏ bởi Thông tư 09/2023/TT-BXD (Sửa đổi 1:2023)"


@pytest.fixture(scope="module")
def master_content() -> str:
    if not MASTER_FILE.exists():
        pytest.skip(f"Master file not found at {MASTER_FILE}")
    return MASTER_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def amendment_content() -> str:
    if not AMENDMENT_FILE.exists():
        pytest.skip(f"Amendment file not found at {AMENDMENT_FILE}")
    return AMENDMENT_FILE.read_text(encoding="utf-8")


def _get_section_text(content: str, anchor_id: str) -> str:
    """Extracts text of a given section anchor up to the next anchor."""
    pattern = rf'((?:#{{1,4}}\s*)?<a\s+id=[\"\x27]{re.escape(anchor_id)}[\"\x27][^>]*></a>.*?)(?=\n(?:#{{1,4}}\s*)?<a\s+id=|\n##\s+|\Z)'
    m = re.search(pattern, content, re.DOTALL)
    assert m is not None, f"Anchor '{anchor_id}' not found in content"
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
        """Verify Mục 1.1.2 reflects 7 floors, 25m, 5000m3 and basement thresholds, without OCR artifacts."""
        sec = _get_section_text(master_content, "muc-1-1-2")
        assert CITATION_SUBSTR in sec
        assert "cao từ 7 tầng trở lên (hoặc có chiều cao PCCC từ 25 m trở lên)" in sec
        assert "hoặc có khối tích từ 5 000 m3 trở lên" in sec
        assert "hoặc có nhiều hơn 1 tầng hầm đến 3 tầng hầm" in sec
        assert "Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm" in sec
        assert "_GHI CHÚ CHỈ SỐ PHỤ:_" not in sec

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

    def test_muc_1_1_5_exclusions_verbatim(self, master_content: str):
        """Verify Mục 1.1.5 verbatim exclusions with no third-party synthetic text."""
        sec = _get_section_text(master_content, "muc-1-1-5")
        assert CITATION_SUBSTR in sec
        assert "nhà máy thủy điện, nhiệt điện, điện nguyên tử" in sec
        assert "công trình hầm giao thông; tháp đèn biển" in sec
        assert "150 m" not in sec
        assert "dầu khí ngoài khơi" not in sec

    def test_muc_1_1_7_foreign_standards(self, master_content: str):
        """Verify Mục 1.1.7 verbatim adoption of foreign standards clause."""
        sec = _get_section_text(master_content, "muc-1-1-7")
        assert CITATION_SUBSTR in sec
        assert "Cho phép sử dụng các tài liệu chuẩn của nước ngoài" in sec

    def test_muc_1_1_10_clean_no_old_procedures(self, master_content: str):
        """Verify Mục 1.1.10 engineering argumentation and no old Ministry submission procedures."""
        sec = _get_section_text(master_content, "muc-1-1-10")
        assert CITATION_SUBSTR in sec
        assert "bổ sung, thay thế một số yêu cầu của quy chuẩn này đối với công trình cụ thể bằng các yêu cầu an toàn cháy phù hợp khác" in sec
        assert "gửi Bộ Xây dựng" not in sec
        assert "Cục Cảnh sát" not in sec

    def test_muc_1_1_11_local_regulations(self, master_content: str):
        """Verify Mục 1.1.11 local technical regulation delegation."""
        sec = _get_section_text(master_content, "muc-1-1-11")
        assert CITATION_SUBSTR in sec
        assert "Các địa phương được ban hành quy chuẩn kỹ thuật địa phương" in sec

    def test_muc_1_3_repealed(self, master_content: str):
        """Verify Mục 1.3 is explicitly marked as repealed."""
        sec = _get_section_text(master_content, "muc-1-3")
        assert REPEAL_SUBSTR in sec
        assert "bãi bỏ theo quy định tại" in sec

    def test_muc_1_4_21a_gian_phong_chung_verbatim(self, master_content: str):
        """Verify Mục 1.4.21a Gian phòng chung verbatim SĐ1 definition without synthetic 300 m2."""
        sec = _get_section_text(master_content, "muc-1-4-21a")
        assert CITATION_SUBSTR in sec
        assert "Gian phòng chung" in sec
        assert "tổ chức sự kiện" in sec
        assert "300 m2" not in sec

    def test_muc_1_5_5_and_1_5_6_inserted(self, master_content: str):
        """Verify Mục 1.5.5 (± 5% tolerance) and Mục 1.5.6 (actual function)."""
        sec_155 = _get_section_text(master_content, "muc-1-5-5")
        assert CITATION_SUBSTR in sec_155
        assert "sai số thi công là ± 5 %" in sec_155

        sec_156 = _get_section_text(master_content, "muc-1-5-6")
        assert CITATION_SUBSTR in sec_156
        assert "công năng sử dụng thực tế" in sec_156

    def test_muc_3_2_3_roller_shutters_and_sliding_doors(self, master_content: str):
        """Verify Mục 3.2.3 rules on roller shutters and sliding/folding doors."""
        sec = _get_section_text(master_content, "muc-3-2-3")
        assert CITATION_SUBSTR in sec
        assert "cửa cuốn hoặc cửa quay" in sec
        assert "cửa trượt hoặc cửa xếp" in sec

    def test_muc_3_3_1_and_4_3_1_tai_lieu_chuan(self, master_content: str):
        """Verify TCVN 3890 replaced by tài liệu chuẩn at Mục 3.3.1 and Mục 4.3.1."""
        sec_331 = _get_section_text(master_content, "muc-3-3-1")
        assert "tài liệu chuẩn" in sec_331
        assert "TCVN 3890" not in sec_331

        sec_431 = _get_section_text(master_content, "muc-4-3-1")
        assert "tài liệu chuẩn" in sec_431
        assert "TCVN 3890" not in sec_431

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

    def test_muc_5_1_1_1_infrastructure_water_supply(self, master_content: str):
        """Verify Mục 5.1.1.1 external water supply for infrastructure."""
        sec = _get_section_text(master_content, "muc-5-1-1-1")
        assert CITATION_SUBSTR in sec
        assert "đầu tư xây dựng hạ tầng kỹ thuật" in sec
        assert "TCVN 3890:2023" in sec

    def test_muc_5_1_1_4_water_column_meters_and_ground_elevation(self, master_content: str):
        """Verify Mục 5.1.1.4 pressure units in m cột nước and ground elevation measurement."""
        sec = _get_section_text(master_content, "muc-5-1-1-4")
        assert CITATION_SUBSTR in sec
        assert "10 m cột nước" in sec
        assert "60 m cột nước" in sec
        assert "đo ở vị trí cao độ bằng với mặt đất" in sec

    def test_bang_10_clean_table(self, master_content: str):
        """Verify Bảng 10 is un-nested from blockquote, has exact SĐ1 title and flow rates."""
        sec = _get_section_text(master_content, "bang-10")
        assert CITATION_SUBSTR in sec
        # Title must not be reversed
        assert "Bảng 10 - Lưu lượng nước cho chữa cháy ngoài nhà cho nhà nhóm F5 không có lỗ mở trên mái" in sec
        assert "đối với nhà sản xuất và nhà kho có lỗ mở trên mái" not in sec
        # Must not be inside > blockquote
        for line in sec.splitlines():
            if "|" in line:
                assert not line.startswith(">"), f"Table line should not be blockquoted: {line}"
        # Check specific table values
        assert "| I và II | S0, S1 | A, B, C | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |" in sec
        assert "| I và II | S0 | D, E | 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 |" in sec

    def test_loi_noi_dau_clean_no_synthetic_wording(self, master_content: str):
        """Verify Lời nói đầu has zero synthetic living standard phrasing."""
        header_area = master_content[:6000]
        assert "ấn bản hợp nhất thực chất" not in header_area
        assert "Living Standard" not in header_area
        assert "ngày 10 tháng 10 năm 2023" in header_area

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
        assert "bãi bỏ theo quy định tại" in sec

    def test_16_core_technical_anchors_grok_audit(self, master_content: str):
        """Verify all 16 technical anchors highlighted in Grok audit are updated verbatim."""
        # 1.4.9 CHÚ THÍCH 4
        sec_149 = _get_section_text(master_content, "muc-1-4-9")
        assert "CHÚ THÍCH 4: Trong trường hợp các mặt đường tiếp cận nhà có cao độ khác nhau" in sec_149

        # 3.2.8
        sec_328 = _get_section_text(master_content, "muc-3-2-8")
        assert "lớn hơn hoặc bằng 7 m" in sec_328
        assert "hai cạnh xa nhất của chúng" in sec_328
        assert "hoặc hành lang bên" in sec_328

        # 3.3.2
        sec_332 = _get_section_text(master_content, "muc-3-3-2")
        assert "dọc theo tâm đường thoát nạn" in sec_332
        assert "đến tâm của lối ra thoát nạn gần nhất của mỗi tầng" in sec_332

        # 3.3.5
        sec_335 = _get_section_text(master_content, "muc-3-3-5")
        assert "màn ngăn khói, có mép dưới cách sàn hành lang tối đa 2,5 m" in sec_335

        # 3.4.4
        sec_344 = _get_section_text(master_content, "muc-3-4-4")
        assert "3 bậc thang chéo (rẻ quạt)" in sec_344
        assert "Được sử dụng thang cong toàn phần hoặc một phần" in sec_344

        # 3.4.8
        sec_348 = _get_section_text(master_content, "muc-3-4-8")
        assert "lỗ thoát khói trên tum thang" in sec_348

        # 4.5
        sec_45 = _get_section_text(master_content, "muc-4-5")
        assert "El 45 đối với nhà có bậc chịu lửa I đến III" in sec_45 or "EI 45 đối với nhà có bậc chịu lửa I đến III" in sec_45

        # 2.5.3.3
        sec_2533 = _get_section_text(master_content, "muc-2-5-3-3")
        assert "cột 6 của Bảng 4" in sec_2533

        # 5.1.1.3
        sec_5113 = _get_section_text(master_content, "muc-5-1-1-3")
        assert "được trang bị phương tiện" not in sec_5113

        # 5.1.4.7
        sec_5147 = _get_section_text(master_content, "muc-5-1-4-7")
        assert "không được lớn hơn 400 m" in sec_5147

        # 5.1.5.4
        sec_5154 = _get_section_text(master_content, "muc-5-1-5-4")
        assert "bãi lấy nước" in sec_5154
        assert "12 m x 12 m" not in sec_5154

        # 5.1.5.10
        sec_51510 = _get_section_text(master_content, "muc-5-1-5-10")
        assert "không nhỏ hơn 3 m3" in sec_51510
        assert "từ 3 m3 đến 5 m3" not in sec_51510

        # 6.2.2.3
        sec_6223 = _get_section_text(master_content, "muc-6-2-2-3")
        assert "tiếp cận đến ít nhất 50 % chu vi" in sec_6223
        assert "2 m đến 10 m" in sec_6223

        # 6.13
        sec_613 = _get_section_text(master_content, "muc-6-13")
        assert "bán kính phục vụ) không vượt quá 60 m" in sec_613

        # 6.14
        sec_614 = _get_section_text(master_content, "muc-6-14")
        assert "nếu được thiết kế để lực lượng chữa cháy tiếp cận qua mái thì" in sec_614

        # 6.1.7.1
        sec_6171 = _get_section_text(master_content, "muc-6-1-7-1")
        assert "theo A.4" not in sec_6171

        # 6.17.2
        sec_6172 = _get_section_text(master_content, "muc-6-17-2")
        assert "ít nhất một lối ra trực tiếp thông với hành lang chính" in sec_6172

    def test_dot_swallow_map_completeness(self, master_content: str):
        """Verify all keys in DOT_SWALLOW_MAP resolve deterministically to valid anchors."""
        for num, aid in DOT_SWALLOW_MAP.items():
            if aid.startswith("muc-A-") or aid.startswith("muc-H-"):
                continue  # Checked in annex tests
            assert f'id="{aid}"' in master_content or f"id='{aid}'" in master_content, (
                f"Anchor '{aid}' mapped from '{num}' not found in master content"
            )

    def test_annex_swallow_map_and_dual_anchors(self):
        """Verify Annex A and H dot-swallowed numbers resolve to canonical headings and anchors."""
        annex_a_file = ANNEXES_DIR / "phu_luc_a_quy_dinh_bo_sung_nhom_nha_cu_the.md"
        assert annex_a_file.exists()
        text_a = annex_a_file.read_text(encoding="utf-8")

        # Canonical anchors and headings
        assert 'id="muc-A-1-3-10"' in text_a and "### A.1.3.10" in text_a
        assert 'id="muc-A-2-11"' in text_a and "### A.2.11" in text_a
        assert 'id="muc-A-2-12"' in text_a and "### A.2.12" in text_a
        assert 'id="muc-A-2-14"' in text_a and "### A.2.14" in text_a
        assert 'id="muc-A-3-1-13"' in text_a and "### A.3.1.13" in text_a
        assert 'id="muc-A-3-1-16"' in text_a and "### A.3.1.16" in text_a
        assert "Đoạn e đã được bãi bỏ" in text_a
        assert 'id="muc-A-2-25-5"' in text_a and "### A.2.25.5" in text_a
        assert "người thoát nạn an toàn ra ngoài nhà trước khi bị các yếu tố nguy hiểm cháy tác động" in text_a
        assert "Khu vực lánh nạn trên mái" in text_a

        annex_h_file = ANNEXES_DIR / "phu_luc_h_bac_chiu_lua_va_khoang_chay.md"
        assert annex_h_file.exists()
        text_h = annex_h_file.read_text(encoding="utf-8")

        assert 'id="muc-H-2-11-1"' in text_h and "### H.2.11.1" in text_h
        assert 'id="muc-H-2-12-10"' in text_h and "### H.2.12.10" in text_h
        assert 'id="muc-H-2-4-4"' in text_h and "### H.2.4.4" in text_h
        assert "hai thang thoát nạn bảo đảm yêu cầu" in text_h
        assert "1 400 5)" in text_h
        assert "1 400 2)" in text_h
        assert "Không quy định" in text_h
        assert 'id="muc-H-7"' in text_h

    def test_annex_repeals(self):
        """Verify Phụ lục A (A.4, A.1.3.12) and Phụ lục H (H.2.10.3) repeals."""
        annex_a_file = ANNEXES_DIR / "phu_luc_a_quy_dinh_bo_sung_nhom_nha_cu_the.md"
        assert annex_a_file.exists()
        text_a = annex_a_file.read_text(encoding="utf-8")
        sec_a4 = _get_section_text(text_a, "muc-A-4")
        assert REPEAL_SUBSTR in sec_a4
        assert "Nhà kinh doanh dịch vụ karaoke, vũ trường" in sec_a4

        sec_a1312 = _get_section_text(text_a, "muc-A-1-3-1-2")
        assert REPEAL_SUBSTR in sec_a1312

        annex_h_file = ANNEXES_DIR / "phu_luc_h_bac_chiu_lua_va_khoang_chay.md"
        assert annex_h_file.exists()
        text_h = annex_h_file.read_text(encoding="utf-8")
        sec_h2103 = _get_section_text(text_h, "muc-H-2-10-3")
        assert REPEAL_SUBSTR in sec_h2103

    def test_annexes_c_d_e_g_consolidation(self):
        """Verify amendments in Annexes C, D, E, G."""
        # Annex C
        annex_c_file = ANNEXES_DIR / "phu_luc_c_hang_nguy_hiem_chay_va_chay_no.md"
        text_c = annex_c_file.read_text(encoding="utf-8")
        assert "Phương pháp xác định các dấu hiệu để xếp hạng" in text_c
        assert "bụi cháy được và có khả năng tạo thành các hỗn hợp nguy hiểm nổ" in text_c

        # Annex D
        annex_d_file = ANNEXES_DIR / "phu_luc_d_bao_ve_chong_khoi.md"
        text_d = annex_d_file.read_text(encoding="utf-8")
        assert "Mục đích bảo vệ chống khói" in text_d
        assert "không thấp hơn 2 m (hoặc lấy theo giá trị quy định trong tài liệu chuẩn áp dụng)" in text_d
        assert "Khu vực phải thực hiện thoát khói khi có cháy" in text_d
        assert "Cơ chế hút xả khói và thoát khói tự nhiên" in text_d
        assert "CHÚ THÍCH 3: Không yêu cầu chỉ tiêu I" in text_d
        assert "CHÚ THÍCH 4:" in text_d
        assert "Cấp không khí bù" in text_d

        # Annex E
        annex_e_file = ANNEXES_DIR / "phu_luc_e_khoang_cach_pccc.md"
        text_e = annex_e_file.read_text(encoding="utf-8")
        assert "CHÚ THÍCH 6: Không quy định khoảng cách giữa các nhà và công trình công cộng" in text_e
        assert "Khoảng cách phòng cháy chống cháy xác định theo đường ranh giới" in text_e
        assert "nhân đôi diện tích lỗ mở không được bảo vệ chống cháy" in text_e

        # Annex G
        annex_g_file = ANNEXES_DIR / "phu_luc_g_khoang_cach_va_chieu_rong_thoat_nan.md"
        text_g = annex_g_file.read_text(encoding="utf-8")
        assert "đã được bãi bỏ theo Thông tư 09/2023/TT-BXD" in text_g
        assert "Bảng G.9, hoặc xác định theo tài liệu chuẩn khác (ví dụ [5])" in text_g

    def test_gate_reads_amendment_file_directly(self, amendment_content: str):
        """Verify the test gate directly reads AMENDMENT_FILE and confirms its legal provenance."""
        assert len(amendment_content) > 50000, "Amendment file content is suspiciously small"
        assert "SỬA ĐỔI 1:2023 QCVN 06:2022/BXD" in amendment_content
        assert "Thông tư số 09/2023/TT-BXD" in amendment_content
        assert "10 tháng 10 năm 2023" in amendment_content

    def test_cross_check_amendment_verbatim_clauses_in_vault(
        self, amendment_content: str, master_content: str
    ):
        """Cross-check verbatim clauses directly extracted from AMENDMENT_FILE against vault files."""
        # 1. Scope 1.1.2 residential threshold from amendment
        target_112_phrase = (
            "Chung cư và nhà ở tập thể có chiều cao PCCC không quá 150 m và không quá 3 tầng hầm"
        )
        assert target_112_phrase in amendment_content
        assert target_112_phrase in master_content

        # 2. Scope 1.1.11 local regulation delegation from amendment
        target_1111_phrase = (
            "Các địa phương được ban hành quy chuẩn kỹ thuật địa phương để thay thế, sửa đổi hoặc bổ sung"
        )
        assert target_1111_phrase in amendment_content
        assert target_1111_phrase in master_content

        # 3. Clause 1.4.9 NOTE 4 roadway levels
        target_149_phrase = (
            "Trong trường hợp các mặt đường tiếp cận nhà có cao độ khác nhau thì nhà có thể có"
        )
        assert target_149_phrase in amendment_content
        assert target_149_phrase in master_content

        # 4. Clause 3.2.8 corridor exit distance
        target_328_phrase = (
            "Khoảng cách giữa hai lối ra thoát nạn được đo theo đường thẳng nối giữa hai cạnh xa nhất của chúng và phải lớn hơn hoặc bằng 7 m"
        )
        assert target_328_phrase in amendment_content
        assert target_328_phrase in master_content

        # 5. Clause 3.3.2 centerline of exit pathway
        target_332_phrase = "đo dọc theo tâm đường thoát nạn"
        assert target_332_phrase in amendment_content
        assert target_332_phrase in master_content

        # 6. Clause 3.3.5 smoke curtain depth
        target_335_phrase = "có mép dưới cách sàn hành lang tối đa 2,5 m"
        assert target_335_phrase in amendment_content
        assert target_335_phrase in master_content

        # 7. Clause 3.4.4 winder stairs
        target_344_phrase = "cho phép bố trí tối đa 3 bậc thang chéo (rẻ quạt)"
        assert target_344_phrase in amendment_content
        assert target_344_phrase in master_content

        # 8. Clause 3.4.8 stairwell roof hatch smoke vent
        target_348_phrase = (
            "phải bố trí các lỗ thoát khói trên tum thang với tổng diện tích tối thiểu bằng 10 % diện tích phủ bì"
        )
        assert target_348_phrase in amendment_content
        assert target_348_phrase in master_content

        # 9. Clause 4.5 fire ratings
        target_45_phrase = "El 45"
        assert target_45_phrase in amendment_content
        assert target_45_phrase in master_content

        # 10. Table 10 heading and F5 criteria
        target_table10_phrase = (
            "Lưu lượng nước cho chữa cháy ngoài nhà cho nhà nhóm F5 không có lỗ mở trên mái"
        )
        assert target_table10_phrase in amendment_content
        assert target_table10_phrase in master_content

        # 11. Annex A (A.2.4)
        annex_a_file = ANNEXES_DIR / "phu_luc_a_quy_dinh_bo_sung_nhom_nha_cu_the.md"
        text_a = annex_a_file.read_text(encoding="utf-8")
        target_a24_phrase = (
            "Cho phép bố trí các gian phòng tập trung đông người ở chiều cao PCCC cao hơn quy định trên"
        )
        assert target_a24_phrase in amendment_content
        assert target_a24_phrase in text_a

        # 12. Annex D (D.1.1)
        annex_d_file = ANNEXES_DIR / "phu_luc_d_bao_ve_chong_khoi.md"
        text_d = annex_d_file.read_text(encoding="utf-8")
        target_d11_phrase = (
            "thiết kế bảo vệ chống khói của nhà cần bảo đảm mục tiêu tối thiểu là an toàn cho người thoát nạn ra ngoài"
        )
        assert target_d11_phrase in amendment_content
        assert target_d11_phrase in text_d

        # 13. Annex H (H.2.4.4)
        annex_h_file = ANNEXES_DIR / "phu_luc_h_bac_chiu_lua_va_khoang_chay.md"
        text_h = annex_h_file.read_text(encoding="utf-8")
        target_h244_phrase = "hai thang thoát nạn bảo đảm yêu cầu"
        assert target_h244_phrase in amendment_content
        assert target_h244_phrase in text_h

    def test_dot_swallow_map_amendment_cross_validation(
        self, amendment_content: str, master_content: str
    ):
        """Cross-validate DOT_SWALLOW_MAP against amendment citations and vault anchors."""
        for clause_num, anchor_id in DOT_SWALLOW_MAP.items():
            assert clause_num in amendment_content, (
                f"Clause {clause_num} in DOT_SWALLOW_MAP not found in amendment file"
            )
            # Anchor must exist in master or one of the annexes
            found_in_master = f'id="{anchor_id}"' in master_content
            found_in_annexes = any(
                f'id="{anchor_id}"' in f.read_text(encoding="utf-8")
                for f in ANNEXES_DIR.glob("*.md")
            )
            assert found_in_master or found_in_annexes, (
                f"Anchor {anchor_id} for clause {clause_num} not found in master or any annex"
            )
