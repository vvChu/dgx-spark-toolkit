"""Three-tier citation verifier for Vietnamese construction-law RAG.

Tier 0 compares document, article, and clause identifiers with regex and
returns immediately on a pure pointer or a clear numbering conflict.
Tier 1 strips the citation pointer and leaves the core technical proposition.
Tier 2 scores that proposition against the source chunk with an NLI callable.

The scorer contract is ``nli_scorer(premise, hypothesis) -> (p_entail, p_neutral, p_contra)``.
``premise`` is the chunk text. ``hypothesis`` is the extracted proposition.
Label order matches ``MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7``:
index 0 entailment, index 1 neutral, index 2 contradiction.

When no checkpoint is loaded, a hermetic token-overlap heuristic fills the
same three probabilities. It is not a calibrated substitute for mDeBERTa and
it does not consult a retrieval reranker.
"""
from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

DEFAULT_NLI_CHECKPOINT = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
NLI_LABEL_ORDER: tuple[str, str, str] = ("entailment", "neutral", "contradiction")
DEFAULT_TAU_ENTAIL = 0.75
DEFAULT_TAU_CONTRA = 0.80

NliScorer = Callable[[str, str], tuple[float, float, float]]

_NLI_LABELS = set(NLI_LABEL_ORDER)

# QCVN 06:2022/BXD, TCVN 9385:2012, QCVN 06/2022.
_STANDARD_RE = re.compile(
    r"\b(?P<family>QCVN|TCVN|TCCS|QCĐP|QCDP)\s*"
    r"(?P<num>\d+)\s*[:/]\s*(?P<year>\d{4})"
    r"(?:\s*/\s*(?P<agency>[A-Za-zĐđ]{2,12}))?",
    re.IGNORECASE | re.UNICODE,
)

# 01/2024/TT-BXD, 15/2021/NĐ-CP.
_LEGAL_FULL_RE = re.compile(
    r"\b(?P<num>\d{1,5})\s*/\s*(?P<year>\d{4})\s*/\s*"
    r"(?P<kind>NĐ|ND|TT|QĐ|QD|CV|CT|KH|BT|HD|NQ)\s*-\s*"
    r"(?P<agency>[A-Za-zĐđ0-9]{2,12})\b",
    re.IGNORECASE | re.UNICODE,
)

# "Thông tư 01/2024" has no agency suffix. Kept only when a full number did not already cover the span.
_LEGAL_PARTIAL_RE = re.compile(
    r"\b(?P<label>Thông\s+tư|Thong\s+tu|Nghị\s+định|Nghi\s+dinh|"
    r"Quyết\s+định|Quyet\s+dinh|Nghị\s+quyết|Nghi\s+quyet)"
    r"\s+(?:số\s+|so\s+)?(?P<num>\d{1,5})\s*/\s*(?P<year>\d{4})\b",
    re.IGNORECASE | re.UNICODE,
)

_ARTICLE_RE = re.compile(r"\b(?:Điều|Dieu)\s+(\d+)\b", re.IGNORECASE | re.UNICODE)
_CLAUSE_RE = re.compile(r"\b(?:khoản|khoan)\s+(\d+)\b", re.IGNORECASE | re.UNICODE)
_POINT_RE = re.compile(r"\b(?:điểm|diem)\s+([a-zđ])\b", re.IGNORECASE | re.UNICODE)
_STRUCT_RE = re.compile(
    r"\b(?:Chương|Chuong|Mục|Muc|Phần|Phan)\s+([IVXLCDM]+|\d+)\b",
    re.IGNORECASE | re.UNICODE,
)

# Comma or semicolon splits a pointer from the proposition. A colon does too,
# except the colon inside a standard number such as "QCVN 06:2022".
_CITE_SPLIT = r"(?:[,;]|:(?!\d{4}))"

_LEADING_CITE_RE = re.compile(
    r"^\s*(?:"
    r"theo\s+quy\s+định\s+(?:của\s+)?(?:tại\s+)?"
    r"|căn\s+cứ\s+(?:vào\s+|theo\s+)?(?:quy\s+định\s+(?:tại\s+)?)?"
    r"|thực\s+hiện\s+(?:nghiệm\s+thu\s+)?theo\s+(?:quy\s+định\s+(?:tại\s+)?)?"
    r"|áp\s+dụng\s+(?:theo\s+)?(?:quy\s+định\s+(?:tại\s+)?)?"
    r"|tuân\s+thủ\s+(?:theo\s+)?(?:quy\s+định\s+(?:tại\s+)?)?"
    r"|theo\s+"
    rf")(?P<cite>.+?){_CITE_SPLIT}\s*(?P<prop>\S.*)$",
    re.IGNORECASE | re.UNICODE,
)

_TRAILING_CITE_RE = re.compile(
    r"^(?P<prop>.+?)(?:\s*[,;]\s*|\s+)(?:"
    r"theo\s+quy\s+định\s+(?:của\s+)?(?:tại\s+)?"
    r"|căn\s+cứ\s+(?:vào\s+|theo\s+)?(?:quy\s+định\s+(?:tại\s+)?)?"
    r"|được\s+quy\s+định\s+tại\s+"
    r"|quy\s+định\s+tại\s+"
    r"|theo\s+"
    r")(?P<cite>(?:Điều|Dieu|khoản|khoan|điểm|diem|QCVN|TCVN|TCCS|QCĐP|QCDP|"
    r"Thông|Thong|Nghị|Nghi|Quyết|Quyet)\b.*)$",
    re.IGNORECASE | re.UNICODE,
)

_PAREN_CITE_RE = re.compile(
    r"\([^()]{0,160}(?:Điều|Dieu|khoản|khoan|QCVN|TCVN|TCCS|/TT-|/NĐ-|/QĐ-)[^()]{0,160}\)",
    re.IGNORECASE | re.UNICODE,
)

_MEASURE_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>m²|m³|m2|m3|mm|cm|km|mét|met|mpa|kpa|kg|°c|℃|%|m)\b",
    re.IGNORECASE | re.UNICODE,
)

_UNIT_ALIASES = {
    "m": "m",
    "met": "m",
    "mét": "m",
    "m2": "m2",
    "m²": "m2",
    "m3": "m3",
    "m³": "m3",
    "mm": "mm",
    "cm": "cm",
    "km": "km",
    "%": "%",
    "kg": "kg",
    "mpa": "mpa",
    "kpa": "kpa",
    "°c": "c",
    "℃": "c",
}

_LABEL_FAMILY = {
    "thong tu": "tt",
    "nghi dinh": "nd",
    "quyet dinh": "qd",
    "nghi quyet": "nq",
}

_KIND_FAMILY = {
    "nd": "nd",
    "tt": "tt",
    "qd": "qd",
    "cv": "cv",
    "ct": "ct",
    "kh": "kh",
    "bt": "bt",
    "hd": "hd",
    "nq": "nq",
}

# Citation rhetoric and document-type words. A pure pointer has none left after these are removed.
_POINTER_BOILERPLATE = {
    "thuc", "hien", "theo", "quy", "dinh", "tai", "can", "cu", "vao",
    "ap", "dung", "tuan", "thu", "xem", "nhu", "cua", "va", "van", "ban",
    "nay", "tren", "duoc", "viec", "cac", "nhung", "nghiem", "so", "ban",
    "hanh", "la", "co", "cho", "voi", "ve", "trong", "khi", "de", "thi",
    "ma", "do", "se", "da", "dang", "tu", "den", "boi", "hoac", "hay",
    "mot", "nhat", "chuan", "tieu", "thong", "nghi", "quyet", "luat",
    "bxd", "bca", "btnmt", "byt", "bct", "btc", "btp", "ubnd",
}

_CONTENT_STOPWORDS = {
    "la", "cua", "va", "cac", "mot", "nhung", "duoc", "trong", "co", "cho",
    "voi", "tai", "theo", "ve", "khi", "de", "thi", "ma", "nay", "do",
    "nhu", "se", "da", "dang", "tu", "den", "boi", "vao", "tren", "duoi",
    "hoac", "hay", "rat", "nhat", "hon", "viec", "nao", "gi", "bi", "ra",
    "len", "xuong",
}

_PROHIBIT_RE = re.compile(
    r"\b(?:cam|nghiem\s+cam|khong\s+duoc(?:\s+phep)?|khong\s+cho\s+phep|chang\s+duoc)\b",
    re.IGNORECASE | re.UNICODE,
)
_ALLOW_RE = re.compile(r"\b(?:duoc\s+phep|cho\s+phep)\b", re.IGNORECASE | re.UNICODE)


class CitationStatus(str, Enum):
    """Tri-state citation decision plus the two tier-0 terminals."""

    VERIFIED_POINTER = "verified_pointer"
    VERIFIED_ENTAILMENT = "verified_entailment"
    UNVERIFIED = "unverified"
    REJECTED_MISMATCH = "rejected_mismatch"
    REJECTED_CONTRADICTION = "rejected_contradiction"


class CitationVerificationResult(BaseModel):
    """One citation decision. ``tier`` is 0, 1, or 2. Tier 1 never decides alone."""

    model_config = ConfigDict(frozen=True)

    status: CitationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    tier: int = Field(ge=0, le=2)
    reason: str
    claim: str
    extracted_proposition: str


@dataclass(frozen=True)
class _DocRef:
    family: str
    number: str
    year: str
    agency: str | None = None

    def matches(self, other: _DocRef) -> bool:
        if self.family != other.family or self.number != other.number or self.year != other.year:
            return False
        if self.agency and other.agency and self.agency != other.agency:
            return False
        return True

    def label(self) -> str:
        agency = f"/{self.agency}" if self.agency else ""
        return f"{self.family} {self.number}:{self.year}{agency}"


def nli_probs_from_logits(
    logits: Sequence[float],
    label_order: Sequence[str] = NLI_LABEL_ORDER,
) -> tuple[float, float, float]:
    """Softmax a 3-way logit vector into ``(p_entail, p_neutral, p_contra)``.

    The default order is the mDeBERTa XNLI checkpoint order. Pass the
    checkpoint's own ``id2label`` sequence when it differs.
    """
    if len(logits) != 3 or len(label_order) != 3:
        raise ValueError("NLI logits and label_order must each have length 3")
    if set(label_order) != _NLI_LABELS:
        raise ValueError("label_order must be a permutation of entailment, neutral, contradiction")
    values = [float(item) for item in logits]
    if not all(math.isfinite(item) for item in values):
        raise ValueError("NLI logits must be finite")
    peak = max(values)
    exps = [math.exp(item - peak) for item in values]
    total = sum(exps)
    by_label = {label: exps[index] / total for index, label in enumerate(label_order)}
    return (by_label["entailment"], by_label["neutral"], by_label["contradiction"])


def _squash(text: str | None) -> str:
    normalized = unicodedata.normalize("NFC", text or "")
    normalized = normalized.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _fold(text: str) -> str:
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return stripped.replace("đ", "d")


def _norm_int_token(value: str) -> str:
    text = value.strip().lstrip("0")
    return text or "0"


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < stop and end > begin for begin, stop in occupied)


def _parse_doc_refs(text: str) -> list[_DocRef]:
    if not text:
        return []
    refs: list[_DocRef] = []
    occupied: list[tuple[int, int]] = []

    for match in _STANDARD_RE.finditer(text):
        agency = match.group("agency")
        refs.append(_DocRef(
            family=_fold(match.group("family")),
            number=_norm_int_token(match.group("num")),
            year=match.group("year"),
            agency=_fold(agency) if agency else None,
        ))
        occupied.append(match.span())

    for match in _LEGAL_FULL_RE.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        kind = _KIND_FAMILY.get(_fold(match.group("kind")))
        if kind is None:
            continue
        refs.append(_DocRef(
            family=kind,
            number=_norm_int_token(match.group("num")),
            year=match.group("year"),
            agency=_fold(match.group("agency")),
        ))
        occupied.append(match.span())

    for match in _LEGAL_PARTIAL_RE.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        label = re.sub(r"\s+", " ", _fold(match.group("label")))
        family = _LABEL_FAMILY.get(label)
        if family is None:
            continue
        refs.append(_DocRef(
            family=family,
            number=_norm_int_token(match.group("num")),
            year=match.group("year"),
            agency=None,
        ))
    return refs


def _chunk_doc_refs(chunk: dict[str, Any]) -> list[_DocRef]:
    """Prefer ``doc_number``. Hierarchy is only a fallback when that field does not parse.

    A hierarchy title can mention a related document. Unioning both sources would
    hide a real document-number conflict.
    """
    primary = _parse_doc_refs(_squash(_as_text(chunk.get("doc_number"))))
    if primary:
        return primary
    return _parse_doc_refs(_squash(_as_text(chunk.get("hierarchy_path"))))


def _all_nums(pattern: re.Pattern[str], text: str) -> set[str]:
    return {_norm_int_token(item) for item in pattern.findall(text)}


def _last_num(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.findall(text)
    if not found:
        return None
    return _norm_int_token(found[-1])


def _all_points(text: str) -> set[str]:
    return {_fold(item) for item in _POINT_RE.findall(text)}


def _last_point(text: str) -> str | None:
    found = _POINT_RE.findall(text)
    if not found:
        return None
    return _fold(found[-1])


def _strip_identifiers(text: str) -> str:
    stripped = text
    for pattern in (_STANDARD_RE, _LEGAL_FULL_RE, _LEGAL_PARTIAL_RE, _ARTICLE_RE, _CLAUSE_RE, _POINT_RE, _STRUCT_RE):
        stripped = pattern.sub(" ", stripped)
    return stripped


def _substantive_tokens(text: str) -> list[str]:
    folded = _fold(_strip_identifiers(text))
    folded = re.sub(r"[^a-z0-9]+", " ", folded)
    tokens: list[str] = []
    for token in folded.split():
        if len(token) <= 1 or token in _POINTER_BOILERPLATE:
            continue
        tokens.append(token)
    return tokens


def _has_legal_identifier(text: str) -> bool:
    return bool(
        _ARTICLE_RE.search(text)
        or _CLAUSE_RE.search(text)
        or _POINT_RE.search(text)
        or _parse_doc_refs(text)
    )


def _is_pure_pointer(text: str) -> bool:
    """True when the claim only points at a provision and states no technical obligation."""
    if not _has_legal_identifier(text):
        return False
    return not _substantive_tokens(text)


def _content_tokens(text: str) -> set[str]:
    folded = _fold(_squash(text))
    folded = re.sub(r"[^a-z0-9%]+", " ", folded)
    return {token for token in folded.split() if len(token) > 1 and token not in _CONTENT_STOPWORDS}


def _norm_measure(raw: str) -> str:
    value = float(raw.replace(",", "."))
    if value.is_integer():
        return str(int(value))
    return format(value, "g")


def _measures(text: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for match in _MEASURE_RE.finditer(text or ""):
        unit = _UNIT_ALIASES.get(match.group("unit").lower(), match.group("unit").lower())
        found.setdefault(unit, set()).add(_norm_measure(match.group("num")))
    return found


def _measure_relation(premise: str, hypothesis: str) -> str:
    """Return ``conflict``, ``unsupported``, or ``ok`` for unit-bearing numbers.

    A conflict is the same unit with disjoint values (50 m against 75 m).
    A number the premise never states is unsupported, which stays unverified
    rather than a contradiction.
    """
    premise_measures = _measures(premise)
    hypothesis_measures = _measures(hypothesis)
    unsupported = False
    for unit, hypothesis_values in hypothesis_measures.items():
        premise_values = premise_measures.get(unit)
        if not premise_values:
            unsupported = True
            continue
        if hypothesis_values.isdisjoint(premise_values):
            return "conflict"
    if unsupported:
        return "unsupported"
    return "ok"


def _polarity(text: str) -> int:
    """-1 prohibition, +1 explicit permission, 0 otherwise.

    ``không quá`` / ``không vượt quá`` are limits, not prohibitions, and do not match.
    """
    folded = _fold(text)
    if _PROHIBIT_RE.search(folded):
        return -1
    if _ALLOW_RE.search(folded):
        return 1
    return 0


def _recall(hypothesis_tokens: set[str], premise_tokens: set[str]) -> float:
    if not hypothesis_tokens:
        return 0.0
    return len(hypothesis_tokens & premise_tokens) / len(hypothesis_tokens)


def _overlap_entails(hypothesis_tokens: set[str], premise_tokens: set[str]) -> bool:
    if _recall(hypothesis_tokens, premise_tokens) < 0.80:
        return False
    if len(hypothesis_tokens) >= 4:
        return True
    # A two-word fragment inside a long article is not an entailment.
    return len(hypothesis_tokens) >= 2 and len(premise_tokens) <= len(hypothesis_tokens) + 3


def heuristic_nli_scores(premise: str, hypothesis: str) -> tuple[float, float, float]:
    """Hermetic stand-in for a 3-way NLI head.

    Returns probabilities that already sit on the tri-state side of the default
    thresholds for numeric opposition, permission/prohibition flips, high overlap,
    and low overlap. Partial overlap stays below both thresholds.
    """
    hypothesis_text = _squash(hypothesis)
    premise_text = _squash(premise)
    if not hypothesis_text:
        return (0.05, 0.90, 0.05)

    relation = _measure_relation(premise_text, hypothesis_text)
    hypothesis_tokens = _content_tokens(hypothesis_text)
    premise_tokens = _content_tokens(premise_text)
    recall = _recall(hypothesis_tokens, premise_tokens)
    premise_polarity = _polarity(premise_text)
    hypothesis_polarity = _polarity(hypothesis_text)
    polarity_conflict = (
        premise_polarity != 0
        and hypothesis_polarity != 0
        and premise_polarity != hypothesis_polarity
        and recall >= 0.50
    )

    if relation == "conflict" or polarity_conflict:
        return (0.04, 0.08, 0.88)
    if relation == "unsupported":
        return (0.18, 0.74, 0.08)
    if _overlap_entails(hypothesis_tokens, premise_tokens):
        entail = min(0.95, 0.78 + 0.17 * recall)
        contra = 0.03
        neutral = max(0.0, 1.0 - entail - contra)
        return (entail, neutral, contra)
    if recall < 0.35:
        return (0.12, 0.80, 0.08)
    entail = 0.35 + 0.35 * recall
    contra = 0.08
    neutral = max(0.0, 1.0 - entail - contra)
    return (entail, neutral, contra)


def _fmt_refs(refs: Sequence[_DocRef]) -> str:
    if not refs:
        return "-"
    return ", ".join(ref.label() for ref in refs)


class CitationVerifier:
    """Verify one LLM citation against one retrieved chunk.

    ``nli_scorer`` receives ``(chunk_text, proposition)`` and returns
    ``(p_entail, p_neutral, p_contra)``. ``None`` selects :func:`heuristic_nli_scores`.
    Contradiction is decided before entailment, so a score that clears both
    thresholds is ``REJECTED_CONTRADICTION``.
    """

    def __init__(
        self,
        nli_scorer: NliScorer | None = None,
        tau_entail: float = DEFAULT_TAU_ENTAIL,
        tau_contra: float = DEFAULT_TAU_CONTRA,
    ) -> None:
        if nli_scorer is not None and not callable(nli_scorer):
            raise TypeError("nli_scorer must be callable or None")
        if not 0.0 <= tau_entail <= 1.0:
            raise ValueError("tau_entail must be between 0 and 1")
        if not 0.0 <= tau_contra <= 1.0:
            raise ValueError("tau_contra must be between 0 and 1")
        self.nli_scorer = nli_scorer
        self.tau_entail = tau_entail
        self.tau_contra = tau_contra

    def check_tier0(self, claim: str, chunk: dict[str, Any]) -> CitationVerificationResult | None:
        """Return a terminal tier-0 decision, or ``None`` when tier 2 must run.

        A clear conflict is a document, article, clause, or point that both
        sides state and that does not agree. A pure pointer is verified only
        when every identifier the claim states is confirmed by the chunk.
        """
        claim_text = _squash(claim)
        chunk = chunk or {}
        hierarchy = _squash(_as_text(chunk.get("hierarchy_path")))
        claim_refs = _parse_doc_refs(claim_text)
        chunk_refs = _chunk_doc_refs(chunk)
        claim_articles = _all_nums(_ARTICLE_RE, claim_text)
        chunk_article = _last_num(_ARTICLE_RE, hierarchy)
        claim_clauses = _all_nums(_CLAUSE_RE, claim_text)
        chunk_clause = _last_num(_CLAUSE_RE, hierarchy)
        claim_points = _all_points(claim_text)
        chunk_point = _last_point(hierarchy)

        conflicts: list[str] = []
        doc_matches = bool(
            claim_refs
            and chunk_refs
            and any(left.matches(right) for left in claim_refs for right in chunk_refs)
        )
        if claim_refs and chunk_refs and not doc_matches:
            conflicts.append(f"doc_number claim [{_fmt_refs(claim_refs)}] vs chunk [{_fmt_refs(chunk_refs)}]")
        if claim_articles and chunk_article and chunk_article not in claim_articles:
            claim_article_label = ", ".join(sorted(claim_articles, key=int))
            conflicts.append(f"article claim {claim_article_label} vs chunk {chunk_article}")
        if claim_clauses and chunk_clause and chunk_clause not in claim_clauses:
            claim_clause_label = ", ".join(sorted(claim_clauses, key=int))
            conflicts.append(f"clause claim {claim_clause_label} vs chunk {chunk_clause}")
        if claim_points and chunk_point and chunk_point not in claim_points:
            conflicts.append(f"point claim {', '.join(sorted(claim_points))} vs chunk {chunk_point}")

        pointer = _is_pure_pointer(claim_text)
        if conflicts:
            proposition = "" if pointer else self.extract_tier1_proposition(claim_text)
            reason = "tier0 mismatch: " + "; ".join(conflicts)
            logger.debug("[CitationVerifier] %s", reason)
            return self._result(
                CitationStatus.REJECTED_MISMATCH,
                1.0,
                0,
                reason,
                claim_text,
                proposition,
            )

        # A pure pointer never reaches NLI. An empty proposition would make the
        # entailment head score the citation label instead of a technical claim.
        if pointer:
            gaps = _unconfirmed_pointer_fields(
                claim_articles,
                chunk_article,
                claim_clauses,
                chunk_clause,
                claim_points,
                chunk_point,
                claim_refs,
                doc_matches,
            )
            if not gaps:
                reason = (
                    "tier0 pointer: "
                    f"doc={_fmt_refs(chunk_refs)} article={chunk_article or '-'} "
                    f"clause={chunk_clause or '-'}"
                )
                logger.debug("[CitationVerifier] %s", reason)
                return self._result(CitationStatus.VERIFIED_POINTER, 1.0, 0, reason, claim_text, "")
            reason = "tier0 pointer incomplete: " + ", ".join(gaps)
            logger.debug("[CitationVerifier] %s", reason)
            return self._result(CitationStatus.UNVERIFIED, 0.5, 0, reason, claim_text, "")
        return None

    def extract_tier1_proposition(self, claim: str) -> str:
        """Drop leading or trailing citation pointers and keep the core proposition.

        A pure pointer has no core proposition, so the result is an empty string.
        """
        text = _squash(claim)
        if not text or _is_pure_pointer(text):
            return ""
        for _ in range(3):
            match = _LEADING_CITE_RE.match(text)
            if match is None or not _has_legal_identifier(match.group("cite")):
                break
            text = match.group("prop").strip()
        trailing = _TRAILING_CITE_RE.match(text)
        if trailing is not None and _has_legal_identifier(trailing.group("cite")):
            candidate = trailing.group("prop").strip(" ,;")
            if candidate and _substantive_tokens(candidate):
                text = candidate
        text = _PAREN_CITE_RE.sub(" ", text)
        text = _squash(text).strip(" ,;:-")
        if text.endswith("."):
            text = text[:-1].rstrip()
        return text

    def check_tier2_nli(self, proposition: str, chunk_text: str) -> CitationVerificationResult:
        """Apply the tri-state policy to one proposition / chunk pair.

        ``P_contra >= tau_contra`` rejects. Else ``P_entail >= tau_entail`` verifies.
        The open interval between the two thresholds stays ``UNVERIFIED`` and the
        citation is kept for an engineer to read.
        """
        p_entail, p_neutral, p_contra = self._score(chunk_text, proposition)
        source = "nli" if self.nli_scorer is not None else "heuristic"
        if p_contra >= self.tau_contra:
            status = CitationStatus.REJECTED_CONTRADICTION
            confidence = p_contra
            reason = f"tier2 {source} contradiction: P_contra={p_contra:.3f} >= {self.tau_contra:.2f}"
        elif p_entail >= self.tau_entail:
            status = CitationStatus.VERIFIED_ENTAILMENT
            confidence = p_entail
            reason = f"tier2 {source} entailment: P_entail={p_entail:.3f} >= {self.tau_entail:.2f}"
        else:
            status = CitationStatus.UNVERIFIED
            confidence = p_neutral
            reason = (
                f"tier2 {source} unverified: "
                f"P_entail={p_entail:.3f} P_neutral={p_neutral:.3f} P_contra={p_contra:.3f}"
            )
        logger.debug("[CitationVerifier] %s", reason)
        return self._result(status, confidence, 2, reason, proposition, proposition)

    def verify_citation(self, claim: str, chunk: dict[str, Any]) -> CitationVerificationResult:
        """Run tier 0, then tier 1 extraction, then tier 2. Tier 0 does not call NLI."""
        claim_text = _squash(claim)
        chunk = chunk or {}
        tier0 = self.check_tier0(claim_text, chunk)
        if tier0 is not None:
            return tier0
        proposition = self.extract_tier1_proposition(claim_text)
        result = self.check_tier2_nli(proposition, self._chunk_text(chunk))
        return result.model_copy(update={"claim": claim_text, "extracted_proposition": proposition})

    def verify_citations_batch(
        self,
        citations: list[tuple[str, dict[str, Any]]],
    ) -> list[CitationVerificationResult]:
        """Verify citations in input order. Each pair is independent."""
        return [self.verify_citation(claim, chunk) for claim, chunk in citations]

    def _score(self, premise: str, hypothesis: str) -> tuple[float, float, float]:
        if self.nli_scorer is None:
            return heuristic_nli_scores(premise, hypothesis)
        raw = self.nli_scorer(premise, hypothesis)
        if not isinstance(raw, (tuple, list)) or len(raw) != 3:
            raise ValueError("nli_scorer must return (p_entail, p_neutral, p_contra)")
        probs: list[float] = []
        for value in raw:
            number = float(value)
            if not math.isfinite(number) or number < 0.0 or number > 1.0:
                raise ValueError("nli_scorer values must be finite probabilities in [0, 1]")
            probs.append(number)
        return (probs[0], probs[1], probs[2])

    @staticmethod
    def _chunk_text(chunk: dict[str, Any]) -> str:
        for key in ("text", "content", "chunk_text"):
            value = chunk.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    @staticmethod
    def _result(
        status: CitationStatus,
        confidence: float,
        tier: int,
        reason: str,
        claim: str,
        extracted_proposition: str,
    ) -> CitationVerificationResult:
        return CitationVerificationResult(
            status=status,
            confidence=confidence,
            tier=tier,
            reason=reason,
            claim=claim,
            extracted_proposition=extracted_proposition,
        )


def _unconfirmed_pointer_fields(
    claim_articles: set[str],
    chunk_article: str | None,
    claim_clauses: set[str],
    chunk_clause: str | None,
    claim_points: set[str],
    chunk_point: str | None,
    claim_refs: Sequence[_DocRef],
    doc_matches: bool,
) -> list[str]:
    """Identifiers the pointer names that the chunk metadata does not confirm.

    An empty list means the pointer is confirmed. A conflict is handled before
    this function runs, so a gap here is missing metadata rather than a clash.
    """
    gaps: list[str] = []
    if not claim_articles and not claim_clauses and not claim_points and not claim_refs:
        return ["identifier"]
    if claim_articles and (chunk_article is None or chunk_article not in claim_articles):
        gaps.append("article " + ", ".join(sorted(claim_articles, key=int)))
    if claim_clauses and (chunk_clause is None or chunk_clause not in claim_clauses):
        gaps.append("clause " + ", ".join(sorted(claim_clauses, key=int)))
    if claim_points and (chunk_point is None or chunk_point not in claim_points):
        gaps.append("point " + ", ".join(sorted(claim_points)))
    if claim_refs and not doc_matches:
        gaps.append("doc_number " + _fmt_refs(claim_refs))
    return gaps
