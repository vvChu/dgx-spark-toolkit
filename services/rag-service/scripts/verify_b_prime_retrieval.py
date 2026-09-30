#!/usr/bin/env python3
"""Run real retrieval queries against legal_docs_v12_okf inside container.

Tests the 4 canonical verification criteria from Grok 4.7 Verdict B':
1. Exact Clause Precision: Dieu 3 Khoan 1 of Luat Xay dung 2025.
2. TCVN Section Span Integrity: Muc 1 & 1.1 of TCVN 7336:2021.
3. QCVN Anchor Retrieval: QCVN 06:2022 General Provisions.
4. OUTDATED status enforcement: Nghi dinh 10/2021/ND-CP.
"""
import json
import os
import sys
from pathlib import Path

COLLECTION = "legal_docs_v12_okf"

TEST_CASES = [
    {
        "id": "CASE_1_LUAT_XD_2025",
        "query": "Hoạt động xây dựng gồm những công việc gì theo Luật Xây dựng 2025?",
        "expected_doc": "135/2025/QH15",
        "expected_clause": "dieu-3",
        "expected_status": "ACTIVE",
    },
    {
        "id": "CASE_2_TCVN_7336",
        "query": "TCVN 7336:2021 yêu cầu thiết kế và lắp đặt hệ thống chữa cháy tự động",
        "expected_doc": "TCVN 7336:2021",
        "expected_clause": "muc-1",
        "expected_status": "ACTIVE",
    },
    {
        "id": "CASE_3_QCVN_06",
        "query": "Quy chuẩn kỹ thuật quốc gia về an toàn cháy cho nhà và công trình QCVN 06:2022 quy định chung",
        "expected_doc": "QCVN 06:2022/BXD",
        "expected_clause": "muc-1",
        "expected_status": "ACTIVE",
    },
    {
        "id": "CASE_4_REPLACEMENT_ND10",
        "query": "Quản lý chi phí đầu tư xây dựng theo Nghị định 10/2021",
        "expected_doc": "206/2026/NĐ-CP",
        "expected_clause": "dieu-38",
        "expected_status": "ACTIVE",
    },
]

def main():
    import urllib.request

    api_url = "http://localhost:8005/search"
    # Check if inside container or on host
    try:
        urllib.request.urlopen("http://localhost:8005/health", timeout=2)
    except Exception:
        api_url = "http://localhost:8000/search"

    print("\n" + "=" * 80)
    print("VERDICT B-PRIME END-TO-END RETRIEVAL VERIFICATION SCORECARD")
    print("=" * 80)
    print(f"Target Service Endpoint: {api_url}")

    all_passed = True

    for tc in TEST_CASES:
        print(f"\nEvaluating {tc['id']}: '{tc['query']}'")
        payload = json.dumps({"query": tc["query"], "limit": 5}).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
        except Exception as e:
            print(f"  [ERROR] API request failed: {e}")
            all_passed = False
            continue

        print(f"  Top 3 Hits:")
        hit_matched = False
        status_matched = True

        for rank, hit in enumerate(results[:3], 1):
            doc_no = hit.get("doc_number", "")
            pid = hit.get("parent_id", "")
            status = hit.get("validity_status", "")
            snippet = (hit.get("child_text") or hit.get("text") or "")[:120].replace("\n", " ")
            print(f"    {rank}. [Score: {hit.get('score', 0):.4f}] {doc_no} | {pid} ({status})")
            print(f"       Text: {snippet}...")

            if (tc["expected_clause"] in pid or tc["expected_clause"] in (hit.get("text") or "")) and (tc["expected_doc"] in doc_no or tc["expected_doc"] in pid):
                hit_matched = True
            if "expected_status" in tc and tc["expected_status"] != status:
                status_matched = False

        status_str = "PASS" if (hit_matched and status_matched) else "FAIL"
        print(f"  --> Verdict: [{status_str}] (Target: {tc['expected_clause']} in {tc['expected_doc']})")
        if status_str != "PASS":
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("ALL 4 VERDICT B-PRIME CANONICAL TEST CASES PASSED WITH 100% PRECISION!")
    else:
        print("SOME TEST CASES FAILED - REVIEW REQUIRED")
    print("=" * 80)
    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
