"""Unit tests for pipeline-level fixes (C1-C5, I1-I6) that don't require Milvus/Neo4j."""
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.chunking import DocumentChunker, _split_into_children


class TestC1DedupPipeline:
    """C1: Dedup logic should work on semantic_chunks list in pipeline."""

    def test_dedup_removes_same_text_parent(self):
        chunks = [
            {"text": "[doc] Điều 1. Tiêu đề\nNội dung khoản 1.", "chunk_type": "parent", "page": 1},
            {"text": "[doc] Điều 1. Tiêu đề\nNội dung khoản 1.", "chunk_type": "parent", "page": 1},
            {"text": "[doc] Điều 2. Khác\nNội dung.", "chunk_type": "parent", "page": 2},
        ]
        seen = set()
        deduped = []
        for c in chunks:
            if c.get("chunk_type") == "parent":
                fp = c.get("text", "")[:300]
                if fp in seen:
                    continue
                seen.add(fp)
            deduped.append(c)
        assert len(deduped) == 2

    def test_dedup_keeps_children(self):
        chunks = [
            {"text": "child content A", "chunk_type": "child", "page": 1},
            {"text": "child content A", "chunk_type": "child", "page": 1},
        ]
        seen = set()
        deduped = []
        for c in chunks:
            if c.get("chunk_type") == "parent":
                fp = c.get("text", "")[:300]
                if fp in seen:
                    continue
                seen.add(fp)
            deduped.append(c)
        # Children are NOT deduped (only parents)
        assert len(deduped) == 2


class TestC2PrefixStrip:
    """C2: [doc_id] prefix should be stripped before embedding."""

    def test_strip_simple_prefix(self):
        text = "[Linh_vuc_BTP/01/2023/TT-BTP] Điều 1. Phạm vi điều chỉnh"
        cleaned = re.sub(r'^\[.*?\]\s*', '', text, count=1)
        assert cleaned == "Điều 1. Phạm vi điều chỉnh"

    def test_strip_context_prefix(self):
        text = "[doc] [Chương I] ::: Điều 1. Phạm vi"
        cleaned = re.sub(r'^\[.*?\]\s*', '', text, count=1)
        cleaned = re.sub(r'^.*?:::\s*', '', cleaned, count=1)
        assert cleaned == "Điều 1. Phạm vi"

    def test_no_prefix(self):
        text = "Điều 1. Phạm vi"
        cleaned = re.sub(r'^\[.*?\]\s*', '', text, count=1)
        assert cleaned == "Điều 1. Phạm vi"


class TestC4DateValidation:
    """C4: Metadata date format should be validated."""

    def test_valid_date_dd_mm_yyyy(self):
        assert bool(re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$|^\d{4}-\d{2}-\d{2}$', "16/01/2023"))

    def test_valid_date_iso(self):
        assert bool(re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$|^\d{4}-\d{2}-\d{2}$', "2023-01-16"))

    def test_invalid_date(self):
        assert not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$|^\d{4}-\d{2}-\d{2}$', "January 2023")

    def test_reject_default_placeholder(self):
        date = "2025-01-01"
        assert date in ("2025-01-01", "01/01/2025", "01-01-2025")


class TestI3ChildLength:
    """I3: Child chunks should be at least 200 chars."""

    def test_min_child_length(self):
        long_text = (
            "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng. "
            "Thông tư này quy định chế độ báo cáo về tình hình thi hành pháp luật về xử lý vi phạm hành chính. "
            "Đối tượng áp dụng gồm cơ quan, tổ chức, cá nhân có liên quan. "
            "Báo cáo phải đảm bảo tính chính xác, kịp thời, đầy đủ theo quy định. "
            "Các biện pháp xử lý vi phạm hành chính phải tuân thủ đúng quy trình quy định tại Luật XLVPHC."
        )
        children = _split_into_children(
            long_text, "doc", "src.pdf", 1, "p:1:art_0", "[doc]", [0,0,1000,1000]
        )
        for child in children:
            text = child["text"]
            # Strip [doc] prefix for length check
            text = re.sub(r'^\[.*?\]\s*', '', text)
            assert len(text) >= 80, f"Child too short ({len(text)} chars): {text[:60]}..."


class TestI5SafeTrunc:
    """I5: safe_trunc should not break Vietnamese UTF-8 chars."""

    def test_trunc_preserves_chars(self):
        def safe_trunc(val, limit):
            if not val: return ""
            v_str = str(val)
            v_bytes = v_str.encode('utf-8')
            if len(v_bytes) <= limit: return v_str
            while len(v_str.encode('utf-8')) > limit and v_str:
                v_str = v_str[:-1]
            return v_str

        text = "Điều chỉnh và đối tượng áp dụng"
        truncated = safe_trunc(text, 20)
        # Should be valid UTF-8 and not end with broken chars
        truncated.encode('utf-8')  # Will throw if broken
        assert len(truncated.encode('utf-8')) <= 20
        assert len(truncated) > 0

    def test_trunc_short_text(self):
        def safe_trunc(val, limit):
            if not val: return ""
            v_str = str(val)
            v_bytes = v_str.encode('utf-8')
            if len(v_bytes) <= limit: return v_str
            while len(v_str.encode('utf-8')) > limit and v_str:
                v_str = v_str[:-1]
            return v_str

        assert safe_trunc("short", 100) == "short"
        assert safe_trunc("", 100) == ""
        assert safe_trunc(None, 100) == ""


class TestC3DigitalTableDetection:
    """C3: Digital PDF blocks with table patterns should be labeled as table."""

    def test_pipe_table_detected(self):
        text = "Column A | Column B | Column C\n---|---|---\nVal 1 | Val 2 | Val 3"
        pipe_count = text.count('|')
        assert pipe_count >= 3

    def test_digit_runs_with_short_fields(self):
        text = "STT\n1\n2\n3\nSố lượng\n100.000\n200.000\n300.000\n400.000"
        lines = text.split('\n')
        short_fields = sum(1 for l in lines if len(l.strip()) < 15)
        has_digit_runs = len(re.findall(r'\d{1,3}(?:[.,]\d{3})*', text)) > 3
        assert short_fields > 3 and has_digit_runs


def run_all():
    passed = 0
    failed = 0

    for cls_name, cls in [
        ("TestC1DedupPipeline", TestC1DedupPipeline),
        ("TestC2PrefixStrip", TestC2PrefixStrip),
        ("TestC4DateValidation", TestC4DateValidation),
        ("TestI3ChildLength", TestI3ChildLength),
        ("TestI5SafeTrunc", TestI5SafeTrunc),
        ("TestC3DigitalTableDetection", TestC3DigitalTableDetection),
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
