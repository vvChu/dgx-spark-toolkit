"""Query Intent Classifier — routes queries to the most appropriate retrieval strategy.

Three strategies:
    EXACT   → BM25-first (sparse-heavy): doc numbers, article references, code lookup
    COMPLEX → AgenticRetriever (multi-hop): comparisons, cross-law analysis, timelines
    SEMANTIC → Standard hybrid search (default): semantic questions about legal content

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


# ── Pattern sets ──────────────────────────────────────────────────────────────

# EXACT: doc numbers, article/clause references, code lookups
_EXACT_PATTERNS = [
    # Vietnamese legal document numbers WITH year: 87/2023/NĐ-CP, 16/2025/TT-BXD, 1417/QĐ-TTg
    (re.compile(
        r'\b\d{1,5}/\d{4}/(?:NĐ|TT|QĐ|CV|CT|KH|BT|HD|NQ)-[A-ZĐa-z]{2,10}\b',
        re.UNICODE
    ), "doc_number_with_year"),
    # Vietnamese legal document numbers WITHOUT year: 1417/QĐ-TTg, 2345/QĐ-BXD
    (re.compile(
        r'\b\d{1,5}/(?:QĐ|NQ|CT|CV)-[A-ZĐa-z]{2,10}\b',
        re.UNICODE
    ), "doc_number_no_year"),
    # Article references: Điều 15, khoản 3, điểm a
    (re.compile(
        r'\b(?:Điều|Khoản|Điểm|Chương|Mục|Phần)\s+\d+\b',
        re.IGNORECASE | re.UNICODE
    ), "article_reference"),
    # Technical standard numbers: QCVN 06:2022, TCVN 1234:2020, TCCS 001:2024
    (re.compile(
        r'\b(?:QCVN|TCVN|TCCS|QCĐP)\s+\d+[:/]\d{4}\b',
        re.IGNORECASE
    ), "technical_standard_code"),
    # Exact section titles in quotes
    (re.compile(r'"[^"]{5,80}"'), "quoted_exact_term"),
]

# COMPLEX: comparison, timeline, amendment analysis
_COMPLEX_PATTERNS = [
    (re.compile(
        r'\b(?:so sánh|khác nhau|giống nhau|phân biệt)\b',
        re.IGNORECASE | re.UNICODE
    ), "comparison_keyword"),
    (re.compile(
        r'\b(?:thay thế|sửa đổi|bổ sung|ban hành mới|còn hiệu lực|hết hiệu lực)\b',
        re.IGNORECASE | re.UNICODE
    ), "amendment_keyword"),
    (re.compile(
        r'\b(?:trước|sau|từ năm|đến năm|lịch sử|timeline|tiến trình)\b',
        re.IGNORECASE | re.UNICODE
    ), "timeline_keyword"),
    (re.compile(
        r'\b(?:mâu thuẫn|xung đột|không nhất quán|chồng chéo)\b',
        re.IGNORECASE | re.UNICODE
    ), "conflict_keyword"),
    # Multiple doc references in same query
    (re.compile(
        r'\b\d{1,5}/\d{4}/[A-ZĐ\-]+\b.*\b\d{1,5}/\d{4}/[A-ZĐ\-]+\b',
        re.UNICODE
    ), "multiple_doc_refs"),
]


def classify_query(query: str) -> ClassificationResult:
    """Classify a query into EXACT, COMPLEX, or SEMANTIC intent.

    Uses regex pattern matching only — zero LLM latency overhead.
    Bias toward EXACT for precision-critical legal lookups.

    Returns:
        ClassificationResult with intent, confidence, and matched rule name.
    """
    if not query or not query.strip():
        return ClassificationResult(QueryIntent.SEMANTIC, 0.5, "empty_query")

    q = query.strip()

    # Check EXACT first (highest precision for legal queries)
    for pattern, rule_name in _EXACT_PATTERNS:
        if pattern.search(q):
            logger.debug(f"[QueryClassifier] EXACT match via '{rule_name}': {q[:60]}")
            return ClassificationResult(QueryIntent.EXACT, 0.90, rule_name)

    # Check COMPLEX patterns (multi-document analysis)
    complex_matches = []
    for pattern, rule_name in _COMPLEX_PATTERNS:
        if pattern.search(q):
            complex_matches.append(rule_name)

    if complex_matches:
        confidence = min(0.95, 0.70 + len(complex_matches) * 0.08)
        rule = complex_matches[0]
        logger.debug(f"[QueryClassifier] COMPLEX match via {complex_matches}: {q[:60]}")
        return ClassificationResult(QueryIntent.COMPLEX, confidence, rule)

    # Default: semantic search
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
