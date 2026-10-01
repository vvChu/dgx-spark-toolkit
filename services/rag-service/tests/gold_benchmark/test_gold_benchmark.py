"""Automated Pytest Gate for OKF Gold Benchmark Suite (50 Questions).
=============================================================================
Enforces ADR-0058: Hard Completion Lock.
All 50 statutory ground-truth test cases across all 7 categories must achieve
100% accuracy before any pull request or deployment is approved.

Categories:
1. Scope Gate & Exclusions (Mục 1.1.3, Mục 1.1.2)
2. Normative Force (QCVN vs TCVN vs Contract)
3. Temporal Edition (2022 vs SĐ1:2023 vs SĐ01:2026 vs Luật 2025)
4. Table 4 REI Ratings & Footnotes 1, 2, 3
5. Table 10 External Water Flow & Footnotes 1, 2
6. EV Charging Technical Compliance (Mục 2.10 QCVN 04)
7. Statutory Repeal of Thông tư 06/2021/TT-BXD
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAG_SERVICE_DIR = REPO_ROOT / "services/rag-service"
if str(RAG_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_SERVICE_DIR))

from tests.gold_benchmark.benchmark_runner import GoldBenchmarkRunner  # noqa: E402


def test_gold_benchmark_suite_execution():
    """Execute all 50 gold standard statutory test cases and enforce 100% pass rate."""
    runner = GoldBenchmarkRunner()
    results = runner.run_all()

    total = results["total_cases"]
    passed = results["passed_cases"]
    score = results["overall_score"]

    failed_cases = [c for c in results["case_details"] if not c["passed"]]
    failure_summary = "\n".join([f"[{c['id']}] {c['category']} - {c['reason']}" for c in failed_cases])

    assert total == 50, f"Expected exactly 50 benchmark cases, got {total}"
    assert passed == total, f"Gold benchmark failed {len(failed_cases)} cases (Score: {score}%):\n{failure_summary}"
    assert score == 100.0, f"Overall benchmark score must be 100.0%, got {score}%"


def test_gold_benchmark_category_integrity():
    """Verify that every individual category in the benchmark achieves 100% accuracy."""
    runner = GoldBenchmarkRunner()
    results = runner.run_all()

    expected_categories = [
        "scope_gate",
        "normative_force",
        "temporal_edition",
        "numeric_table4",
        "numeric_table10",
        "ev_charging_qcvn04",
        "repeal_enforcement",
    ]

    breakdown = results["category_breakdown"]
    for cat in expected_categories:
        assert cat in breakdown, f"Missing expected category {cat} in benchmark breakdown"
        assert breakdown[cat]["accuracy"] == 100.0, (
            f"Category {cat} achieved only {breakdown[cat]['accuracy']}% accuracy "
            f"({breakdown[cat]['passed']}/{breakdown[cat]['total']})"
        )
