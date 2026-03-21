"""Unit tests for ingestion.exporter — Markdown export quality fixes."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.exporter import DataExporter
from ingestion.table_extraction import _validate_markdown_table
from ingestion.chunking import (
    _merge_small_segments, _is_noise_chunk,
    DocumentChunker, LayoutAwareChunker,
)


class TestDedupParentChunks:
    """Fix 1: Duplicate parent chunks should be removed."""

    def test_removes_exact_duplicates(self):
        chunks = [
            {"text": "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng\n1. Phạm vi điều chỉnh...", "page": 1, "chunk_type": "parent", "parent_id": "file:1:art_0"},
            {"text": "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng\n1. Phạm vi điều chỉnh...", "page": 1, "chunk_type": "parent", "parent_id": "file:1:art_1"},
            {"text": "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng\n1. Phạm vi điều chỉnh...", "page": 1, "chunk_type": "parent", "parent_id": "file:1:art_2"},
        ]
        result = DataExporter._dedup_parent_chunks(chunks)
        assert len(result) == 1, f"Expected 1 unique chunk, got {len(result)}"

    def test_keeps_different_chunks(self):
        chunks = [
            {"text": "Điều 1. Phạm vi điều chỉnh...", "page": 1, "chunk_type": "parent"},
            {"text": "Điều 2. Trách nhiệm báo cáo...", "page": 2, "chunk_type": "parent"},
            {"text": "Điều 3. Chế độ báo cáo...", "page": 2, "chunk_type": "parent"},
        ]
        result = DataExporter._dedup_parent_chunks(chunks)
        assert len(result) == 3, f"Expected 3 unique chunks, got {len(result)}"

    def test_empty_list(self):
        assert DataExporter._dedup_parent_chunks([]) == []


class TestGarbledChunkDetection:
    """Fix 2: Garbled table text should be detected and skipped."""

    def test_detects_unicode_garbage(self):
        text = "xử phạt vi phạm hành chính Kết quả thi hành quyết định khiểu quyêt định khởi kiện (10) nai, Sŷ\nį cương quyêt hành định (15) chê Số į hoãn, quyết miễn, giảm định (14)\nSô ďã hành quyết phạm chímh Tổng định phạt (11)\nΧŲ phạt જ chuyển"
        assert DataExporter._is_garbled_chunk(text) is True

    def test_detects_html_tags(self):
        text = "Số đối tượng bị xử phạt <math>\\mathbf{T}^{\\delta}</math> 0 đôi với <br>thế biện nhờ niên áр <sup>5</sup>"
        assert DataExporter._is_garbled_chunk(text) is True

    def test_detects_repetitive_text(self):
        # Block must be >= 200 chars for the fingerprint to match
        block = "áp dụng các biện pháp xử lý hành chính Tình hình tổ chức thi hành quyết định Tổng sô thời hạn áp dụng Không tượng giảm duroc quyết châp hành định đôi Tổng số đình chỉ turong được quyết hành châp tam định đôi cộng đồng biện pháp giáo dục thay thế "
        text = (block * 5)  # Repeat 5 times
        assert DataExporter._is_garbled_chunk(text) is True

    def test_normal_text_not_garbled(self):
        text = ("Điều 1. Ban hành kèm theo Quyết định này Kế hoạch thực hiện "
                "Quy hoạch thành phố Đà Nẵng thời kỳ 2021 - 2030, tầm nhìn "
                "đến năm 2050. Chủ tịch Ủy ban nhân dân thành phố chịu trách "
                "nhiệm toàn diện về tính chính xác.")
        assert DataExporter._is_garbled_chunk(text) is False

    def test_short_text_not_garbled(self):
        assert DataExporter._is_garbled_chunk("") is False
        assert DataExporter._is_garbled_chunk("short") is False


class TestHeadingExtraction:
    """Fix 3: Headings should be truncated to article title only."""

    def test_extracts_dieu_heading(self):
        path = "[doc_id] -> [Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng]"
        result = DataExporter._extract_heading_from_hierarchy(path, "doc_id")
        assert result is not None
        assert result.startswith("Điều 1.")
        assert len(result) <= 80

    def test_truncates_long_heading(self):
        # Simulate heading with body text leaked in
        path = "[doc_id] -> [Điều 4. Hình thức báo cáo và phương thức gửi, nhận báo cáo xuất trong lĩnh vực xử lý vi phạm hành chính, được thực hiện theo yêu cầu]"
        result = DataExporter._extract_heading_from_hierarchy(path, "doc_id")
        assert result is not None
        assert len(result) <= 80, f"Heading too long ({len(result)} chars): {result}"

    def test_skips_header(self):
        path = "[doc_id > Header]"
        result = DataExporter._extract_heading_from_hierarchy(path, "doc_id")
        assert result is None

    def test_skips_doc_id_only(self):
        path = "[my_doc_id]"
        result = DataExporter._extract_heading_from_hierarchy(path, "my_doc_id")
        assert result is None


class TestMarkdownGeneration:
    """Integration test: full markdown generation quality."""

    def test_no_duplicate_content(self):
        exporter = DataExporter("/tmp/test_exports")
        chunks = [
            {"text": "[doc] Điều 1. Tiêu đề\nNội dung khoản 1.", "page": 1, "chunk_type": "parent", "chunk_index": 0, "parent_id": "a:1:art_0", "hierarchy_path": "[doc] -> [Điều 1.]"},
            {"text": "[doc] Điều 1. Tiêu đề\nNội dung khoản 1.", "page": 1, "chunk_type": "parent", "chunk_index": 1, "parent_id": "a:1:art_1", "hierarchy_path": "[doc] -> [Điều 1.]"},
            {"text": "[doc] Điều 2. Tiêu đề khác\nNội dung khoản 1.", "page": 2, "chunk_type": "parent", "chunk_index": 0, "parent_id": "a:2:art_0", "hierarchy_path": "[doc] -> [Điều 2.]"},
        ]
        md = exporter._generate_markdown("path.pdf", "doc", {}, "Summary", chunks)
        # Dedup should remove the second identical Điều 1 chunk
        # Content "Tiêu đề" should appear only once
        content_count = md.count("Tiêu đề\nNội dung khoản 1.")
        assert content_count <= 1, f"Điều 1 content appeared {content_count} times (expected <=1)"

    def test_garbled_table_becomes_placeholder(self):
        exporter = DataExporter("/tmp/test_exports")
        garbled = "ŧĖΧŲġşŷįďŕŝ some garbage text with lots of ŧĖΧŲġşŷ nonsense"
        chunks = [
            {"text": garbled, "page": 5, "chunk_type": "parent", "parent_id": "a:5:art_0", "hierarchy_path": "[doc > Table > Page 5]", "is_table": True},
        ]
        md = exporter._generate_markdown("path.pdf", "doc", {}, "Summary", chunks)
        assert "⚠️" in md
        assert garbled not in md


class TestLegalTaxonomy:
    """Fix 4: Document type classification from filenames."""

    def test_tt_prefix_filename(self):
        from ingestion.legal_taxonomy import classify_doc_type
        result = classify_doc_type(filename="TT01-2023-BTP_Quy dinh che do BC.pdf")
        assert result == "THONG_TU", f"Expected THONG_TU, got {result}"

    def test_nd_prefix_filename(self):
        from ingestion.legal_taxonomy import classify_doc_type
        result = classify_doc_type(filename="ND15-2021-CP_Quy dinh chi tiet.pdf")
        assert result == "NGHI_DINH", f"Expected NGHI_DINH, got {result}"

    def test_qd_prefix_filename(self):
        from ingestion.legal_taxonomy import classify_doc_type
        result = classify_doc_type(filename="QD08-TTg_Title.pdf")
        assert result == "QUYET_DINH", f"Expected QUYET_DINH, got {result}"

    def test_existing_rules_still_work(self):
        from ingestion.legal_taxonomy import classify_doc_type
        # These use the separator-based rules
        result = classify_doc_type(doc_number="01/2023/TT-BTP")
        assert result == "THONG_TU", f"Expected THONG_TU, got {result}"

        result = classify_doc_type(doc_number="118/2021/NĐ-CP")
        assert result == "NGHI_DINH", f"Expected NGHI_DINH, got {result}"


class TestHeadingDedup:
    """Fix 4: Consecutive heading deduplication."""

    def test_removes_short_heading_before_full(self):
        exporter = DataExporter("/tmp/test_exports")
        chunks = [
            {"text": "[doc] Điều 2.", "page": 1, "chunk_type": "parent", "chunk_index": 0,
             "hierarchy_path": "[doc] -> [Điều 2.]"},
            {"text": "[doc] Điều 2. Giải thích từ ngữ\nTrong Thông tư này...", "page": 2, "chunk_type": "parent", "chunk_index": 0,
             "hierarchy_path": "[doc] -> [Điều 2. Giải thích từ ngữ]"},
        ]
        md = exporter._generate_markdown("path.pdf", "doc", {}, "Summary", chunks)
        # "### Điều 2." (short) should be removed, only full version kept
        dieu_2_headings = [l for l in md.split('\n') if l.startswith('### Điều 2')]
        assert len(dieu_2_headings) == 1, f"Expected 1 heading, got {len(dieu_2_headings)}: {dieu_2_headings}"
        assert 'Giải thích' in dieu_2_headings[0]

    def test_keeps_different_headings(self):
        exporter = DataExporter("/tmp/test_exports")
        chunks = [
            {"text": "[doc] Điều 1. Phạm vi\nNội dung", "page": 1, "chunk_type": "parent", "chunk_index": 0,
             "hierarchy_path": "[doc] -> [Điều 1. Phạm vi]"},
            {"text": "[doc] Điều 2. Trách nhiệm\nNội dung", "page": 2, "chunk_type": "parent", "chunk_index": 0,
             "hierarchy_path": "[doc] -> [Điều 2. Trách nhiệm]"},
        ]
        md = exporter._generate_markdown("path.pdf", "doc", {}, "Summary", chunks)
        assert '### Điều 1' in md
        assert '### Điều 2' in md


class TestTableValidation:
    """Fix 2: Garbled markdown table validation."""

    def test_rejects_mostly_empty_table(self):
        md = """| Col1 | Col2 | Col3 |
| --- | --- | --- |
|  |  |  |
| x |  |  |
|  |  | y |"""
        assert _validate_markdown_table(md) is False

    def test_rejects_fragment_table(self):
        md = """| A | B | C |
| --- | --- | --- |
| Đo | chi | c |
| rộng | tng | ng |
| hình | c | th |"""
        assert _validate_markdown_table(md) is False

    def test_accepts_valid_table(self):
        md = """| Kích thước | Đơn vị | Giá trị |
| --- | --- | --- |
| Chiều rộng | mm | 1200 |
| Chiều cao | mm | 800 |
| Trọng lượng | kg | 450 |"""
        assert _validate_markdown_table(md) is True

    def test_rejects_too_short(self):
        md = "| A | B |\n| --- | --- |"
        assert _validate_markdown_table(md) is False


class TestChunkingQuality:
    """Tests for chunking quality improvements (Fixes 1-4)."""

    def test_merge_small_segments(self):
        """FIX-1: Small segments should be merged into larger blocks."""
        segments = [
            {"text": "Short segment one.", "bbox": [0, 0, 100, 100]},
            {"text": "Short segment two.", "bbox": [0, 100, 100, 200]},
            {"text": "Short segment three.", "bbox": [0, 200, 100, 300]},
            {"text": "A" * 400, "bbox": [0, 300, 100, 400]},  # Large segment
        ]
        blocks = _merge_small_segments(segments, min_block_size=300)
        # First 3 small segments should be merged into 1 block
        assert len(blocks) <= 2, f"Expected <=2 blocks, got {len(blocks)}"
        assert "Short segment one" in blocks[0][0]
        assert "Short segment two" in blocks[0][0]

    def test_children_from_article(self):
        """FIX-2: Long articles without numbered sub-parts should still get children."""
        chunker = DocumentChunker()
        long_article = "Điều 1. " + "Nội dung rất dài. " * 50  # >500 chars
        chunks = chunker.chunk_document(
            long_article, "test.pdf", 1, "doc/test"
        )
        parents = [c for c in chunks if c.get('chunk_type') == 'parent']
        children = [c for c in chunks if c.get('chunk_type') == 'child']
        assert len(parents) >= 1, f"Expected parents, got {len(parents)}"
        assert len(children) >= 1, f"Expected children for long article, got {len(children)}"

    def test_noise_filter_boilerplate(self):
        """FIX-3: Government headers should be filtered as noise."""
        assert _is_noise_chunk("[doc] CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Độc lập - Tự do - Hạnh phúc") is True
        assert _is_noise_chunk("[doc] Số: /2023/TT-BGTVT Hà Nội, ngày tháng 12 năm 2023") is True
        assert _is_noise_chunk("[doc] Kính gửi: Bộ Giao thông vận tải") is True
        # But long content with these words should NOT be noise
        assert _is_noise_chunk("[doc] CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM " + "x" * 200) is False

    def test_section_fallback(self):
        """FIX-4: LayoutAwareChunker should try Section chunker before per-segment."""
        chunker = LayoutAwareChunker()
        # Two paragraphs separated by blank line — no Điều but SectionChunker should work
        layout = [{
            "label": "text",
            "text": "Paragraph one content here.\n\nParagraph two content here with more text to make it substantial enough for section chunking to work properly. " * 3,
            "bbox": [0, 0, 1000, 1000]
        }]
        chunks = chunker.chunk("ignored", "test.pdf", 1, "doc/test", layout=layout)
        # Should produce chunks (section or segment fallback)
        assert len(chunks) >= 1, f"Expected chunks, got {len(chunks)}"


class TestGFMTableFix:
    """P1: Missing GFM separator rows should be inserted."""

    def test_inserts_separator_row(self):
        text = "| Tên | Đơn vị | Giá trị |\n| A | m2 | 100 |\n| B | m2 | 200 |"
        result = DataExporter._fix_table_gfm(text)
        assert '| --- | --- | --- |' in result

    def test_preserves_existing_separator(self):
        text = "| Tên | Đơn vị |\n| --- | --- |\n| A | m2 |"
        result = DataExporter._fix_table_gfm(text)
        # Should not insert a duplicate separator — only the original remains
        assert result == text, f"Should not modify table with existing separator, got: {result}"

    def test_no_change_non_table(self):
        text = "Đây là văn bản bình thường không có bảng."
        assert DataExporter._fix_table_gfm(text) == text

    def test_numeric_row_not_mistaken_as_header(self):
        # All-numeric cells should NOT get a separator inserted
        text = "| 100 | 200 | 300 |\n| 400 | 500 | 600 |"
        result = DataExporter._fix_table_gfm(text)
        assert '---' not in result


class TestBoilerplateStrip:
    """P5: Government boilerplate should be stripped from Content."""

    def test_strips_full_header(self):
        text = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\nĐiều 1. Nội dung"
        result = DataExporter._strip_content_boilerplate(text)
        assert 'CỘNG HÒA' not in result
        assert 'Điều 1' in result

    def test_strips_partial_header(self):
        text = "Độc lập – Tự do – Hạnh phúc\nĐiều 2. Nội dung"
        result = DataExporter._strip_content_boilerplate(text)
        assert 'Độc lập' not in result
        assert 'Điều 2' in result

    def test_preserves_normal_text(self):
        text = "Điều 1. Ban hành kèm theo Quyết định này Kế hoạch thực hiện."
        result = DataExporter._strip_content_boilerplate(text)
        assert result == text

    def test_strips_so_number(self):
        text = "Số: 107/QĐ-BXD\nĐiều 1. Nội dung"
        result = DataExporter._strip_content_boilerplate(text)
        assert 'Số: 107' not in result
        assert 'Điều 1' in result


def run_all():
    """Simple test runner."""
    passed = 0
    failed = 0
    errors = []

    for cls_name, cls in [
        ("TestDedupParentChunks", TestDedupParentChunks),
        ("TestGarbledChunkDetection", TestGarbledChunkDetection),
        ("TestHeadingExtraction", TestHeadingExtraction),
        ("TestMarkdownGeneration", TestMarkdownGeneration),
        ("TestLegalTaxonomy", TestLegalTaxonomy),
        ("TestHeadingDedup", TestHeadingDedup),
        ("TestTableValidation", TestTableValidation),
        ("TestChunkingQuality", TestChunkingQuality),
        ("TestGFMTableFix", TestGFMTableFix),
        ("TestBoilerplateStrip", TestBoilerplateStrip),
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
                    errors.append(f"  ❌ {cls_name}.{attr}: {e}")
                    print(f"  ❌ {cls_name}.{attr}: {e}")
                except Exception as e:
                    failed += 1
                    errors.append(f"  💥 {cls_name}.{attr}: {type(e).__name__}: {e}")
                    print(f"  💥 {cls_name}.{attr}: {type(e).__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(e)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
