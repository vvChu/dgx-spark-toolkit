"""Precedence tests for retrieval.query_classifier.

High-priority COMPLEX (comparison, conflict, two or more citations) must win
over an article or document-number lookup. Bare prepositions "trước" and "sau"
must stay SEMANTIC.
"""
import pytest

from retrieval.query_classifier import QueryIntent, classify_query

_COMPLEX_CONFIDENCE = 0.85
_EXACT_CONFIDENCE = 0.90
_SEMANTIC_CONFIDENCE = 0.75
_EMPTY_CONFIDENCE = 0.5


def _expect(query: str, intent: QueryIntent, rule: str, confidence: float) -> None:
    result = classify_query(query)
    assert result.intent is intent, (query, result)
    assert result.matched_rule == rule, (query, result)
    assert result.confidence == confidence, (query, result)


def test_comparison_with_articles_is_complex():
    _expect(
        "So sánh Điều 15 Nghị định 87/2023 và Điều 16 Nghị định 88/2023",
        QueryIntent.COMPLEX,
        "comparison_keyword",
        _COMPLEX_CONFIDENCE,
    )


def test_conflict_with_articles_is_complex():
    _expect(
        "Mâu thuẫn giữa Điều 4 và Điều 8 QCVN 06:2022",
        QueryIntent.COMPLEX,
        "conflict_keyword",
        _COMPLEX_CONFIDENCE,
    )


def test_multiple_doc_numbers_is_complex():
    _expect(
        "87/2023/NĐ-CP và 88/2023/NĐ-CP",
        QueryIntent.COMPLEX,
        "multiple_doc_refs",
        _COMPLEX_CONFIDENCE,
    )


def test_before_after_preposition_is_semantic():
    _expect(
        "biện pháp an toàn trước khi đào móng",
        QueryIntent.SEMANTIC,
        "default_semantic",
        _SEMANTIC_CONFIDENCE,
    )
    _expect(
        "kiểm tra sau khi thi công",
        QueryIntent.SEMANTIC,
        "default_semantic",
        _SEMANTIC_CONFIDENCE,
    )


def test_timeline_legal_is_complex():
    _expect(
        "Quy định trước năm 2020 về PCCC",
        QueryIntent.COMPLEX,
        "timeline_keyword",
        _COMPLEX_CONFIDENCE,
    )
    # "sửa đổi" is an amendment cue and is scanned before the timeline phrase "lịch sử".
    _expect(
        "lịch sử sửa đổi Thông tư",
        QueryIntent.COMPLEX,
        "amendment_keyword",
        _COMPLEX_CONFIDENCE,
    )


def test_single_article_is_exact():
    _expect(
        "Điều 15 khoản 3",
        QueryIntent.EXACT,
        "article_reference",
        _EXACT_CONFIDENCE,
    )


def test_single_doc_number_is_exact():
    _expect(
        "Nghị định 87/2023/NĐ-CP",
        QueryIntent.EXACT,
        "doc_number_with_year",
        _EXACT_CONFIDENCE,
    )


def test_technical_standard_is_exact():
    _expect(
        "QCVN 06:2022/BXD",
        QueryIntent.EXACT,
        "technical_standard_code",
        _EXACT_CONFIDENCE,
    )


def test_empty_and_whitespace_is_semantic():
    for query in ("", "   ", "\t\n"):
        _expect(query, QueryIntent.SEMANTIC, "empty_query", _EMPTY_CONFIDENCE)


@pytest.mark.parametrize("query", [
    "so sánh hai văn bản",
    "khác nhau giữa Nghị định cũ và mới",
    "giống nhau về phạm vi áp dụng",
    "phân biệt TT 01 và TT 02",
    "đối chiếu Điều 5 với Điều 9",
])
def test_comparison_keywords_are_complex(query):
    result = classify_query(query)
    assert result.intent is QueryIntent.COMPLEX
    assert result.matched_rule == "comparison_keyword"


@pytest.mark.parametrize("query", [
    "xung đột điều khoản",
    "không nhất quán giữa khoản 1 và khoản 2",
    "chồng chéo thẩm quyền cấp phép",
])
def test_conflict_keywords_are_complex(query):
    result = classify_query(query)
    assert result.intent is QueryIntent.COMPLEX
    assert result.matched_rule == "conflict_keyword"


def test_two_technical_standards_are_complex():
    _expect(
        "QCVN 06:2022/BXD và QCVN 07:2023/BXD",
        QueryIntent.COMPLEX,
        "multiple_doc_refs",
        _COMPLEX_CONFIDENCE,
    )
    _expect(
        "TCVN 9385:2012 thay thế TCVN 9385:2010",
        QueryIntent.COMPLEX,
        "multiple_doc_refs",
        _COMPLEX_CONFIDENCE,
    )


def test_mixed_doc_number_and_standard_is_complex():
    _expect(
        "87/2023/NĐ-CP và QCVN 06:2022/BXD",
        QueryIntent.COMPLEX,
        "multiple_doc_refs",
        _COMPLEX_CONFIDENCE,
    )
    _expect(
        "QCVN 06:2022/BXD áp dụng theo 16/2025/TT-BXD",
        QueryIntent.COMPLEX,
        "multiple_doc_refs",
        _COMPLEX_CONFIDENCE,
    )


@pytest.mark.parametrize("query", [
    "văn bản nào thay thế NĐ này",
    "thông tư sửa đổi bổ sung",
    "ban hành mới quy chuẩn PCCC",
    "còn hiệu lực không",
    "quy định nào hết hiệu lực",
])
def test_amendment_keyword_is_complex(query):
    result = classify_query(query)
    assert result.intent is QueryIntent.COMPLEX
    assert result.matched_rule == "amendment_keyword"


@pytest.mark.parametrize("query", [
    "có hiệu lực sau ngày 01/01/2024",
    "áp dụng trước tháng ban hành",
    "trước thời điểm có hiệu lực",
    "sau khi có hiệu lực của nghị định",
    "từ năm 2018",
    "đến năm 2024",
    "tiến trình sửa quy chuẩn",
    "timeline của thông tư phòng cháy",
    "lịch sử hình thành quy chuẩn",
])
def test_legal_timeline_phrases_are_complex(query):
    result = classify_query(query)
    assert result.intent is QueryIntent.COMPLEX
    assert result.matched_rule == "timeline_keyword"


def test_theory_question_is_semantic():
    _expect(
        "yêu cầu phòng cháy chữa cháy nhà cao tầng",
        QueryIntent.SEMANTIC,
        "default_semantic",
        _SEMANTIC_CONFIDENCE,
    )
    _expect(
        "từ năm nào quy chuẩn PCCC được áp dụng",
        QueryIntent.SEMANTIC,
        "default_semantic",
        _SEMANTIC_CONFIDENCE,
    )


def test_quoted_exact_term_is_exact():
    _expect(
        'tra cứu "phòng cháy chữa cháy"',
        QueryIntent.EXACT,
        "quoted_exact_term",
        _EXACT_CONFIDENCE,
    )


def test_doc_number_without_year_is_exact():
    _expect(
        "1417/QĐ-TTg",
        QueryIntent.EXACT,
        "doc_number_no_year",
        _EXACT_CONFIDENCE,
    )


def test_single_identifier_beats_amendment_keyword():
    """Amendment stays behind EXACT, so one citation plus "còn hiệu lực" is EXACT."""
    _expect(
        "Nghị định 87/2023/NĐ-CP còn hiệu lực không",
        QueryIntent.EXACT,
        "doc_number_with_year",
        _EXACT_CONFIDENCE,
    )
    _expect(
        "QCVN 06:2022/BXD hết hiệu lực",
        QueryIntent.EXACT,
        "technical_standard_code",
        _EXACT_CONFIDENCE,
    )


def test_article_with_bare_preposition_stays_exact():
    _expect(
        "Điều 12 trước khi đào móng",
        QueryIntent.EXACT,
        "article_reference",
        _EXACT_CONFIDENCE,
    )
