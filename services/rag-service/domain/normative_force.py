"""Normative Force Disambiguation Engine (OKF Standard).
=============================================================================
Distinguishes binding legal status:
- QCVN = mandatory (bắt buộc áp dụng)
- TCVN = voluntary (khuyến nghị), EXCEPT when explicitly cited by a QCVN or contract
- Statutory Laws/Decrees/Circulars = mandatory

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Grok 4.7 xhigh & Hermes Domain Review
"""

from enum import Enum
from typing import FrozenSet


class NormativeForce(str, Enum):
    """Classification of normative binding power in Vietnamese construction law."""
    MANDATORY = "mandatory"
    VOLUNTARY = "voluntary"
    MANDATORY_BY_REFERENCE = "mandatory_by_reference"
    CONTRACT_ADOPTED = "contract_adopted"


# Standards cited directly within QCVN 06:2022 and QCVN 04:2021
CITED_MANDATORY_STANDARDS: FrozenSet[str] = frozenset({
    "TCVN 7336",  # Phòng cháy chữa cháy - Hệ thống sprinkler tự động
    "TCVN 3890",  # Phương tiện PCCC cho nhà và công trình
    "TCVN 5738",  # Hệ thống báo cháy tự động - Yêu cầu kỹ thuật
    "TCVN 2622",  # Phòng cháy, chống cháy cho nhà và công trình
    "TCVN 9383",  # Thử nghiệm khả năng chịu lửa của cửa đi và cửa chắn
    "TCVN 9311",  # Thử nghiệm chịu lửa - Các bộ phận kết cấu xây dựng
    "TCVN 3254",  # An toàn cháy - Yêu cầu chung đối với vật liệu
})


def resolve_normative_force(
    doc_identifier: str,
    is_cited_in_clause: bool = False,
    contract_stipulated: bool = False,
) -> NormativeForce:
    """Resolve the normative legal binding force of a document or standard.

    Args:
        doc_identifier: Document number, code, or identifier (e.g. 'QCVN 06:2022/BXD', 'TCVN 7336:2021').
        is_cited_in_clause: Whether the standard is cited by an applicable QCVN clause.
        contract_stipulated: Whether the parties explicitly adopted the standard into project contract.

    Returns:
        NormativeForce enum instance.
    """
    clean_id = (doc_identifier or "").strip().upper()

    # Contract agreement overrides voluntary status
    if contract_stipulated:
        return NormativeForce.CONTRACT_ADOPTED

    # Statutory technical regulations, laws, decrees, circulars are strictly mandatory
    if any(prefix in clean_id for prefix in ("QCVN", "QCXDVN", "LUẬT", "LUAT", "NĐ-CP", "ND-CP", "TT-BXD")):
        return NormativeForce.MANDATORY

    # Tiêu chuẩn quốc gia (TCVN)
    if "TCVN" in clean_id:
        if is_cited_in_clause:
            return NormativeForce.MANDATORY_BY_REFERENCE

        for cited_std in CITED_MANDATORY_STANDARDS:
            if cited_std.upper() in clean_id:
                return NormativeForce.MANDATORY_BY_REFERENCE

        return NormativeForce.VOLUNTARY

    return NormativeForce.VOLUNTARY
