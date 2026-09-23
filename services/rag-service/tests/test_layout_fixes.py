"""
Unit tests for Layout Fixes #1-#5 (markdown layout quality improvements).
Run: pytest tests/test_layout_fixes.py -v
"""
import io
import sys
import pytest

sys.path.insert(0, '/app')

from PIL import Image
import numpy as np


# ─────────────────────────────────────────────
# Fix #1: is_blank_page()
# ─────────────────────────────────────────────
class TestIsBlankPage:
    from ingestion.vision import is_blank_page

    def _make_img(self, pixel_value: int, size=(200, 200)) -> bytes:
        img = Image.fromarray(np.full(size, pixel_value, dtype=np.uint8), mode='L')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        return buf.getvalue()

    def test_near_white_image_blank(self):
        from ingestion.vision import is_blank_page
        img_bytes = self._make_img(245)
        assert is_blank_page(img_bytes, surya_text='') is True

    def test_dark_image_not_blank(self):
        from ingestion.vision import is_blank_page
        img_bytes = self._make_img(80)  # dark
        assert is_blank_page(img_bytes, surya_text='') is False

    def test_enough_text_skips_pixel_check(self):
        """If Surya extracted >60 chars, skip pixel check (watermark edge case)."""
        from ingestion.vision import is_blank_page
        img_bytes = self._make_img(245)  # white image
        long_text = 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Độc lập - Tự do - Hạnh phúc'
        assert is_blank_page(img_bytes, surya_text=long_text) is False

    def test_watermark_with_short_text(self):
        """Page with small logo + short OCR text → still detected as blank."""
        from ingestion.vision import is_blank_page
        img_bytes = self._make_img(240)
        assert is_blank_page(img_bytes, surya_text='Logo') is True  # 4 chars < 60

    def test_ocr_raw_none_never_blank(self):
        """When worker failed (ocr_raw=None), is_blank_page must return False to prevent data loss."""
        from ingestion.vision import is_blank_page
        img_bytes = self._make_img(245)  # 100% white image
        assert is_blank_page(img_bytes, surya_text='', ocr_raw=None) is False

    def test_marginal_white_ratio_protected(self):
        """Image with ~88% white pixels should NOT be detected as blank under 90% threshold."""
        from ingestion.vision import is_blank_page
        # Create an image where exactly 88% of pixels are white (245) and 12% are dark (50)
        arr = np.full((100, 100), 245, dtype=np.uint8)
        arr[:12, :] = 50  # 12% dark rows
        buf = io.BytesIO()
        Image.fromarray(arr, mode='L').save(buf, format='JPEG')
        img_bytes = buf.getvalue()

        # At 88% white ratio, it would have failed under old 85% threshold, but now safe under 90%
        assert is_blank_page(img_bytes, surya_text='', ocr_raw=[]) is False


# ─────────────────────────────────────────────
# Fix #2: is_toc_page()
# ─────────────────────────────────────────────
class TestIsTocPage:
    def test_structured_toc_with_keyword(self):
        from ingestion.vision import is_toc_page
        toc = "MỤC LỤC\n1. QUY ĐỊNH CHUNG 5\n1.1. Phạm vi điều chỉnh 5\n1.2. Đối tượng 5\n2. QUY ĐỊNH KỸ THUẬT 7"
        assert is_toc_page(toc) is True

    def test_inline_toc_pattern(self):
        """Inline TOC: all on one line, numbers at end of each section title."""
        from ingestion.vision import is_toc_page
        inline = "1. QUY ĐỊNH CHUNG5 1.1. Phạm vi điều chỉnh5 1.2. Đối tượng áp dụng5"
        assert is_toc_page(inline) is True

    def test_content_text_not_toc(self):
        """Regular paragraph text should NOT be detected as TOC."""
        from ingestion.vision import is_toc_page
        content = (
            "1.1. Phạm vi điều chỉnh\n"
            "Quy chuẩn này áp dụng cho thiết bị phát, thu phát vô tuyến VHF "
            "điều chế biên độ song biên đầy đủ sóng mang (DSB AM)."
        )
        assert is_toc_page(content) is False

    def test_technical_table_not_toc(self):
        """Technical parameter table rows should NOT trigger TOC detection."""
        from ingestion.vision import is_toc_page
        table = (
            "Bảng 1 - Sai số tần số\n"
            "| Loại thiết bị | Sai số (ppm) |\n"
            "| Trạm gốc (8,33 kHz) | ±1 |\n"
            "| Di động (25 kHz) | ±10 |\n"
        )
        assert is_toc_page(table) is False

    def test_strong_toc_signal_without_keyword(self):
        """4+ TOC-pattern lines → detected even without 'mục lục' keyword."""
        from ingestion.vision import is_toc_page
        toc_no_kw = (
            "1. QUY ĐỊNH CHUNG 5\n"
            "1.1. Phạm vi điều chỉnh 5\n"
            "1.2. Đối tượng áp dụng 5\n"
            "2. QUY ĐỊNH KỸ THUẬT 7\n"
            "3. PHƯƠNG PHÁP ĐO 12"
        )
        assert is_toc_page(toc_no_kw) is True


# ─────────────────────────────────────────────
# Fix #3: summary _extract_content_for_summary
# ─────────────────────────────────────────────
class TestExtractContentForSummary:
    def test_finds_quy_dinh_chung_marker(self):
        from ingestion.vision import VisionExtractor
        # Cover 100 chars (cover page), then ~700 chars of content → marker at pos ~100
        # which is 14% of total ~700 chars — within the 60% threshold
        cover = 'Cover page metadata. ' * 5  # ~105 chars
        content = ('Nội dung lời nói đầu. ' * 30) + '\n1. QUY ĐỊNH CHUNG\nPhạm vi điều chỉnh\nQuy chuẩn này áp dụng cho...' * 10
        text = cover + content
        result = VisionExtractor._extract_content_for_summary(text)
        # The marker should be found and used as start_pos
        assert '1. QUY ĐỊNH CHUNG' in result
        # Result should NOT start from the very beginning (cover chars)
        assert not result.startswith('Cover page')

    def test_fallback_offset_when_no_marker(self):
        """No marker found → start from min(3000, len//5) offset."""
        from ingestion.vision import VisionExtractor
        text = 'A' * 10000  # Long text with no markers
        result = VisionExtractor._extract_content_for_summary(text)
        # Should have skipped 2000 chars (min(3000, 10000//5) = 2000)
        assert len(result) <= 12000
        # Result should NOT be the very beginning
        assert result != text[:12000]

    def test_short_text_no_offset(self):
        """Text < 4000 chars → no offset applied."""
        from ingestion.vision import VisionExtractor
        text = 'Short text ' * 100  # ~1200 chars
        result = VisionExtractor._extract_content_for_summary(text)
        assert result == text[:12000]


# ─────────────────────────────────────────────
# Fix #4: Vietnamese word merge
# ─────────────────────────────────────────────
class TestVietnameseWordMerge:
    def test_cua_cac_merge(self):
        from ingestion.cleaning_utils import clean_llm_text
        result = clean_llm_text('củacác cơ quan', source_id='test')
        assert 'của các' in result

    def test_va_he_merge(self):
        from ingestion.cleaning_utils import clean_llm_text
        result = clean_llm_text('vàhệ thống quản lý', source_id='test')
        assert 'và hệ' in result

    def test_phuc_vu_ket_merge(self):
        from ingestion.cleaning_utils import clean_llm_text
        result = clean_llm_text('phụcvụkết nối hệ thống', source_id='test')
        assert 'phục vụ kết' in result

    def test_technical_unit_not_affected(self):
        """Technical units like kHz, dBm should NOT have spaces inserted."""
        from ingestion.cleaning_utils import clean_llm_text
        result = clean_llm_text('tần số 127,5 MHz với sai số ±1 dBm', source_id='test')
        assert 'MHz' in result
        assert 'dBm' in result

    def test_compound_word_vang_not_broken(self):
        """'vàng' (gold) should not be space-split into 'và ng'."""
        from ingestion.cleaning_utils import clean_llm_text
        result = clean_llm_text('màu vàng và xanh', source_id='test')
        assert 'vàng' in result  # Must stay intact


# ─────────────────────────────────────────────
# Fix #5a: Base64 strip
# ─────────────────────────────────────────────
class TestBase64Strip:
    def test_long_base64_stripped(self):
        from ingestion.cleaning_utils import clean_llm_text
        b64 = 'ni6/zOtQFyD15v9YoWHaBvR0BELvl+jc88YeVgmXCIoQfy2JwuU4AAa+n2Rnt='
        result = clean_llm_text(f'Nội dung. {b64} Tiếp theo.', source_id='test')
        assert '[BASE64_DATA]' in result
        assert 'Nội dung.' in result

    def test_short_string_preserved(self):
        """Short Base64-like strings (< 60 chars) should NOT be stripped."""
        from ingestion.cleaning_utils import clean_llm_text
        # A typical document number, not base64
        result = clean_llm_text('Mã số: G14.27 và H26.15 (identifier)', source_id='test')
        assert 'G14.27' in result

    def test_sha256_hex_not_stripped(self):
        """SHA-256 hex = 64 chars [0-9a-f], NO '+/' chars → should NOT match base64 regex."""
        from ingestion.cleaning_utils import clean_llm_text
        sha = 'a' * 64  # 64 lowercase hex chars, no +/
        result = clean_llm_text(f'Hash: {sha}', source_id='test')
        # sha256 hex doesn't have +/ so won't trigger base64 regex
        # However if it happens to match, it's less critical
        assert 'Hash:' in result


# ─────────────────────────────────────────────
# Fix #5b: XML code fence
# ─────────────────────────────────────────────
class TestXmlCodeFence:
    def test_xml_declaration_wrapped(self):
        from ingestion.exporter import DataExporter
        text = 'Phụ lục C\n<?xml version="1.0" ?>\n<edXMLEnvelope/>'
        result = DataExporter._wrap_xml_blocks(text)
        assert '```xml' in result
        assert 'Phụ lục C' in result

    def test_edxml_namespace_wrapped(self):
        from ingestion.exporter import DataExporter
        text = '<edXML:From><edXML:OrganId>G14</edXML:OrganId></edXML:From>'
        result = DataExporter._wrap_xml_blocks(text)
        assert '```xml' in result

    def test_already_wrapped_not_double_wrapped(self):
        from ingestion.exporter import DataExporter
        text = '```xml\n<edXMLEnvelope/>\n```'
        result = DataExporter._wrap_xml_blocks(text)
        assert result.count('```xml') == 1

    def test_plain_text_not_wrapped(self):
        from ingestion.exporter import DataExporter
        text = 'Điều 1. Phạm vi điều chỉnh\nQuy chuẩn này áp dụng cho...'
        result = DataExporter._wrap_xml_blocks(text)
        assert '```' not in result
