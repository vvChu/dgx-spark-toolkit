"""Verification Gate for QCVN 06:2022/BXD Master Consolidation.

Ensures that the master file `qcvn_06_2022_bxd.md` in the legal vault
has properly received the substantive technical updates from Amendment 1:2023 (TT 09/2023/TT-BXD)
before allowing Milvus re-indexing.
"""

import os
import re
from pathlib import Path
import pytest


VAULT_DIR = Path(os.environ.get("HUB3_LEGAL_PATH", "/home/vvc/ccba/ccba-legal-knowledge"))
MASTER_FILE = VAULT_DIR / "legal_docs" / "02_qcvn" / "qcvn_06_2022_bxd" / "qcvn_06_2022_bxd.md"


@pytest.fixture(scope="module")
def master_content() -> str:
    assert MASTER_FILE.exists(), f"QCVN 06 Master file missing at: {MASTER_FILE}"
    return MASTER_FILE.read_text(encoding="utf-8")


class TestQCVN06ConsolidationGate:
    """Rigorous gate checking all 4 Grok 4.7 invariants on living standard."""

    def test_muc_1_1_2_has_25m_and_5000m3(self, master_content: str):
        """Mục 1.1.2 must contain the updated thresholds from Sửa đổi 1:2023."""
        # Find Mục 1.1.2 block
        m = re.search(r'<a id="muc-1-1-2"></a>.*?(?=<a id="muc-1-1-3"|<a id="muc-1-1-4"|### 1\.1\.3|### 1\.1\.4)', master_content, flags=re.DOTALL)
        assert m is not None, "Mục 1.1.2 anchor not found in master"
        block = m.group(0)
        
        # Verify substantive thresholds
        assert "25 m" in block or "25m" in block, "Mục 1.1.2 must contain 25 m height threshold"
        assert "5 000 m3" in block or "5.000 m3" in block or "5000 m3" in block, "Mục 1.1.2 must contain 5 000 m3 volume threshold"
        assert "Thông tư 09/2023/TT-BXD" in block, "Mục 1.1.2 must cite amending Circular 09/2023"

    def test_muc_1_3_is_repealed(self, master_content: str):
        """Mục 1.3 (Tài liệu viện dẫn) must have an explicit repeal notice."""
        m = re.search(r'<a id="muc-1-3"></a>.*?(?=<a id="muc-1-4"|### 1\.4)', master_content, flags=re.DOTALL)
        assert m is not None, "Mục 1.3 anchor not found in master"
        block = m.group(0)
        assert "BÃI BỎ" in block or "bãi bỏ" in block.lower(), "Mục 1.3 must contain repeal notice"
        assert "09/2023/TT-BXD" in block, "Mục 1.3 repeal must cite Circular 09/2023"

    def test_muc_1_1_5_has_exclusions(self, master_content: str):
        """Mục 1.1.5 must include new exclusions: tháp đèn biển and hầm giao thông."""
        m = re.search(r'<a id="muc-1-1-5"></a>.*?(?=<a id="muc-1-1-6"|<a id="muc-1-1-7"|### 1\.1\.6|### 1\.1\.7)', master_content, flags=re.DOTALL)
        assert m is not None, "Mục 1.1.5 anchor not found in master"
        block = m.group(0)
        assert "tháp đèn biển" in block, "Mục 1.1.5 must include 'tháp đèn biển'"
        assert "hầm giao thông" in block, "Mục 1.1.5 must include 'hầm giao thông'"

    def test_new_anchors_present(self, master_content: str):
        """New clauses from Sửa đổi 1 must exist with anchors."""
        assert 'id="muc-1-1-11"' in master_content, "Anchor muc-1-1-11 (quy chuẩn địa phương) must exist"
        assert 'id="muc-1-4-21a"' in master_content, "Anchor muc-1-4-21a (gian phòng chung) must exist"

    def test_bang_10_has_new_flow_rates(self, master_content: str):
        """Bảng 10 must contain the full replacement water flow rate matrix."""
        m = re.search(r'<a id="bang-10"[^>]*></a>.*?(?=<a id="bang-11"|<a id="muc-5-1-3"|### 5\.1\.3)', master_content, flags=re.DOTALL)
        assert m is not None, "Bảng 10 anchor not found in master"
        block = m.group(0)
        assert "Lưu lượng nước cho chữa cháy ngoài nhà cho nhà nhóm F5" in block
        assert "thông tư số 09/2023/tt-bxd" in block.lower() or "09/2023" in block
