"""Query Intent Classifier — routes queries to the most appropriate retrieval strategy.

Three strategies:
    EXACT   → BM25-first (sparse-heavy): one doc number, one article, one standard code
    COMPLEX → AgenticRetriever (multi-hop): comparisons, conflicts, multi-doc, timelines
    SEMANTIC → Standard hybrid search (default): semantic questions about legal content

Precedence inside classify_query (first match wins):
    1. Empty query → SEMANTIC
    2. High-priority COMPLEX: two or more citations, comparison, conflict
    3. EXACT: a single document number, standard code, article, or quoted term
    4. Remaining COMPLEX: amendment verbs, legal timeline phrases
    5. Default SEMANTIC

Bare prepositions "trước" / "sau" are not timeline cues.

Usage:
    from retrieval.query_classifier import classify_query, QueryIntent
    intent = classify_query("Điều 15 Nghị định 87/2023")
    # → QueryIntent.EXACT
"""
import logging
import re
from enum import Enum
from typing import NamedTuple

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    EXACT = "exact"       # Exact term/number lookup → sparse-heavy search
    COMPLEX = "complex"   # Multi-document, comparison, timeline → agentic
    SEMANTIC = "semantic" # Default semantic search → hybrid balanced


class ClassificationResult(NamedTuple):
    intent: QueryIntent
    confidence: float
    matched_rule: str


# Single decisive COMPLEX hit. EXACT stays at 0.90; these are not calibrated probabilities.
_COMPLEX_CONFIDENCE = 0.85

# ── Pattern sets ──────────────────────────────────────────────────────────────

# COMPLEX, checked before EXACT so a citation inside a comparison is not swallowed.
_HIGH_PRIORITY_COMPLEX_PATTERNS = [
    # Two or more legal document numbers: 87/2023/NĐ-CP ... 88/2023/NĐ-CP
    (re.compile(
        r'\b\d{1,5}/\d{4}/[A-ZĐ\-]+\b.*\b\d{1,5}/\d{4}/[A-ZĐ\-]+\b',
        re.UNICODE
    ), "multiple_doc_refs"),
    # Two or more technical standards: QCVN 06:2022 ... QCVN 07:2023
    # Same family as technical_standard_code, otherwise the first code returns EXACT.
    (re.compile(
        r'\b(?:QCVN|TCVN|TCCS|QCĐP)\s+\d+[:/]\d{4}\b'
        r'.*'
        r'\b(?:QCVN|TCVN|TCCS|QCĐP)\s+\d+[:/]\d{4}\b',
        re.IGNORECASE | re.UNICODE
    ), "multiple_doc_refs"),
    # One year-form document number and one technical standard, either order.
    (re.compile(
        r'\b\d{1,5}/\d{4}/[A-ZĐ\-]+\b'
        r'.*'
        r'\b(?:QCVN|TCVN|TCCS|QCĐP)\s+\d+[:/]\d{4}\b'
        r'|'
        r'\b(?:QCVN|TCVN|TCCS|QCĐP)\s+\d+[:/]\d{4}\b'
        r'.*'
        r'\b\d{1,5}/\d{4}/[A-ZĐ\-]+\b',
        re.IGNORECASE | re.UNICODE
    ), "multiple_doc_refs"),
    (re.compile(
        r'\b(?:so sánh|khác nhau|giống nhau|phân biệt|đối chiếu)\b',
        re.IGNORECASE | re.UNICODE
    ), "comparison_keyword"),
    (re.compile(
        r'\b(?:mâu thuẫn|xung đột|không nhất quán|chồng chéo)\b',
        re.IGNORECASE | re.UNICODE
    ), "conflict_keyword"),
]

# EXACT: one doc number, one standard, one article/clause, or a quoted term.
_EXACT_PATTERNS = [
    # Vietnamese legal document numbers WITH year: 87/2023/NĐ-CP, 16/2025/TT-BXD
    (re.compile(
        r'\b\d{1,5}/\d{4}/(?:NĐ|TT|QĐ|CV|CT|KH|BT|HD|NQ)-[A-ZĐa-z]{2,10}\b',
        re.UNICODE
    ), "doc_number_with_year"),
    # Vietnamese legal document numbers WITHOUT year: 1417/QĐ-TTg, 2345/QĐ-BXD
    (re.compile(
        r'\b\d{1,5}/(?:QĐ|NQ|CT|CV)-[A-ZĐa-z]{2,10}\b',
        re.UNICODE
    ), "doc_number_no_year"),
    # Technical standard numbers: QCVN 06:2022, TCVN 1234:2020, TCCS 001:2024
    (re.compile(
        r'\b(?:QCVN|TCVN|TCCS|QCĐP)\s+\d+[:/]\d{4}\b',
        re.IGNORECASE
    ), "technical_standard_code"),
    # Article references: Điều 15, khoản 3, Chương 2
    (re.compile(
        r'\b(?:Điều|Khoản|Điểm|Chương|Mục|Phần)\s+\d+\b',
        re.IGNORECASE | re.UNICODE
    ), "article_reference"),
    # Exact section titles in quotes
    (re.compile(r'"[^"]{5,80}"'), "quoted_exact_term"),
]

# COMPLEX after EXACT. A single citation plus one of these verbs stays EXACT.
_REMAINING_COMPLEX_PATTERNS = [
    (re.compile(
        r'\b(?:thay thế|sửa đổi|bổ sung|ban hành mới|còn hiệu lực|hết hiệu lực)\b',
        re.IGNORECASE | re.UNICODE
    ), "amendment_keyword"),
    # Legal time phrases only. Bare "trước"/"sau" ("trước khi đào móng") must not match.
    (re.compile(
        r'\b(?:trước|sau)\s+(?:ngày|tháng|năm\s+\d{4}|thời điểm|khi có hiệu lực)\b',
        re.IGNORECASE | re.UNICODE
    ), "timeline_keyword"),
    (re.compile(
        r'\b(?:từ năm|đến năm)\s+\d{4}\b',
        re.IGNORECASE | re.UNICODE
    ), "timeline_keyword"),
    (re.compile(
        r'\b(?:lịch sử|tiến trình|timeline)\b',
        re.IGNORECASE | re.UNICODE
    ), "timeline_keyword"),
]


def _first_matching_rule(
    patterns: list[tuple[re.Pattern[str], str]],
    query: str,
) -> str | None:
    for pattern, rule_name in patterns:
        if pattern.search(query):
            return rule_name
    return None


def classify_query(query: str) -> ClassificationResult:
    """Classify a query into EXACT, COMPLEX, or SEMANTIC intent.

    Uses regex pattern matching only — zero LLM latency overhead.
    High-priority comparison, conflict, and multi-citation rules run before EXACT.

    Returns:
        ClassificationResult with intent, confidence, and matched rule name.
    """
    if not query or not query.strip():
        return ClassificationResult(QueryIntent.SEMANTIC, 0.5, "empty_query")

    q = query.strip()

    high_rule = _first_matching_rule(_HIGH_PRIORITY_COMPLEX_PATTERNS, q)
    if high_rule:
        logger.debug(f"[QueryClassifier] COMPLEX match via '{high_rule}': {q[:60]}")
        return ClassificationResult(QueryIntent.COMPLEX, _COMPLEX_CONFIDENCE, high_rule)

    exact_rule = _first_matching_rule(_EXACT_PATTERNS, q)
    if exact_rule:
        logger.debug(f"[QueryClassifier] EXACT match via '{exact_rule}': {q[:60]}")
        return ClassificationResult(QueryIntent.EXACT, 0.90, exact_rule)

    remaining_rule = _first_matching_rule(_REMAINING_COMPLEX_PATTERNS, q)
    if remaining_rule:
        logger.debug(f"[QueryClassifier] COMPLEX match via '{remaining_rule}': {q[:60]}")
        return ClassificationResult(QueryIntent.COMPLEX, _COMPLEX_CONFIDENCE, remaining_rule)

    return ClassificationResult(QueryIntent.SEMANTIC, 0.75, "default_semantic")


def get_search_weights(intent: QueryIntent) -> dict:
    """Return dense/sparse weight ratios for the given intent.

    Used to tune the RRFRanker or WeightedRanker in hybrid search.

    Returns:
        dict with 'dense_weight' and 'sparse_weight' (must sum to 1.0)
    """
    weights = {
        QueryIntent.EXACT:   {"dense_weight": 0.30, "sparse_weight": 0.70},
        QueryIntent.COMPLEX: {"dense_weight": 0.70, "sparse_weight": 0.30},
        QueryIntent.SEMANTIC: {"dense_weight": 0.60, "sparse_weight": 0.40},
    }
    return weights[intent]
