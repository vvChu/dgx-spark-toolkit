"""Unit tests for the PDF classifier module.

Tests only the pure-Python utility functions that don't require fitz (PyMuPDF).
fitz is available inside the Docker container but not necessarily on the host.
"""
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import only pure-Python helpers (avoid fitz top-level import)
# We inline the functions here for host-safe testing
from ingestion.pdf_classifier import (
    PdfType,
    _has_complex_table_signals,
    _has_broken_ocr_spacing,
)


class TestComplexTableDetection:
    """Test _has_complex_table_signals heuristic."""

    def test_qcvn_table_headers(self):
        text = "STT | Đơn vị | Kích thước | Quy cách"
        assert _has_complex_table_signals(text)

    def test_technical_symbols(self):
        text = "Áp suất ≤ 10 kN/m² và chiều dài ≥ 5m²"
        assert _has_complex_table_signals(text)

    def test_normal_text(self):
        text = "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng"
        assert not _has_complex_table_signals(text)

    def test_empty_text(self):
        assert not _has_complex_table_signals("")

    def test_single_unit(self):
        text = "Tần số MHz"
        assert not _has_complex_table_signals(text)  # Need 2+ signals


class TestBrokenOCRSpacing:
    """Test _has_broken_ocr_spacing detection."""

    def test_broken_spacing(self):
        text = "B Ộ  XÂY  D Ự N G  CỘNG  HÒA  XÃ  HỘI  CHỦ  NGHĨA"
        assert _has_broken_ocr_spacing(text)

    def test_normal_text(self):
        text = "BỘ XÂY DỰNG CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
        assert not _has_broken_ocr_spacing(text)

    def test_short_text(self):
        text = "BXD"
        assert not _has_broken_ocr_spacing(text)

    def test_mixed_content(self):
        """Normal Vietnamese text with some 2-char words (prepositions)."""
        text = "Đây là một quy chuẩn kỹ thuật về phòng cháy chữa cháy"
        assert not _has_broken_ocr_spacing(text)


class TestPdfType:
    """Test PdfType enum values."""

    def test_enum_values(self):
        assert PdfType.NATIVE.value == "NATIVE"
        assert PdfType.SCAN_SIMPLE.value == "SCAN_SIMPLE"
        assert PdfType.SCAN_COMPLEX.value == "SCAN_COMPLEX"

    def test_string_comparison(self):
        assert PdfType.NATIVE == "NATIVE"
        assert PdfType.SCAN_SIMPLE == "SCAN_SIMPLE"


def run_all():
    passed = 0
    failed = 0

    for cls_name, cls in [
        ("TestComplexTableDetection", TestComplexTableDetection),
        ("TestBrokenOCRSpacing", TestBrokenOCRSpacing),
        ("TestPdfType", TestPdfType),
    ]:
        instance = cls()
        for attr in sorted(dir(instance)):
            if attr.startswith("test_"):
                try:
                    getattr(instance, attr)()
                    passed += 1
                    print(f"  ✅ {cls_name}.{attr}")
                except AssertionError as e:
                    failed += 1
                    print(f"  ❌ {cls_name}.{attr}: {e}")
                except Exception as e:
                    failed += 1
                    print(f"  💥 {cls_name}.{attr}: {type(e).__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
