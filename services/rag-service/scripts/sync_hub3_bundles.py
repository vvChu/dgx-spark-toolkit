#!/usr/bin/env python3
"""CLI Runner: Connect Hub 3 OKF v2.4 Gazette Bundles to Ingestion Pipeline & Neo4j.

Usage:
    python scripts/sync_hub3_bundles.py [OPTIONS]

Options:
    --hub3-path PATH    Path to Hub 3 (ccba-legal-knowledge) repository
    --category CAT      Filter by category (01_vbpl, 02_qcvn, 03_tcvn, 04_appendices)
    --limit N           Limit processing to first N bundles
    --dry-run           Simulate operations without writing to Neo4j or queue
    --verify-sha        Run streaming 64KB cryptographic SHA-256 verification
    --sync-neo4j        Synchronize legal topology and document status to Neo4j
    --enqueue           Enqueue bundles into Redis IngestionQueue
    --verbose           Enable debug logging
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add service directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = SCRIPT_DIR.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from ingestion.hub3_bridge import Hub3Bridge, Hub3BundleInfo, ShaVerificationStatus
from ingestion.pipeline_config import (
    HUB3_LEGAL_PATH,
    NEO4J_PASS,
    NEO4J_URI,
    NEO4J_USER,
)

logger = logging.getLogger("sync_hub3_bundles")


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Synchronize Hub 3 OKF v2.4 Gazette Bundles into DGX Spark RAG pipeline."
    )
    parser.add_argument(
        "--hub3-path",
        default=os.getenv("HUB3_LEGAL_PATH", HUB3_LEGAL_PATH),
        help="Path to ccba-legal-knowledge repository",
    )
    parser.add_argument(
        "--category",
        choices=["01_vbpl", "02_qcvn", "03_tcvn", "04_appendices"],
        default=None,
        help="Filter bundles by category",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of bundles to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (do not commit changes to Neo4j or Redis)",
    )
    parser.add_argument(
        "--verify-sha",
        action="store_true",
        help="Verify streaming 64KB SHA-256 against expected hash (ADR-0059)",
    )
    parser.add_argument(
        "--sync-neo4j",
        action="store_true",
        help="Synchronize document status and topology to Neo4j",
    )
    parser.add_argument(
        "--enqueue",
        action="store_true",
        help="Push bundles into Redis IngestionQueue",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging",
    )
    return parser.parse_args(args)


async def sync_to_neo4j(bridge: Hub3Bridge, bundles: List[Hub3BundleInfo]) -> Dict[str, int]:
    """Execute Neo4j synchronization with Neo4jRepository."""
    from neo4j import AsyncGraphDatabase
    from repositories.neo4j_repo import Neo4jRepository

    logger.info("Connecting to Neo4j at %s ...", NEO4J_URI)
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    try:
        repo = Neo4jRepository(driver)
        await repo.init_schema()
        result = await bridge.sync_topology_to_neo4j(bundles, repo)
        logger.info(
            "Neo4j Topology Sync complete: %d nodes, %d replaces, %d amends",
            result["nodes_synced"],
            result["replaces_created"],
            result["amends_created"],
        )
        return result
    finally:
        await driver.close()


def run_enqueue(bridge: Hub3Bridge, bundles: List[Hub3BundleInfo]) -> int:
    """Enqueue bundles into IngestionQueue."""
    from ingestion.ingestion_queue import IngestionQueue

    queue = IngestionQueue()
    count = bridge.enqueue_batch(bundles, queue)
    logger.info("Successfully enqueued %d bundles into IngestionQueue", count)
    return count


def main(argv: Optional[List[str]] = None) -> int:
    """Main execution function."""
    args = parse_args(argv)
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Initializing Hub3Bridge at: %s", args.hub3_path)
    bridge = Hub3Bridge(hub3_path=args.hub3_path)

    # 1. Load Master Catalog
    logger.info(
        "Loading Master Catalog (category=%s, limit=%s)...",
        args.category or "ALL",
        args.limit or "ALL",
    )
    bundles = bridge.load_master_catalog(category=args.category, limit=args.limit)
    logger.info("Discovered %d bundles.", len(bundles))

    if not bundles:
        logger.warning("No bundles found matching criteria.")
        return 0

    # 2. SHA-256 Cryptographic Verification (ADR-0059)
    # Automatically enabled if --enqueue or --sync-neo4j is active (Hard Security Gate)
    if args.enqueue or args.sync_neo4j:
        args.verify_sha = True

    should_verify_sha = args.verify_sha
    if should_verify_sha:
        logger.info("Running streaming 64KB SHA-256 verification on %d bundles...", len(bundles))
        sha_stats = {
            ShaVerificationStatus.VERIFIED.value: 0,
            ShaVerificationStatus.TAMPERED.value: 0,
            ShaVerificationStatus.NO_SOURCE.value: 0,
            ShaVerificationStatus.NON_STATUTORY.value: 0,
        }
        tampered_bundles: List[Hub3BundleInfo] = []
        for b in bundles:
            status = bridge.verify_bundle_sha256(b)
            sha_stats[status] = sha_stats.get(status, 0) + 1
            if status == ShaVerificationStatus.TAMPERED.value:
                tampered_bundles.append(b)
                logger.critical(
                    "SECURITY GATE BREACH: Bundle %s (%s) is TAMPERED! Hash mismatch on %s",
                    b.slug,
                    b.document_number,
                    b.pdf_path,
                )
            elif args.verbose:
                logger.debug("[%s] %s: %s", status, b.slug, b.canonical_id)

        print("\n--- SHA-256 Cryptographic Verification Report (ADR-0059) ---")
        for k, v in sha_stats.items():
            print(f"  {k:15s}: {v:3d}")
        print("------------------------------------------------------------\n")

        if tampered_bundles:
            is_production = os.getenv("ENVIRONMENT") == "production" or os.getenv("PRODUCTION_MODE", "0") == "1"
            if is_production:
                raise RuntimeError(
                    f"Production Security Gate: Aborting sync due to {len(tampered_bundles)} TAMPERED bundles."
                )
            logger.warning(
                "Hard Security Gate: Removing %d TAMPERED bundles from sync pipeline.",
                len(tampered_bundles),
            )
            tampered_slugs = {b.slug for b in tampered_bundles}
            bundles = [b for b in bundles if b.slug not in tampered_slugs]

    if not bundles:
        logger.warning("No valid bundles found matching criteria.")
        return 0

    # Build canonical ID map
    id_map = bridge.build_canonical_id_map(bundles)
    logger.info("Constructed Bidirectional ID Resolver map with %d alias entries", len(id_map))

    # 3. Dry-Run Check
    if args.dry_run:
        print("[DRY RUN] Summary of bundles to synchronize:")
        for idx, b in enumerate(bundles[:10], 1):
            replaces_str = f"replaces {b.replaces}" if b.replaces else "no replaces"
            amends_str = f"amends {b.amends}" if b.amends else ""
            print(f"  {idx:2d}. [{b.validity_status:8s}] {b.canonical_id:32s} ({replaces_str} {amends_str})")
        if len(bundles) > 10:
            print(f"  ... and {len(bundles) - 10} more bundles.")
        print("\n[DRY RUN] Completed without remote side-effects.")
        return 0

    # 4. Neo4j Topology Sync
    if args.sync_neo4j:
        logger.info("Syncing %d bundles to Neo4j...", len(bundles))
        try:
            res = asyncio.run(sync_to_neo4j(bridge, bundles))
            print("\n--- Neo4j Knowledge Graph Sync Report ---")
            print(f"  Nodes synchronized    : {res['nodes_synced']}")
            print(f"  Replaces relationships: {res['replaces_created']}")
            print(f"  Amends relationships  : {res['amends_created']}")
            print("-----------------------------------------\n")
        except Exception as e:
            logger.error("Neo4j synchronization failed: %s", e)
            return 1

    # 5. Enqueue into Redis IngestionQueue
    if args.enqueue:
        logger.info("Enqueueing %d bundles into IngestionQueue...", len(bundles))
        try:
            count = run_enqueue(bridge, bundles)
            print(f"\n[ENQUEUE] Enqueued {count} bundles into IngestionQueue.\n")
        except Exception as e:
            logger.error("Enqueue failed: %s", e)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
