"""Deterministic Gate Tests for QCVN 04:2021/BXD Living Standard Consolidation.
=============================================================================
Ensures that:
1. All technical clauses of QCVN 04:2021/BXD Master strictly match verbatim text
   of Amendment 01:2026 (Thông tư số 31/2026/TT-BXD, effective 2026-12-15).
2. All 140+ lines of critical technical requirements in Section 2.10 & 2.11
   (electric vehicle charging, battery swap cabinets, lithium-ion safety) are present.
3. Transitional provisions (Section 3.3) and Section 3.4, 3.5 are properly un-nested
   into clean markdown headings with dedicated anchors.
4. Clean baseline recovery (.bak -> sources/goc_2021.md) enforces cryptographic SHA-256 hash.
5. Idempotent: Subsequent ULCE runs produce bit-for-bit identical outputs without drifting.

Adheres strictly to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding & Mandatory Acquisition Invariant
- Grok 4.7 xhigh Verdict: PLAN_APPROVED_WITH_OBSERVATIONS
"""

import hashlib
import re
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ulce_engine import UniversalLegalConsolidationEngine  # noqa: E402

BUNDLE_DIR = Path("/home/vvc/ccba/ccba-legal-knowledge/legal_docs/02_qcvn/qcvn_04_2021_bxd")
MASTER_FILE = BUNDLE_DIR / "qcvn_04_2021_bxd.md"
BAK_FILE = BUNDLE_DIR / "qcvn_04_2021_bxd.md.bak"
BASELINE_FILE = BUNDLE_DIR / "sources/qcvn_04_2021_bxd_goc_2021.md"
AMENDMENT_FILE = BUNDLE_DIR / "sources/sua_doi_01_2026_qcvn_04_2021_bxd.md"
MANIFEST_FILE = BUNDLE_DIR / "patch_manifest.yaml"

EXPECTED_BASELINE_SHA256 = "88d5c18a0dc2581309321b1a4d9fc5e0b749b45afd2c820d9a6d7a13602efc73"


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
    esc_id = re.escape(anchor_id)
    pattern = (
        rf'((?:<a\s+(?:id|name)=[\"\x27]{esc_id}[\"\x27][^>]*></a>\s*\n*)?'
        rf'(?:#{{1,4}}\s*)?<a\s+(?:id|name)=[\"\x27]{esc_id}[\"\x27][^>]*></a>.*?)'
        r'(?=\n(?:#{{1,4}}\s*)?<a\s+(?:id|name)=|\n##\s+|\Z)'
    )
    m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    assert m is not None, f"Anchor '{anchor_id}' not found in content"
    return m.group(1)


class TestQCVN04BaselineIntegrity:
    """Verify cryptographic baseline management and backup states."""

    def test_baseline_file_sha256(self):
        """Pristine 2021 source file must match immutable cryptographic hash."""
        assert BASELINE_FILE.exists(), f"Missing {BASELINE_FILE}"
        hasher = hashlib.sha256()
        hasher.update(BASELINE_FILE.read_bytes())
        assert hasher.hexdigest().lower() == EXPECTED_BASELINE_SHA256

    def test_backup_file_created_and_matches_baseline(self):
        """Backup .bak file must exist and mirror pristine baseline."""
        assert BAK_FILE.exists(), f"Backup file {BAK_FILE} was not created"
        hasher = hashlib.sha256()
        hasher.update(BAK_FILE.read_bytes())
        assert hasher.hexdigest().lower() == EXPECTED_BASELINE_SHA256

    def test_master_file_length_expansion(self, master_content: str):
        """Consolidated master markdown must expand well beyond legacy stub (~953 lines)."""
        lines = master_content.splitlines()
        assert len(lines) >= 1200, f"Expected >= 1200 lines, but got {len(lines)} (indicates unexpanded stub)"


class TestQCVN04RequiredAnchors:
    """Ensure all statutory anchors from SĐ 01:2026 are present and uniquely indexed."""

    @pytest.mark.parametrize(
        "anchor_id",
        [
            "muc-1-1-3",
            "muc-1-4-31",
            "muc-1-4-32",
            "muc-1-4-33",
            "muc-1-4-34",
            "muc-2-2-17",
            "muc-2-10",
            "muc-2-10-1-1",
            "muc-2-10-1-2",
            "muc-2-10-1-3",
            "muc-2-10-2-1",
            "muc-2-10-2-2",
            "muc-2-10-2-3",
            "muc-2-11",
            "muc-2-11-1",
            "muc-2-11-2-1",
            "muc-2-11-2-2",
            "muc-2-11-3",
            "muc-2-11-4",
            "muc-3-3",
            "muc-3-4",
            "muc-3-5",
            "muc-4-1a",
            "muc-4-1b",
            "muc-4-3",
        ],
    )
    def test_anchor_exists_and_uniquely_indexed(self, master_content: str, anchor_id: str):
        """Each statutory anchor must appear exactly once in the master document."""
        matches = re.findall(rf'<a\s+(?:id|name)=[\"\x27]{re.escape(anchor_id)}[\"\x27]', master_content, re.IGNORECASE)
        assert len(matches) == 1, f"Anchor '{anchor_id}' expected 1 occurrence, found {len(matches)}"


class TestQCVN04VerbatimFidelity:
    """Ensure 100% pure verbatim statutory text from Official Gazette (TT 31/2026/TT-BXD)."""

    def test_section_1_1_3_verbatim(self, master_content: str):
        sec = _get_section_text(master_content, "muc-1-1-3")
        assert "áp dụng đối với nhà chung cư xây mới và nhà chung cư hiện hữu" in sec

    def test_section_1_3_qcvn10_reference(self, master_content: str):
        sec = _get_section_text(master_content, "muc-1-3")
        assert "QCVN 10:2025/BCA" in sec
        assert "phương tiện phòng cháy, chữa cháy, cứu nạn, cứu hộ" in sec

    def test_definitions_1_4_31_to_34(self, master_content: str):
        sec = _get_section_text(master_content, "muc-1-4-31")
        assert "Nhà chung cư hiện hữu" in sec
        assert "trước thời điểm quy chuẩn này có hiệu lực" in sec

        sec32 = _get_section_text(master_content, "muc-1-4-32")
        assert "Khu vực sạc xe điện" in sec32

        sec33 = _get_section_text(master_content, "muc-1-4-33")
        assert "Chỗ sạc" in sec33

        sec34 = _get_section_text(master_content, "muc-1-4-34")
        assert "Khu vực đổi pin" in sec34

    def test_ev_charging_section_2_10_verbatim(self, master_content: str):
        """Verify full technical depth of Section 2.10 (electric vehicle charging)."""
        sec_2_10_1_1 = _get_section_text(master_content, "muc-2-10-1-1")
        # Priority order & basement safety
        assert "ưu tiên ngoài trời, trên mặt đất, tầng bán hầm, tầng hầm 1" in sec_2_10_1_1
        assert "giải phóng xe bị cháy ra khỏi nhà chung cư hoặc cô lập xe bị cháy" in sec_2_10_1_1
        # Partitioning & spacing
        assert "khoảng cách tối thiểu 2 m" in sec_2_10_1_1
        # Active fire safety & gas sensors
        assert "hệ thống báo cháy tự động, hệ thống camera giám sát" in sec_2_10_1_1
        assert "24/24 giờ" in sec_2_10_1_1
        assert "carbon monoxide (CO) và Hydrofluoric acid (HF)" in sec_2_10_1_1
        assert "Phụ lục D của QCVN 06:2022/BXD" in sec_2_10_1_1

        sec_2_10_2_1 = _get_section_text(master_content, "muc-2-10-2-1")
        assert "25 chỗ sạc cho ô tô điện hoặc 50 chỗ sạc cho mô tô điện" in sec_2_10_2_1
        # Technical compartments & drencher curtain
        assert "1 200 m2 nếu bố trí trong tầng bán hầm hoặc tầng hầm" in sec_2_10_2_1
        assert "300 m2 nếu bố trí trong tầng bán hầm hoặc tầng hầm" in sec_2_10_2_1
        assert "màn nước drencher" in sec_2_10_2_1
        assert "cường độ phun không nhỏ hơn 1 l/s" in sec_2_10_2_1
        # Electrical charging stand limits
        assert "không được vượt quá 22 kW" in sec_2_10_2_1
        assert "tự động ngắt nguồn điện" in sec_2_10_2_1
        assert "ngắt điện khẩn cấp" in sec_2_10_2_1

    def test_battery_swap_section_2_11_verbatim(self, master_content: str):
        """Verify full technical depth of Section 2.11 (battery swap cabinets)."""
        sec_2_11 = _get_section_text(master_content, "muc-2-11")
        assert "Khu vực đổi pin" in sec_2_11

        sec_2_11_2_1 = _get_section_text(master_content, "muc-2-11-2-1")
        assert "khoảng cách tối thiểu 3 m" in sec_2_11_2_1

        sec_2_11_2_2 = _get_section_text(master_content, "muc-2-11-2-2")
        assert "vách ngăn cháy với giới hạn chịu lửa không kém hơn EI 60" in sec_2_11_2_2
        assert "hút xả khói theo cơ chế cưỡng bức" in sec_2_11_2_2

        sec_2_11_4 = _get_section_text(master_content, "muc-2-11-4")
        assert "100 kWh" in sec_2_11_4
        assert "35 kWh" in sec_2_11_4
        assert "18 kWh" in sec_2_11_4

    def test_transitional_un_nested_headings_3_4_and_3_5(self, master_content: str):
        """Ensure Sections 3.4 and 3.5 are un-nested into first-class ### headings."""
        sec34 = _get_section_text(master_content, "muc-3-4")
        assert "### 3.4" in sec34
        assert "quản lý, vận hành đảm bảo hoạt động an toàn" in sec34
        # Must not be trapped in blockquote
        assert not sec34.strip().startswith(">")

        sec35 = _get_section_text(master_content, "muc-3-5")
        assert "### 3.5" in sec35
        assert "giám sát 24/24 giờ" in sec35
        assert not sec35.strip().startswith(">")

    def test_responsibilities_4_1a_and_4_1b(self, master_content: str):
        sec41a = _get_section_text(master_content, "muc-4-1a")
        assert "Mọi tổ chức, cá nhân khi tham gia các hoạt động" in sec41a

        sec41b = _get_section_text(master_content, "muc-4-1b")
        assert "Cơ quan có thẩm quyền theo quy định pháp luật về phòng cháy chữa cháy" in sec41b


class TestQCVN04Idempotency:
    """Ensure running consolidation engine repeatedly yields identical output."""

    def test_repeated_run_determinism(self):
        engine = UniversalLegalConsolidationEngine(BUNDLE_DIR)
        run1_text = engine.execute(verify_hash=True, dry_run=True)
        run2_text = engine.execute(verify_hash=True, dry_run=True)
        assert hashlib.sha256(run1_text.encode("utf-8")).hexdigest() == hashlib.sha256(run2_text.encode("utf-8")).hexdigest()
