"""Gold Benchmark Suite Runner (OKF Enterprise Architecture Standard).
=============================================================================
Evaluates the 50 gold standard statutory questions across 7 OKF metric categories:
1. Scope Gate & Statutory Exclusions (Abstention Accuracy).
2. Normative Force Disambiguation (Binding status correctness).
3. Temporal Edition Anchoring (Cutoff accuracy for 2022 vs 2023 vs 2026 vs 2025).
4. Table 4 Neuro-Symbolic Resolution (Numeric exact match + footnotes 1, 2, 3).
5. Table 10 External Water Flow (Numeric exact match + footnotes 1, 2).
6. QCVN 04 EV Charging Technical Compliance (Section 2.10 predicates).
7. Strict Statutory Repeal Enforcement (Prohibition of TT 06/2021 after 01/07/2026).

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Hermes OKF Evaluation Metrics
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from domain.normative_force import resolve_normative_force
from domain.project_profile import (
    GeometricParameters,
    LegalMilestones,
    PrimaryFunction,
    ProjectLevel,
    ProjectProfile,
)
from retrieval.scope_gate import ScopeGate
from symbolic.charging_area_validator import ChargingAreaParameters, ChargingAreaValidator
from symbolic.table10_solver import Table10SymbolicSolver
from symbolic.table4_solver import Table4SymbolicSolver

BENCHMARK_CASES_PATH = Path(__file__).parent / "gold_benchmark_cases.json"


class GoldBenchmarkRunner:
    """Automated benchmark evaluator for Vietnamese Legal RAG."""

    def __init__(self, dataset_path: Path = BENCHMARK_CASES_PATH):
        with open(dataset_path, "r", encoding="utf-8") as f:
            self.cases: List[Dict[str, Any]] = json.load(f)

        self.scope_gate = ScopeGate()
        self.table4_solver = Table4SymbolicSolver()
        self.table10_solver = Table10SymbolicSolver()
        self.charging_validator = ChargingAreaValidator()

    def run_all(self) -> Dict[str, Any]:
        """Run all 50 gold test cases and return structured OKF scorecard."""
        total = len(self.cases)
        passed = 0
        details: List[Dict[str, Any]] = []

        category_stats: Dict[str, Dict[str, int]] = {}

        for case in self.cases:
            cat = case["category"]
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "passed": 0}
            category_stats[cat]["total"] += 1

            case_pass, reason = self._evaluate_case(case)
            if case_pass:
                passed += 1
                category_stats[cat]["passed"] += 1

            details.append({
                "id": case["id"],
                "category": cat,
                "question": case["question"],
                "passed": case_pass,
                "reason": reason,
            })

        overall_score = round((passed / total) * 100.0, 2) if total > 0 else 0.0

        return {
            "total_cases": total,
            "passed_cases": passed,
            "overall_score": overall_score,
            "category_breakdown": {
                cat: {
                    "total": stats["total"],
                    "passed": stats["passed"],
                    "accuracy": round((stats["passed"] / stats["total"]) * 100.0, 1),
                }
                for cat, stats in category_stats.items()
            },
            "case_details": details,
        }

    def _evaluate_case(self, case: Dict[str, Any]) -> tuple[bool, str]:
        """Evaluate a single test case against the dedicated engine."""
        cat = case["category"]

        if cat == "scope_gate":
            profile = ProjectProfile(
                project_name=case["project_name"],
                project_level=ProjectLevel(case["project_level"]),
                primary_function=PrimaryFunction(case["primary_function"]),
                geometry=GeometricParameters(
                    fire_height_m=case["fire_height_m"],
                    above_ground_floors=case.get("above_ground_floors", 10),
                    underground_floors=case.get("underground_floors", 0),
                    total_floor_area_m2=case.get("total_floor_area_m2", 15000.0),
                ),
            )
            decision = self.scope_gate.evaluate_scope(profile)

            if "expected_applicable" in case and decision.is_applicable != case["expected_applicable"]:
                return False, f"Expected is_applicable={case['expected_applicable']}, got {decision.is_applicable}"
            if "expected_reject_keyword" in case and case["expected_reject_keyword"] not in (decision.reject_reason or ""):
                return False, f"Expected reject keyword '{case['expected_reject_keyword']}' in '{decision.reject_reason}'"
            if "expected_special_clearance" in case and decision.special_clearance_required != case["expected_special_clearance"]:
                return False, f"Expected special_clearance={case['expected_special_clearance']}"
            if "expected_codes" in case:
                for code in case["expected_codes"]:
                    if code not in decision.applicable_codes:
                        return False, f"Missing expected code {code} in {decision.applicable_codes}"
            return True, "Passed scope gate checks."

        elif cat == "normative_force":
            force = resolve_normative_force(
                case["document_identifier"],
                is_cited_in_clause=case.get("is_cited", False),
                contract_stipulated=case.get("contract_stipulated", False),
            )
            if force.value != case["expected_force"]:
                return False, f"Expected {case['expected_force']}, got {force.value}"
            return True, "Passed normative force check."

        elif cat == "temporal_edition":
            pccc_date = date.fromisoformat(case["pccc_approval_date"]) if "pccc_approval_date" in case else None
            permit_date = date.fromisoformat(case["building_permit_date"]) if "building_permit_date" in case else None

            profile = ProjectProfile(
                project_name="Dự án temporal test",
                project_level=ProjectLevel.CAP_I,
                primary_function=PrimaryFunction.F1_2,
                geometry=GeometricParameters(fire_height_m=60.0, above_ground_floors=20, total_floor_area_m2=20000.0),
                milestones=LegalMilestones(pccc_approval=pccc_date, building_permit=permit_date),
            )
            decision = self.scope_gate.evaluate_scope(profile)

            if "expected_qcvn06_edition" in case:
                actual = decision.edition_map.get("QCVN 06:2022/BXD", "")
                if actual != case["expected_qcvn06_edition"]:
                    return False, f"Expected QCVN 06 edition '{case['expected_qcvn06_edition']}', got '{actual}'"

            if "expected_qcvn04_edition" in case:
                actual = decision.edition_map.get("QCVN 04:2021/BXD", "")
                if actual != case["expected_qcvn04_edition"]:
                    return False, f"Expected QCVN 04 edition '{case['expected_qcvn04_edition']}', got '{actual}'"

            if "expected_legal_era" in case and decision.legal_era != case["expected_legal_era"]:
                return False, f"Expected legal era '{case['expected_legal_era']}', got '{decision.legal_era}'"

            return True, "Passed temporal edition check."

        elif cat == "repeal_enforcement":
            pccc_date = date.fromisoformat(case["pccc_approval_date"])
            profile = ProjectProfile(
                project_name="Dự án repeal test",
                project_level=ProjectLevel.CAP_I,
                primary_function=PrimaryFunction.F1_2,
                geometry=GeometricParameters(fire_height_m=60.0, above_ground_floors=20, total_floor_area_m2=20000.0),
                milestones=LegalMilestones(pccc_approval=pccc_date),
            )
            if case.get("expected_prohibited"):
                try:
                    profile.validate_regulatory_citations([case["invalid_citation"]])
                    return False, "Expected ValueError on prohibited citation, but validation passed."
                except ValueError:
                    return True, "Properly blocked prohibited repealed circular citation."
            else:
                profile.validate_regulatory_citations([case["citation"]])
                return True, "Allowed valid pre-2026 citation."

        elif cat == "numeric_table4":
            res = self.table4_solver.resolve_element_rei(
                case["structure_type"],
                building_grade=case["grade"],
                has_sprinkler=case.get("has_sprinkler", False),
                no_attic=case.get("no_attic", True),
                has_auto_alarm=case.get("has_auto_alarm", False),
                wall_material_group=case.get("wall_material_group"),
                floor_finish_group=case.get("floor_finish_group"),
            )
            if res["final_rei"] != case["expected_rei"]:
                return False, f"Expected REI '{case['expected_rei']}', got '{res['final_rei']}'"
            if "expected_footnote" in case:
                if not any(case["expected_footnote"] in fn for fn in res["footnotes_applied"]):
                    return False, f"Expected footnote '{case['expected_footnote']}' in {res['footnotes_applied']}"
            return True, "Passed Table 4 calculation."

        elif cat == "numeric_table10":
            res = self.table10_solver.calculate_flow(
                building_volume_m3=case["building_volume_m3"],
                hazard_class=case["hazard_class"],
                fire_height_m=case["fire_height_m"],
                compartment_volumes_m3=case.get("compartment_volumes_m3"),
            )
            if res["flow_l_s"] != case["expected_flow_l_s"]:
                return False, f"Expected flow {case['expected_flow_l_s']} L/s, got {res['flow_l_s']} L/s"
            if "expected_multiplier" in case and res["height_multiplier"] != case["expected_multiplier"]:
                return False, f"Expected multiplier {case['expected_multiplier']}, got {res['height_multiplier']}"
            if "expected_footnote" in case:
                if not any(case["expected_footnote"] in fn for fn in res["applied_footnotes"]):
                    return False, f"Expected footnote '{case['expected_footnote']}' in {res['applied_footnotes']}"
            return True, "Passed Table 10 calculation."

        elif cat == "ev_charging_qcvn04":
            params = ChargingAreaParameters(
                location=case.get("location", "basement"),
                car_spots=case.get("car_spots", 0),
                motorcycle_spots=case.get("motorcycle_spots", 0),
                compartment_area_m2=case.get("compartment_area_m2", 200.0),
                has_fire_wall_type_1=case.get("has_fire_wall_type_1", True),
                open_space_distance_m=case.get("open_space_distance_m", 6.0),
                has_drencher_curtain=case.get("has_drencher_curtain", False),
                drencher_flow_per_meter=case.get("drencher_flow_per_meter", 0.0),
                has_auto_alarm_24h=case.get("has_auto_alarm_24h", True),
                has_auto_sprinkler=case.get("has_auto_sprinkler", True),
                has_smoke_extraction=case.get("has_smoke_extraction", True),
                has_co_hf_warning=case.get("has_co_hf_warning", True),
                charger_power_kw=case.get("charger_power_kw", 11.0),
                pccc_approval_date=(
                    date.fromisoformat(case["pccc_approval_date"]) if "pccc_approval_date" in case else None
                ),
            )
            assessment = self.charging_validator.validate("Test EV Case", params)

            if "expected_overall_status" in case and assessment.overall_status.value != case["expected_overall_status"]:
                return False, f"Expected status {case['expected_overall_status']}, got {assessment.overall_status.value}"

            if "expected_pass" in case:
                passed_all = assessment.overall_status.value == "COMPLIANT"
                if passed_all != case["expected_pass"]:
                    return False, f"Expected pass={case['expected_pass']}, got {passed_all}"

            if "expected_grace_deadline" in case:
                if not any(w.deadline == case["expected_grace_deadline"] for w in assessment.legal_warnings):
                    return False, f"Missing expected grace deadline {case['expected_grace_deadline']}"

            return True, "Passed EV charging validation."

        return False, f"Unknown category {cat}"
