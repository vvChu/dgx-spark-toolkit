"""Hermetic tests for the three-tier citation verifier.

Tier 0 must accept a pure pointer and reject a clear numbering conflict
without calling the NLI scorer. Tier 2 applies the tri-state thresholds to
an injected scorer. The heuristic path is covered separately and does not
load a GPU checkpoint.
"""
import pytest

from retrieval.citation_verifier import (
    CitationStatus,
    CitationVerifier,
    heuristic_nli_scores,
    nli_probs_from_logits,
)


def _chunk(doc_number: str, hierarchy_path: str, text: str = "") -> dict:
    return {
        "doc_number": doc_number,
        "hierarchy_path": hierarchy_path,
        "text": text,
    }


def _boom_scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
    raise AssertionError(f"NLI must not run for tier 0 ({hypothesis!r})")


def test_tier0_pure_pointer_matches_doc_and_article():
    verifier = CitationVerifier(nli_scorer=_boom_scorer)
    result = verifier.verify_citation(
        "thực hiện theo quy định tại Điều 12 QCVN 06:2022/BXD",
        _chunk(
            "QCVN 06:2022/BXD",
            "[qcvn_06_2022_bxd] -> [Chương II] -> [Điều 12. An toàn cháy]",
            "Nội dung điều 12 về khoảng cách an toàn cháy.",
        ),
    )
    assert result.status == CitationStatus.VERIFIED_POINTER
    assert result.tier == 0
    assert result.confidence == 1.0
    assert result.extracted_proposition == ""


def test_tier0_article_mismatch_rejected():
    verifier = CitationVerifier(nli_scorer=_boom_scorer)
    result = verifier.verify_citation(
        "Theo Điều 15 QCVN 06:2022",
        _chunk(
            "QCVN 06:2022",
            "[qcvn_06_2022] -> [Điều 4. Giải thích từ ngữ]",
            "Điều 4 giải thích các thuật ngữ.",
        ),
    )
    assert result.status == CitationStatus.REJECTED_MISMATCH
    assert result.tier == 0
    assert result.confidence == 1.0
    assert "article" in result.reason
    assert "15" in result.reason
    assert "4" in result.reason


def test_tier1_proposition_extraction():
    proposition = CitationVerifier().extract_tier1_proposition(
        "Theo Điều 5 Thông tư 01/2024, chiều cao công trình tối đa là 50m"
    )
    assert proposition == "chiều cao công trình tối đa là 50m"


def test_tier2_entailment_verified():
    seen: list[tuple[str, str]] = []

    def scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
        seen.append((premise, hypothesis))
        return (0.91, 0.05, 0.04)

    verifier = CitationVerifier(nli_scorer=scorer)
    claim = "Theo Điều 12 QCVN 06:2022, chiều cao công trình tối đa là 50m"
    chunk = _chunk(
        "QCVN 06:2022/BXD",
        "[Điều 12]",
        "Chiều cao công trình tối đa là 50 m.",
    )
    result = verifier.verify_citation(claim, chunk)
    assert result.status == CitationStatus.VERIFIED_ENTAILMENT
    assert result.tier == 2
    assert result.confidence == pytest.approx(0.91)
    assert result.extracted_proposition == "chiều cao công trình tối đa là 50m"
    assert seen == [(chunk["text"], "chiều cao công trình tối đa là 50m")]


def test_tier2_contradiction_rejected():
    def scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
        return (0.05, 0.05, 0.90)

    result = CitationVerifier(nli_scorer=scorer).verify_citation(
        "chiều cao công trình tối đa là 75m",
        _chunk("QCVN 06:2022/BXD", "[Điều 4]", "Chiều cao công trình tối đa là 50 m."),
    )
    assert result.status == CitationStatus.REJECTED_CONTRADICTION
    assert result.tier == 2
    assert result.confidence == pytest.approx(0.90)


def test_tier2_uncertain_keeps_unverified():
    def scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
        return (0.22, 0.70, 0.08)

    result = CitationVerifier(nli_scorer=scorer).verify_citation(
        "hệ thống chữa cháy tự động là bắt buộc với nhà ở liền kề",
        _chunk("QCVN 06:2022/BXD", "[Điều 12]", "Khoảng cách từ công trình đến đường giao thông."),
    )
    assert result.status == CitationStatus.UNVERIFIED
    assert result.tier == 2
    assert result.confidence == pytest.approx(0.70)
    assert result.claim.startswith("hệ thống chữa cháy")


def test_batch_verification_mixed():
    calls: list[str] = []

    def scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
        calls.append(hypothesis)
        if "50m" in hypothesis:
            return (0.91, 0.05, 0.04)
        if "chữa cháy" in hypothesis:
            return (0.22, 0.70, 0.08)
        raise AssertionError(f"unexpected NLI hypothesis: {hypothesis!r}")

    pointer_chunk = _chunk("QCVN 06:2022/BXD", "[Chương II] -> [Điều 12]")
    mismatch_chunk = _chunk("QCVN 06:2022/BXD", "[Điều 4]")
    article_chunk = _chunk(
        "QCVN 06:2022/BXD",
        "[Điều 12]",
        "Chiều cao công trình tối đa là 50 m.",
    )
    citations = [
        ("thực hiện theo quy định tại Điều 12 QCVN 06:2022/BXD", pointer_chunk),
        ("Theo Điều 15 QCVN 06:2022", mismatch_chunk),
        ("Theo Điều 12 QCVN 06:2022, chiều cao công trình tối đa là 50m", article_chunk),
        ("Theo Điều 12 QCVN 06:2022, hệ thống chữa cháy tự động là bắt buộc", article_chunk),
    ]
    results = CitationVerifier(nli_scorer=scorer).verify_citations_batch(citations)
    assert [item.status for item in results] == [
        CitationStatus.VERIFIED_POINTER,
        CitationStatus.REJECTED_MISMATCH,
        CitationStatus.VERIFIED_ENTAILMENT,
        CitationStatus.UNVERIFIED,
    ]
    assert [item.tier for item in results] == [0, 0, 2, 2]
    assert calls == [
        "chiều cao công trình tối đa là 50m",
        "hệ thống chữa cháy tự động là bắt buộc",
    ]


def test_substantive_mismatch_stays_on_tier0():
    def scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
        raise AssertionError("a wrong article must not reach NLI")

    result = CitationVerifier(nli_scorer=scorer).verify_citation(
        "Theo Điều 15 QCVN 06:2022, chiều cao công trình tối đa là 50m",
        _chunk("QCVN 06:2022/BXD", "[Điều 4]", "Chiều cao công trình tối đa là 50 m."),
    )
    assert result.status == CitationStatus.REJECTED_MISMATCH
    assert result.tier == 0
    assert result.extracted_proposition == "chiều cao công trình tối đa là 50m"


def test_tier0_doc_number_mismatch_rejected():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo quy định tại Điều 12 QCVN 07:2022/BXD",
        _chunk("QCVN 06:2022/BXD", "[Điều 12]"),
    )
    assert result.status == CitationStatus.REJECTED_MISMATCH
    assert result.tier == 0
    assert "doc_number" in result.reason


def test_tier0_pointer_matches_article_and_clause():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo khoản 3 Điều 12 QCVN 06:2022/BXD",
        _chunk("QCVN 06:2022/BXD", "[Điều 12] -> [Khoản 3]"),
    )
    assert result.status == CitationStatus.VERIFIED_POINTER
    assert result.tier == 0


def test_tier0_clause_mismatch_rejected():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo khoản 3 Điều 12 QCVN 06:2022/BXD",
        _chunk("QCVN 06:2022/BXD", "[Điều 12] -> [Khoản 1]"),
    )
    assert result.status == CitationStatus.REJECTED_MISMATCH
    assert "clause" in result.reason


def test_tier0_pointer_matches_when_agency_suffix_is_only_on_one_side():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo quy định tại Điều 12 QCVN 06:2022",
        _chunk("QCVN 06:2022/BXD", "[Điều 12]"),
    )
    assert result.status == CitationStatus.VERIFIED_POINTER
    assert result.tier == 0


def test_tier0_zero_padded_standard_number_matches():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo quy định tại Điều 12 QCVN 6:2022/BXD",
        _chunk("QCVN 06:2022/BXD", "[Điều 12]"),
    )
    assert result.status == CitationStatus.VERIFIED_POINTER


def test_pure_pointer_with_missing_clause_does_not_call_nli():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo khoản 3 Điều 12 QCVN 06:2022/BXD",
        _chunk("QCVN 06:2022/BXD", "[Điều 12. An toàn cháy]"),
    )
    assert result.status == CitationStatus.UNVERIFIED
    assert result.tier == 0
    assert result.confidence == 0.5
    assert "clause" in result.reason
    assert result.extracted_proposition == ""


def test_tier0_agency_mismatch_rejected():
    result = CitationVerifier(nli_scorer=_boom_scorer).verify_citation(
        "thực hiện theo quy định tại Điều 12 QCVN 06:2022/BCA",
        _chunk("QCVN 06:2022/BXD", "[Điều 12]"),
    )
    assert result.status == CitationStatus.REJECTED_MISMATCH
    assert result.tier == 0
    assert "doc_number" in result.reason


def test_tier0_substantive_claim_falls_through():
    claim = "Theo Điều 5 Thông tư 01/2024, chiều cao công trình tối đa là 50m"
    chunk = _chunk("01/2024/TT-BXD", "[Điều 5. Chiều cao]", "Chiều cao công trình tối đa là 50 m.")
    assert CitationVerifier().check_tier0(claim, chunk) is None


def test_tier1_strips_can_cu_and_trailing_citation():
    verifier = CitationVerifier()
    assert verifier.extract_tier1_proposition(
        "Căn cứ khoản 3 Điều 4, chiều cao công trình tối đa là 50m"
    ) == "chiều cao công trình tối đa là 50m"
    assert verifier.extract_tier1_proposition(
        "chiều cao công trình tối đa là 50m theo Điều 5 Thông tư 01/2024"
    ) == "chiều cao công trình tối đa là 50m"


def test_tier2_contradiction_wins_when_both_thresholds_fire():
    def scorer(premise: str, hypothesis: str) -> tuple[float, float, float]:
        return (0.90, 0.0, 0.80)

    result = CitationVerifier(nli_scorer=scorer).check_tier2_nli(
        "chiều cao công trình tối đa là 75m",
        "Chiều cao công trình tối đa là 50 m.",
    )
    assert result.status == CitationStatus.REJECTED_CONTRADICTION
    assert result.tier == 2


def test_tier2_thresholds_are_inclusive():
    verifier = CitationVerifier()

    def entail(premise: str, hypothesis: str) -> tuple[float, float, float]:
        return (0.75, 0.25, 0.0)

    def just_under(premise: str, hypothesis: str) -> tuple[float, float, float]:
        return (0.749, 0.251, 0.0)

    def contra(premise: str, hypothesis: str) -> tuple[float, float, float]:
        return (0.10, 0.10, 0.80)

    assert CitationVerifier(nli_scorer=entail).check_tier2_nli("a", "b").status == CitationStatus.VERIFIED_ENTAILMENT
    assert CitationVerifier(nli_scorer=just_under).check_tier2_nli("a", "b").status == CitationStatus.UNVERIFIED
    assert CitationVerifier(nli_scorer=contra).check_tier2_nli("a", "b").status == CitationStatus.REJECTED_CONTRADICTION
    assert verifier.tau_entail == 0.75
    assert verifier.tau_contra == 0.80


def test_heuristic_numeric_contradiction():
    result = CitationVerifier().verify_citation(
        "chiều cao công trình tối đa là 75m",
        _chunk("QCVN 06:2022/BXD", "[Điều 4]", "Chiều cao công trình tối đa là 50 m."),
    )
    assert result.status == CitationStatus.REJECTED_CONTRADICTION
    assert result.tier == 2
    assert "heuristic" in result.reason


def test_heuristic_overlap_entailment():
    result = CitationVerifier().verify_citation(
        "chiều cao công trình tối đa là 50m",
        _chunk("QCVN 06:2022/BXD", "[Điều 4]", "Chiều cao công trình tối đa là 50 m."),
    )
    assert result.status == CitationStatus.VERIFIED_ENTAILMENT
    assert result.tier == 2
    assert "heuristic" in result.reason


def test_heuristic_low_overlap_unverified():
    result = CitationVerifier().verify_citation(
        "cường độ chịu nén của bê tông móng cọc",
        _chunk("QCVN 06:2022/BXD", "[Điều 12]", "Lối thoát nạn phải được bố trí liên tục đến ngoài nhà."),
    )
    assert result.status == CitationStatus.UNVERIFIED
    assert result.tier == 2


def test_heuristic_prohibition_versus_permission():
    scores = heuristic_nli_scores(
        "Nghiêm cấm sử dụng vật liệu cháy nhóm A.",
        "được phép sử dụng vật liệu cháy nhóm A",
    )
    assert scores[2] >= 0.80
    result = CitationVerifier().check_tier2_nli(
        "được phép sử dụng vật liệu cháy nhóm A",
        "Nghiêm cấm sử dụng vật liệu cháy nhóm A.",
    )
    assert result.status == CitationStatus.REJECTED_CONTRADICTION


def test_nli_probs_from_logits_default_and_custom_order():
    entail, neutral, contra = nli_probs_from_logits([5.0, 0.0, 0.0])
    assert entail > 0.90
    assert neutral < 0.05
    assert contra < 0.05
    assert entail + neutral + contra == pytest.approx(1.0)

    remapped_entail, remapped_neutral, remapped_contra = nli_probs_from_logits(
        [5.0, 0.0, 0.0],
        label_order=("contradiction", "neutral", "entailment"),
    )
    assert remapped_contra > 0.90
    assert remapped_entail < 0.05
    assert remapped_neutral < 0.05


def test_batch_empty_and_bad_scorer_contract():
    assert CitationVerifier().verify_citations_batch([]) == []

    def bad_shape(premise: str, hypothesis: str) -> tuple[float, float]:
        return (0.5, 0.5)

    with pytest.raises(ValueError, match="p_entail"):
        CitationVerifier(nli_scorer=bad_shape).check_tier2_nli("mệnh đề", "nguồn")


def test_tau_and_scorer_type_are_validated():
    with pytest.raises(ValueError):
        CitationVerifier(tau_entail=1.5)
    with pytest.raises(ValueError):
        CitationVerifier(tau_contra=-0.1)
    with pytest.raises(TypeError):
        CitationVerifier(nli_scorer="mdeberta")  # type: ignore[arg-type]
