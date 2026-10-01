"""Neuro-Symbolic Solver for QCVN 06:2022/BXD Table 4 (Fire Resistance Ratings).
=============================================================================
Computes exact structural fire resistance requirements (REI ratings) by
evaluating baseline statutory tables and multi-variable footnote predicates:
- Footnote 1: Sprinkler protection for roof/truss without attic -> R15/RE15.
- Footnote 2: Auto fire alarm + non-combustible group A walls -> 1 step reduction for inner walls.
- Footnote 3: Whole-building sprinkler + B1 finish material -> 1 step reduction for floors.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Hermes Table 4 Symbolic Solver Specification
"""

from typing import Dict, List, Optional
from domain.project_profile import StructureResistanceGrade

REDUCTION_MAP: Dict[str, str] = {
    "REI 120": "REI 90",
    "REI 90": "REI 60",
    "REI 60": "REI 45",
    "REI 45": "REI 30",
    "REI 30": "REI 15",
    "R 120": "R 90",
    "R 90": "R 60",
    "R 60": "R 45",
    "R 45": "R 30",
    "R 30": "R 15",
    "RE 30": "RE 15",
}

TABLE_4_BASELINE: Dict[str, Dict[str, str]] = {
    StructureResistanceGrade.BAC_I.value: {
        "load_bearing_wall": "R 120",
        "column": "R 120",
        "floor": "REI 60",
        "roof": "RE 30",
        "truss_beam_purlin": "R 30",
        "wall_inner": "REI 120",
        "staircase": "R 60",
    },
    StructureResistanceGrade.BAC_II.value: {
        "load_bearing_wall": "R 90",
        "column": "R 90",
        "floor": "REI 45",
        "roof": "RE 15",
        "truss_beam_purlin": "R 15",
        "wall_inner": "REI 90",
        "staircase": "R 60",
    },
    StructureResistanceGrade.BAC_III.value: {
        "load_bearing_wall": "R 45",
        "column": "R 45",
        "floor": "REI 45",
        "roof": "RE 15",
        "truss_beam_purlin": "R 15",
        "wall_inner": "REI 60",
        "staircase": "R 45",
    },
    StructureResistanceGrade.BAC_IV.value: {
        "load_bearing_wall": "R 15",
        "column": "R 15",
        "floor": "REI 15",
        "roof": "RE 15",
        "truss_beam_purlin": "R 15",
        "wall_inner": "REI 45",
        "staircase": "R 15",
    },
    StructureResistanceGrade.BAC_V.value: {
        "load_bearing_wall": "Không quy định",
        "column": "Không quy định",
        "floor": "Không quy định",
        "roof": "Không quy định",
        "truss_beam_purlin": "Không quy định",
        "wall_inner": "Không quy định",
        "staircase": "Không quy định",
    },
}


class Table4SymbolicSolver:
    """Symbolic solver for Table 4 QCVN 06:2022 fire resistance ratings."""

    @staticmethod
    def decrement_rei_level(rei: str, steps: int = 1) -> str:
        """Step-down REI rating according to statutory reduction rules."""
        result = rei
        for _ in range(steps):
            result = REDUCTION_MAP.get(result, result)
        return result

    def lookup_table4_base(self, grade: str, structure_type: str) -> str:
        """Tra giá trị gốc Bảng 4."""
        grade_dict = TABLE_4_BASELINE.get(grade, TABLE_4_BASELINE[StructureResistanceGrade.BAC_I.value])
        return grade_dict.get(structure_type, "Không quy định")

    def resolve_element_rei(
        self,
        structure_type: str,
        building_grade: str,
        has_sprinkler: bool = False,
        no_attic: bool = True,
        has_auto_alarm: bool = False,
        wall_material_group: Optional[str] = None,
        floor_finish_group: Optional[str] = None,
    ) -> Dict[str, str]:
        """Resolve final REI for a single structural element with applied footnotes.

        Returns:
            Dict containing:
            - "base_rei": Original table requirement
            - "final_rei": Adjusted requirement after footnote predicates
            - "footnotes_applied": List of applied footnote references
        """
        base_rei = self.lookup_table4_base(building_grade, structure_type)
        if base_rei == "Không quy định":
            return {"base_rei": base_rei, "final_rei": base_rei, "footnotes_applied": []}

        final_rei = base_rei
        applied: List[str] = []

        # Chú thích 1: Mái không áp mái có Sprinkler (TCVN 7336)
        if has_sprinkler and no_attic and structure_type in ("roof", "truss_beam_purlin"):
            if structure_type == "roof":
                final_rei = "RE 15"
            else:
                final_rei = "R 15"
            applied.append("Bảng 4 Chú thích 1 (Sprinkler giảm REI mái và giàn/dầm xuống RE15/R15)")

        # Chú thích 2: Báo cháy tự động + vật liệu tường bao che nhóm A
        if has_auto_alarm and wall_material_group == "A" and structure_type == "wall_inner":
            final_rei = self.decrement_rei_level(base_rei, steps=1)
            applied.append("Bảng 4 Chú thích 2 (Báo cháy + nhóm A giảm 1 bậc tường trong)")

        # Chú thích 3: Sprinkler toàn bộ + hoàn thiện sàn nhóm B1
        if has_sprinkler and floor_finish_group == "B1" and structure_type == "floor":
            final_rei = self.decrement_rei_level(base_rei, steps=1)
            applied.append("Bảng 4 Chú thích 3 (Sprinkler + hoàn thiện B1 giảm 1 bậc sàn)")

        return {
            "base_rei": base_rei,
            "final_rei": final_rei,
            "footnotes_applied": applied,
        }

    def resolve_all_elements(
        self,
        building_grade: str,
        has_sprinkler: bool = False,
        no_attic: bool = True,
        has_auto_alarm: bool = False,
        wall_material_group: Optional[str] = None,
        floor_finish_group: Optional[str] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Resolve REI for all 7 standard structural element categories."""
        elements = [
            "load_bearing_wall",
            "column",
            "floor",
            "roof",
            "truss_beam_purlin",
            "wall_inner",
            "staircase",
        ]
        return {
            elem: self.resolve_element_rei(
                elem,
                building_grade=building_grade,
                has_sprinkler=has_sprinkler,
                no_attic=no_attic,
                has_auto_alarm=has_auto_alarm,
                wall_material_group=wall_material_group,
                floor_finish_group=floor_finish_group,
            )
            for elem in elements
        }
