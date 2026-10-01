"""Tests for Neuro-Symbolic Table Solvers and Statutory Validators.
=============================================================================
Validates:
1. Table4SymbolicSolver: QCVN 06 Table 4 baseline lookup and footnotes 1, 2, 3.
2. Table10SymbolicSolver: QCVN 06 Table 10 external water flow and footnotes 1, 2.
3. ChargingAreaValidator: QCVN 04 Mục 2.10 EV charging rules, power caps, and transitional grace period.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
"""

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAG_SERVICE_DIR = REPO_ROOT / "services/rag-service"
if str(RAG_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_SERVICE_DIR))

from domain.compliance import FindingStatus, OverallStatus  # noqa: E402
from symbolic.charging_area_validator import ChargingAreaParameters, ChargingAreaValidator  # noqa: E402
from symbolic.table10_solver import Table10SymbolicSolver  # noqa: E402
from symbolic.table4_solver import Table4SymbolicSolver  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Table 4 Solver Tests
# ---------------------------------------------------------------------------

def test_table4_baseline_ratings():
    """Verify Table 4 baseline lookup for Grade I and Grade II."""
    solver = Table4SymbolicSolver()

    res_i = solver.resolve_element_rei("column", building_grade="Bậc_I")
    assert res_i["final_rei"] == "R 120"
    assert len(res_i["footnotes_applied"]) == 0

    res_ii = solver.resolve_element_rei("floor", building_grade="Bậc_II")
    assert res_ii["final_rei"] == "REI 45"


def test_table4_footnote_1_sprinkler_roof_and_truss():
    """Footnote 1: Sprinkler protection reduces roof and truss REI to RE15 / R15."""
    solver = Table4SymbolicSolver()

    roof_res = solver.resolve_element_rei(
        "roof",
        building_grade="Bậc_I",
        has_sprinkler=True,
        no_attic=True,
    )
    assert roof_res["base_rei"] == "RE 30"
    assert roof_res["final_rei"] == "RE 15"
    assert any("Chú thích 1" in fn for fn in roof_res["footnotes_applied"])

    truss_res = solver.resolve_element_rei(
        "truss_beam_purlin",
        building_grade="Bậc_I",
        has_sprinkler=True,
        no_attic=True,
    )
    assert truss_res["base_rei"] == "R 30"
    assert truss_res["final_rei"] == "R 15"


def test_table4_footnote_2_and_3_step_reductions():
    """Footnote 2 & 3: Inner wall and floor 1-step reduction with active protection."""
    solver = Table4SymbolicSolver()

    # Footnote 2: Inner wall
    wall_res = solver.resolve_element_rei(
        "wall_inner",
        building_grade="Bậc_I",
        has_auto_alarm=True,
        wall_material_group="A",
    )
    assert wall_res["base_rei"] == "REI 120"
    assert wall_res["final_rei"] == "REI 90"

    # Footnote 3: Floor
    floor_res = solver.resolve_element_rei(
        "floor",
        building_grade="Bậc_I",
        has_sprinkler=True,
        floor_finish_group="B1",
    )
    assert floor_res["base_rei"] == "REI 60"
    assert floor_res["final_rei"] == "REI 45"


def test_table4_grade_v_unregulated():
    """Grade V elements are unregulated."""
    solver = Table4SymbolicSolver()
    res = solver.resolve_element_rei("load_bearing_wall", building_grade="Bậc_V")
    assert res["final_rei"] == "Không quy định"


# ---------------------------------------------------------------------------
# 2. Table 10 Solver Tests
# ---------------------------------------------------------------------------

def test_table10_baseline_flow():
    """Verify base flow for single volume under Table 10."""
    solver = Table10SymbolicSolver()
    res = solver.calculate_flow(building_volume_m3=45000, hazard_class="C", fire_height_m=15.0)
    assert res["flow_l_s"] == 20.0
    assert res["height_multiplier"] == 1.0


def test_table10_footnote_1_height_multiplier():
    """Footnote 1: Height >= 50m applies 1.5x multiplier."""
    solver = Table10SymbolicSolver()
    res = solver.calculate_flow(building_volume_m3=45000, hazard_class="C", fire_height_m=55.0)
    assert res["base_flow_l_s"] == 20.0
    assert res["height_multiplier"] == 1.5
    assert res["flow_l_s"] == 30.0
    assert any("Chú thích 1" in fn for fn in res["applied_footnotes"])


def test_table10_footnote_2_multi_compartment():
    """Footnote 2: Multi-compartment flow is largest + 50% second largest."""
    solver = Table10SymbolicSolver()
    # 80k m³ -> 30 L/s; 40k m³ -> 20 L/s; Total = 30 + 0.5*20 = 40 L/s
    res = solver.calculate_flow(
        building_volume_m3=120000,
        hazard_class="C",
        fire_height_m=20.0,
        compartment_volumes_m3=[80000, 40000],
    )
    assert res["base_flow_l_s"] == 40.0
    assert res["flow_l_s"] == 40.0
    assert any("Chú thích 2" in fn for fn in res["applied_footnotes"])


# ---------------------------------------------------------------------------
# 3. Charging Area Validator Tests
# ---------------------------------------------------------------------------

def test_charging_area_fully_compliant():
    """Verify fully compliant EV charging area in basement."""
    validator = ChargingAreaValidator()
    params = ChargingAreaParameters(
        location="basement",
        car_spots=20,
        motorcycle_spots=40,
        compartment_area_m2=280.0,
        has_fire_wall_type_1=True,
        has_auto_alarm_24h=True,
        has_auto_sprinkler=True,
        has_smoke_extraction=True,
        has_co_hf_warning=True,
        charger_power_kw=11.0,
        pccc_approval_date=date(2027, 1, 15),
    )
    assessment = validator.validate("Chung cư Hòa Bình", params)
    assert assessment.overall_status == OverallStatus.COMPLIANT
    assert all(f.status == FindingStatus.PASS for f in assessment.findings)
    assert len(assessment.legal_warnings) == 0


def test_charging_area_spot_and_power_violations():
    """Verify spot over-limit and power over-limit triggers FAIL."""
    validator = ChargingAreaValidator()
    params = ChargingAreaParameters(
        location="basement",
        car_spots=35,  # > 25 (FAIL)
        motorcycle_spots=60,  # > 50 (FAIL)
        compartment_area_m2=1500.0,  # > 1200 (FAIL)
        has_fire_wall_type_1=False,  # FAIL
        has_auto_alarm_24h=True,
        has_auto_sprinkler=True,
        has_smoke_extraction=True,
        has_co_hf_warning=True,
        charger_power_kw=45.0,  # > 22 kW (FAIL)
        pccc_approval_date=date(2024, 6, 1),  # Generates grace warning
    )
    assessment = validator.validate("Chung cư Cầu Giấy", params)
    assert assessment.overall_status == OverallStatus.NON_COMPLIANT

    fails = [f for f in assessment.findings if f.status == FindingStatus.FAIL]
    assert len(fails) >= 4  # spots, area, separation, power
    assert any("2027-06-15" in w.deadline for w in assessment.legal_warnings)

    md = assessment.to_markdown()
    assert "KHÔNG ĐẠT (NON_COMPLIANT)" in md
    assert "FAIL ❌" in md
