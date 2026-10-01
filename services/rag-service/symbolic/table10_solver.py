"""Neuro-Symbolic Solver for QCVN 06:2022/BXD Table 10 (External Water Flow).
=============================================================================
Calculates statutory external firefighting water flow (L/s) for F5 industrial
facilities based on building volume, hazard category, building height, and
multi-compartment rules:
- Table 10 volume brackets lookup (A/B/C vs D/E hazard classes).
- Footnote 1: Height >= 50m multiplier (1.5x).
- Footnote 2: Multi-compartment combination (largest + 50% second largest).

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Hermes Table 10 Symbolic Solver Specification
"""

from typing import Dict, List, Optional


class Table10SymbolicSolver:
    """Symbolic solver for Table 10 external water flow calculations."""

    @staticmethod
    def _lookup_single_volume(volume_m3: float, hazard_class: str) -> float:
        """Lookup base flow in L/s for a single volume and hazard class."""
        norm_class = hazard_class.strip().upper()
        is_abc = any(c in norm_class for c in ("A", "B", "C"))

        if volume_m3 <= 50000:
            return 20.0 if is_abc else 10.0
        elif volume_m3 <= 100000:
            return 30.0 if is_abc else 15.0
        elif volume_m3 <= 200000:
            return 40.0 if is_abc else 20.0
        elif volume_m3 <= 300000:
            return 50.0 if is_abc else 25.0
        elif volume_m3 <= 400000:
            return 60.0 if is_abc else 30.0
        elif volume_m3 <= 500000:
            return 70.0 if is_abc else 35.0
        elif volume_m3 <= 600000:
            return 80.0 if is_abc else 40.0
        elif volume_m3 <= 700000:
            return 90.0 if is_abc else 45.0
        else:
            return 100.0 if is_abc else 50.0

    def calculate_flow(
        self,
        building_volume_m3: float,
        hazard_class: str = "C",
        fire_height_m: float = 12.0,
        compartment_volumes_m3: Optional[List[float]] = None,
    ) -> Dict[str, any]:
        """Compute the total required external firefighting water flow.

        Args:
            building_volume_m3: Total building volume in m³.
            hazard_class: Production/storage hazard class (A, B, C, D, E).
            fire_height_m: Building fire height in meters.
            compartment_volumes_m3: List of individual compartment volumes if segmented.

        Returns:
            Dict containing final flow_l_s, base_flow_l_s, applied_multiplier, and applied_footnotes.
        """
        applied_footnotes: List[str] = []

        # Compartment evaluation
        if compartment_volumes_m3 and len(compartment_volumes_m3) > 1:
            sorted_vols = sorted(compartment_volumes_m3, reverse=True)
            flow_1 = self._lookup_single_volume(sorted_vols[0], hazard_class)
            flow_2 = self._lookup_single_volume(sorted_vols[1], hazard_class)
            base_flow = flow_1 + (0.5 * flow_2)
            applied_footnotes.append(
                f"Bảng 10 Chú thích 2: Nhiều khoang cháy (khoang 1: {sorted_vols[0]}m³ -> {flow_1}L/s, "
                f"khoang 2: {sorted_vols[1]}m³ -> {flow_2}L/s x 0.5)"
            )
        else:
            base_flow = self._lookup_single_volume(building_volume_m3, hazard_class)

        # Footnote 1: Height >= 50m
        multiplier = 1.0
        if fire_height_m >= 50.0:
            multiplier = 1.5
            applied_footnotes.append("Bảng 10 Chú thích 1: Chiều cao PCCC ≥ 50m nhân hệ số 1.5")

        final_flow = round(base_flow * multiplier, 2)

        return {
            "flow_l_s": final_flow,
            "base_flow_l_s": base_flow,
            "height_multiplier": multiplier,
            "applied_footnotes": applied_footnotes,
        }
