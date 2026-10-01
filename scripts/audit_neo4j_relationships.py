#!/usr/bin/env python3
"""Audit and Repair Neo4j Knowledge Graph Relationships
=============================================================================
Audits statutory relationships in Neo4j, focusing on:
1. Normalizing doc_number on all :Document nodes where doc_number is NULL.
2. Correcting mismatched REPLACES/AMENDS relationships for 2026 Decrees.
3. Establishing Document-level GOVERNS_TRANSITIONAL edges with metadata:
   {cutoff_date, grace_period_end, condition}.
4. Ensuring complete, deterministic legal timeline traversals.

Adheres to:
- ADR-0058: Hard Completion Lock
- ADR-0059: Legal Verbatim Grounding
- Grok 4.7 xhigh Condition C3: Document-level GOVERNS_TRANSITIONAL
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from neo4j import AsyncGraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAG_SERVICE_DIR = REPO_ROOT / "services/rag-service"
if str(RAG_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_SERVICE_DIR))

from core.config import Settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("neo4j_audit")

# Canonical Transitional Rules Matrix
TRANSITIONAL_RULES = [
    {
        "source_doc_number": "135/2025/QH15",
        "target_doc_number": "50/2014/QH13",
        "cutoff_date": "2026-07-01",
        "grace_period_end": "2027-07-01",
        "condition": "Hồ sơ hoặc hợp đồng ký kết/phê duyệt trước 01/07/2026 tiếp tục áp dụng Luật Xây dựng 2014.",
    },
    {
        "source_doc_number": "31/2026/TT-BXD",
        "target_doc_number": "QCVN 04:2021/BXD",
        "cutoff_date": "2026-12-15",
        "grace_period_end": "2027-06-15",
        "condition": "Nhà chung cư hiện hữu có thời hạn đến 15/06/2027 để hoàn thành rà soát trạm sạc xe điện.",
    },
    {
        "source_doc_number": "09/2023/TT-BXD",
        "target_doc_number": "QCVN 06:2022/BXD",
        "cutoff_date": "2023-12-01",
        "grace_period_end": "2024-12-01",
        "condition": "Hồ sơ thiết kế PCCC nộp trước 01/12/2023 tiếp tục áp dụng quy chuẩn tại thời điểm nộp.",
    },
]

# Decrees 2026 Correction Matrix (fixing misallocated targets)
DECREE_CORRECTIONS = [
    # NĐ 207/2026 sửa đổi quản lý dự án (NĐ 15/2021)
    {"decree": "207/2026/NĐ-CP", "correct_target": "15/2021/NĐ-CP", "rel_type": "AMENDS"},
    # NĐ 209/2026 sửa đổi quản lý chất lượng & thi công bảo trì (NĐ 06/2021)
    {"decree": "209/2026/NĐ-CP", "correct_target": "06/2021/NĐ-CP", "rel_type": "AMENDS"},
    # NĐ 206/2026 sửa đổi quản lý chi phí (NĐ 10/2021)
    {"decree": "206/2026/NĐ-CP", "correct_target": "10/2021/NĐ-CP", "rel_type": "AMENDS"},
    # NĐ 339/2026 sửa đổi xử phạt vi phạm hành chính (NĐ 16/2022)
    {"decree": "339/2026/NĐ-CP", "correct_target": "16/2022/NĐ-CP", "rel_type": "AMENDS"},
]


class Neo4jRelationshipAuditor:
    """Audits and repairs Neo4j legal knowledge graph relationships."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        await self.driver.close()

    async def normalize_doc_numbers(self) -> int:
        """Fill missing doc_number properties on :Document nodes from id prefix."""
        query = """
        MATCH (d:Document)
        WHERE d.doc_number IS NULL OR d.doc_number = ''
        WITH d,
             CASE
               WHEN d.id STARTS WITH 'VBPL/' THEN replace(d.id, 'VBPL/', '')
               WHEN d.id STARTS WITH 'ROOT/' THEN replace(d.id, 'ROOT/', '')
               ELSE d.id
             END AS clean_num
        SET d.doc_number = clean_num
        RETURN count(d) as updated_count
        """
        async with self.driver.session() as session:
            res = await session.run(query)
            rec = await res.single()
            count = rec["updated_count"] if rec else 0
            logger.info(f"Normalized {count} Document nodes with missing doc_number.")
            return count

    async def repair_mismatched_decrees(self) -> List[Dict[str, Any]]:
        """Remove invalid REPLACES edges and attach correct AMENDS edges for 2026 decrees."""
        results = []
        async with self.driver.session() as session:
            # First clean up mismatched REPLACES edges from 207 to 06/2021
            cleanup_query = """
            MATCH (s:Document)-[r:REPLACES]->(t:Document)
            WHERE s.doc_number = '207/2026/NĐ-CP' AND (t.doc_number = '06/2021/NĐ-CP' OR t.id CONTAINS '06/2021')
            DELETE r
            RETURN count(r) as deleted
            """
            res = await session.run(cleanup_query)
            rec = await res.single()
            deleted = rec["deleted"] if rec else 0
            if deleted > 0:
                logger.info(f"Removed {deleted} erroneous REPLACES edge between 207/2026 and 06/2021.")

            # Ensure proper AMENDS relationships
            for item in DECREE_CORRECTIONS:
                decree = item["decree"]
                target = item["correct_target"]
                rel_type = item["rel_type"]

                upsert_query = f"""
                MATCH (s:Document) WHERE s.doc_number = $decree OR s.id = 'VBPL/' + $decree
                MATCH (t:Document) WHERE t.doc_number = $target OR t.id = 'VBPL/' + $target
                MERGE (s)-[r:{rel_type}]->(t)
                RETURN s.doc_number as source, type(r) as rel, t.doc_number as target
                """
                res = await session.run(upsert_query, decree=decree, target=target)
                rec = await res.single()
                if rec:
                    logger.info(f"Verified relationship: {rec['source']} -[:{rec['rel']}]-> {rec['target']}")
                    results.append({"source": rec["source"], "rel": rec["rel"], "target": rec["target"]})

        return results

    async def establish_transitional_relationships(self) -> List[Dict[str, Any]]:
        """Create GOVERNS_TRANSITIONAL edges between statute pairs with metadata."""
        created = []
        query = """
        MATCH (s:Document) WHERE s.doc_number = $source OR s.id = $source OR s.id = 'VBPL/' + $source OR s.id = 'ROOT/' + $source
        WITH s LIMIT 1
        MATCH (t:Document) WHERE t.doc_number = $target OR t.id = $target OR t.id = 'VBPL/' + $target OR t.id = 'ROOT/' + $target
        WITH s, t LIMIT 1
        MERGE (s)-[r:GOVERNS_TRANSITIONAL]->(t)
        SET r.cutoff_date = $cutoff_date,
            r.grace_period_end = $grace_period_end,
            r.condition = $condition
        RETURN s.doc_number as source, t.doc_number as target, properties(r) as props
        """
        async with self.driver.session() as session:
            for rule in TRANSITIONAL_RULES:
                res = await session.run(
                    query,
                    source=rule["source_doc_number"],
                    target=rule["target_doc_number"],
                    cutoff_date=rule["cutoff_date"],
                    grace_period_end=rule["grace_period_end"],
                    condition=rule["condition"],
                )
                rec = await res.single()
                if rec:
                    logger.info(
                        f"Established: {rec['source']} -[:GOVERNS_TRANSITIONAL {rec['props']}]-> {rec['target']}"
                    )
                    created.append({
                        "source": rec["source"],
                        "target": rec["target"],
                        "properties": rec["props"],
                    })
                else:
                    logger.warning(f"Could not connect {rule['source_doc_number']} -> {rule['target_doc_number']}")

        return created

    async def create_transitional_indexes(self):
        """Create Neo4j indexes for GOVERNS_TRANSITIONAL properties."""
        query = """
        CREATE INDEX IF NOT EXISTS FOR ()-[r:GOVERNS_TRANSITIONAL]-() ON (r.cutoff_date, r.grace_period_end)
        """
        async with self.driver.session() as session:
            try:
                await session.run(query)
                logger.info("Created relationship index on GOVERNS_TRANSITIONAL(cutoff_date, grace_period_end).")
            except Exception as e:
                logger.warning(f"Index creation notice: {e}")

    async def run_full_audit(self) -> Dict[str, Any]:
        """Execute full audit pipeline and return diagnostic dictionary."""
        normalized_count = await self.normalize_doc_numbers()
        decree_repairs = await self.repair_mismatched_decrees()
        transitional_edges = await self.establish_transitional_relationships()
        await self.create_transitional_indexes()

        # Query summary statistics
        stats_query = """
        MATCH ()-[r]->()
        RETURN type(r) as rel_type, count(r) as rel_count
        ORDER BY rel_count DESC
        """
        stats = {}
        async with self.driver.session() as session:
            res = await session.run(stats_query)
            async for r in res:
                stats[r["rel_type"]] = r["rel_count"]

        report = {
            "status": "SUCCESS",
            "normalized_nodes_count": normalized_count,
            "repaired_decree_relationships": decree_repairs,
            "transitional_relationships_created": transitional_edges,
            "graph_relationship_stats": stats,
        }
        return report


async def main():
    parser = argparse.ArgumentParser(description="Audit and Repair Neo4j Knowledge Graph Relationships")
    parser.add_argument("--json-out", type=Path, default=None, help="Save audit report to JSON file")
    args = parser.parse_args()

    settings = Settings()
    pwd = settings.NEO4J_PASSWORD.get_secret_value()
    # Support localhost fallback if container is mapped to host port 7687
    uri = "bolt://localhost:7687"

    auditor = Neo4jRelationshipAuditor(uri, settings.NEO4J_USER, pwd)
    try:
        report = await auditor.run_full_audit()
        print("\n" + "=" * 60)
        print("NEO4J RELATIONSHIP AUDIT SUMMARY")
        print("=" * 60)
        print(f"Normalized Document Nodes: {report['normalized_nodes_count']}")
        print(f"Repaired Decree Rel:      {len(report['repaired_decree_relationships'])}")
        print(f"Transitional Rel Created: {len(report['transitional_relationships_created'])}")
        print("\nRelationship Topology:")
        for k, v in report["graph_relationship_stats"].items():
            print(f"  - {k:22}: {v}")

        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n[OK] Saved report to {args.json_out}")
    finally:
        await auditor.close()


if __name__ == "__main__":
    asyncio.run(main())
