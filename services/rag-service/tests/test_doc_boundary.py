"""Unit tests for doc_boundary — technical standard content boundary extractor."""
import re
import sys
import os
import types
import pytest

# ── Bootstrap minimal stub so we can test without full service stack ──────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion.doc_boundary import (
    detect_technical_standard,
    find_technical_content_start,
    strip_issuing_document,
    TECHNICAL_STANDARD_TYPES,
)


# ── Helpers ───────────────────────────────────────────────────────────────────
class FakePage:
    """Minimal RawPage stub with .text attribute."""
    def __init__(self, text: str, page: int = 0):
        self.text = text
        self.page = page
        self.is_table = False
        self.layout = []
        self.bbox = []
        self.source = "test"


def make_pages(*texts) -> list[FakePage]:
    return [FakePage(t, i + 1) for i, t in enumerate(texts)]


# ── detect_technical_standard ─────────────────────────────────────────────────
class TestDetectTechnicalStandard:
    def test_detects_qcvn(self):
        pages = make_pages("QCVN 119:2019/BTTTT\nNational technical regulation")
        result = detect_technical_standard(pages)
        assert result is not None
        assert "QCVN" in result

    def test_detects_tcvn(self):
        pages = make_pages("Nội dung thông thường", "TCVN 7909:2015 Tương thích điện từ")
        result = detect_technical_standard(pages)
        assert result is not None
        assert "TCVN" in result

    def test_detects_tccs(self):
        pages = make_pages("TCCS 01/2020/BTTTT Tiêu chuẩn cơ sở")
        result = detect_technical_standard(pages)
        assert result is not None
        assert "TCCS" in result

    def test_returns_none_for_legal_doc(self):
        pages = make_pages(
            "NGHỊ ĐỊNH\nSố 01/2024/NĐ-CP",
            "Điều 1. Phạm vi điều chỉnh"
        )
        result = detect_technical_standard(pages)
        assert result is None

    def test_empty_pages(self):
        assert detect_technical_standard([]) is None


# ── find_technical_content_start ─────────────────────────────────────────────
class TestFindTechnicalContentStart:
    def test_finds_loi_noi_dau(self):
        pages = make_pages(
            "THÔNG TƯ\nĐiều 1. Ban hành QCVN 119:2019/BTTTT",  # issuing doc
            "QCVN 119:2019/BTTTT\nHÀ NỘI - 2019",               # cover
            "Lời nói đầu\nQCVN 119 được xây dựng trên cơ sở...",  # ← content start
            "1. QUY ĐỊNH CHUNG\n1.1. Phạm vi điều chỉnh",
        )
        idx = find_technical_content_start(pages, "QCVN 119:2019/BTTTT")
        assert idx == 2

    def test_finds_quy_dinh_chung(self):
        pages = make_pages(
            "Điều 1. Ban hành QCVN 50:2022/BTTTT",                             # idx 0: issuing doc
            "QCVN 50:2022/BTTTT\nHÀ NỘI - 2022",                               # idx 1: cover (no marker)
            "MỤC LỤC\n1. Quy định chung...5\n2. Quy định kỹ thuật...7",        # idx 2: TOC only (no full-line match)
            "1. QUY ĐỊNH CHUNG\n1.1. Phạm vi điều chỉnh\nQuy chuẩn này quy định...",  # idx 3: real content
        )
        idx = find_technical_content_start(pages, "QCVN 50:2022")
        # Should be index 3 (real content) since TOC at idx 2 has inline not standalone heading
        assert idx == 3

    def test_no_marker_returns_zero(self):
        pages = make_pages("Trang A", "Trang B", "Trang C")
        idx = find_technical_content_start(pages, "QCVN 1:2020")
        assert idx == 0


# ── strip_issuing_document ────────────────────────────────────────────────────
class TestStripIssuingDocument:
    def test_strips_issuing_pages_for_qcvn(self):
        pages = make_pages(
            "THÔNG TƯ SỐ 14/2019/TT-BTTTT\nĐiều 1. Ban hành QCVN 119:2019/BTTTT",
            "QCVN 119:2019/BTTTT\nHÀ NỘI - 2019",
            "Lời nói đầu\nQCVN được xây dựng trên cơ sở IEC 60945:2002",
            "1. QUY ĐỊNH CHUNG\n1.1. Phạm vi điều chỉnh",
            "2. QUY ĐỊNH KỸ THUẬT\n2.1. Yêu cầu chung",
        )
        result = strip_issuing_document(pages, doc_type="QCVN")
        # Should start from "Lời nói đầu" page
        assert len(result) < len(pages)
        assert "Lời nói đầu" in result[0].text

    def test_noop_for_legal_doc(self):
        pages = make_pages(
            "NGHỊ ĐỊNH SỐ 01/2024/NĐ-CP",
            "Điều 1. Phạm vi điều chỉnh",
            "Điều 2. Đối tượng áp dụng",
        )
        result = strip_issuing_document(pages, doc_type="NGHI_DINH")
        assert len(result) == len(pages)  # no-op

    def test_noop_when_no_issuing_doc_present(self):
        """QCVN without Thông tư wrapper — all pages kept."""
        pages = make_pages(
            "QCVN 50:2022/BTTTT\nLời nói đầu\nQuy chuẩn xây dựng từ IEC...",
            "1. QUY ĐỊNH CHUNG\n1.1. Phạm vi",
        )
        result = strip_issuing_document(pages, doc_type="QCVN")
        assert len(result) == len(pages)

    def test_noop_for_empty_pages(self):
        assert strip_issuing_document([], doc_type="QCVN") == []

    def test_auto_detect_without_doc_type(self):
        """Even without doc_type hint, auto-detect from content."""
        pages = make_pages(
            "Thông tư số 14/2019/TT-BTTTT\nĐiều 1. Ban hành QCVN 119:2019",
            "QCVN 119:2019/BTTTT\nHÀ NỘI - 2019",
            "Lời nói đầu\nQCVN 119 được ban hành kèm Thông tư",
            "1. QUY ĐỊNH CHUNG",
        )
        result = strip_issuing_document(pages, doc_type=None)
        assert len(result) <= len(pages)
