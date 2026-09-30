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
from dotenv import load_dotenv

# Add service directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = SCRIPT_DIR.parent
ROOT_DIR = SERVICE_DIR.parent.parent

# Load local environment configuration
load_dotenv()
load_dotenv(ROOT_DIR / ".env")

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
        "--ingest-milvus",
        action="store_true",
        help="Embed and ingest chunks directly into Milvus collection (Verdict B')",
    )
    parser.add_argument(
        "--milvus-collection",
        default=os.getenv("MILVUS_OKF_COLLECTION", "legal_docs_v12_okf"),
        help="Milvus collection name for OKF chunks (default: legal_docs_v12_okf)",
    )
    parser.add_argument(
        "--milvus-host",
        default=os.getenv("MILVUS_HOST", "127.0.0.1"),
        help="Milvus host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--milvus-port",
        default=os.getenv("MILVUS_PORT", "19530"),
        help="Milvus port (default: 19530)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding inference and Milvus insertion (default: 32)",
    )
    parser.add_argument(
        "--force-cpu-embedding",
        action="store_true",
        help="Force CPU execution for BGE-M3 embedding",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687" if not os.path.exists("/.dockerenv") else NEO4J_URI),
        help="Neo4j connection URI (default: bolt://127.0.0.1:7687 on host, bolt://neo4j-graph:7687 in container)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose DEBUG logging",
    )
    return parser.parse_args(args)


async def sync_to_neo4j(
    bridge: Hub3Bridge,
    bundles: List[Hub3BundleInfo],
    uri: Optional[str] = None,
) -> Dict[str, int]:
    """Execute Neo4j synchronization with Neo4jRepository."""
    from neo4j import AsyncGraphDatabase
    from repositories.neo4j_repo import Neo4jRepository

    target_uri = uri or NEO4J_URI
    target_user = os.getenv("NEO4J_USER", NEO4J_USER) or "neo4j"
    target_pass = os.getenv("NEO4J_PASSWORD") or NEO4J_PASS
    logger.info("Connecting to Neo4j at %s (user: %s)...", target_uri, target_user)
    driver = AsyncGraphDatabase.driver(target_uri, auth=(target_user, target_pass))
    try:
        repo = Neo4jRepository(driver)
        await repo.init_schema()
        result = await bridge.sync_topology_to_neo4j(bundles, repo)
        logger.info(
            "Neo4j Topology Sync complete: %d nodes, %d replaces, %d amends, %d guides",
            result["nodes_synced"],
            result["replaces_created"],
            result["amends_created"],
            result.get("guides_created", 0),
        )
        return result
    finally:
        await driver.close()


def run_ingest_milvus(
    bridge: Hub3Bridge,
    bundles: List[Hub3BundleInfo],
    id_map: Dict[str, str],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Batch embed and ingest OKF chunks into dedicated Milvus collection (Verdict B')."""
    import time
    from pymilvus import MilvusClient, DataType
    from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding

    col_name = args.milvus_collection
    milvus_uri = f"http://{args.milvus_host}:{args.milvus_port}"
    logger.info("Connecting to Milvus at %s (target collection: %s)...", milvus_uri, col_name)
    client = MilvusClient(uri=milvus_uri)

    # 1. Ensure hybrid collection schema exists
    if not client.has_collection(col_name):
        logger.info("Creating Milvus collection '%s' with native hybrid schema...", col_name)
        schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
        index_params.add_index(field_name="sparse_vector", metric_type="IP", index_type="SPARSE_INVERTED_INDEX")

        client.create_collection(
            collection_name=col_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info("Collection '%s' created successfully.", col_name)
    else:
        logger.info("Milvus collection '%s' already exists.", col_name)

    # 2. Extract standardized OKF chunks from all bundles
    logger.info("Chunking %d bundles using OKF Anchor-Based Chunker...", len(bundles))
    t0_chunk = time.time()
    bundle_chunks: List[tuple[Hub3BundleInfo, Any]] = []
    total_raw_chunks = 0
    for b in bundles:
        proc_doc = bridge.convert_bundle_to_processed_doc(b, canonical_map=id_map)
        for c in proc_doc.chunks:
            bundle_chunks.append((b, c))
        total_raw_chunks += len(proc_doc.chunks)

    chunk_dur = time.time() - t0_chunk
    logger.info("Extracted %d chunks from %d bundles in %.3f seconds.", total_raw_chunks, len(bundles), chunk_dur)

    # 3. Initialize BGE-M3 Embedder
    if args.force_cpu_embedding:
        os.environ["FORCE_CPU_EMBEDDING"] = "1"
    logger.info("Initializing BGE-M3 Hybrid Embedder...")
    embedder = BGE_M3_HybridEmbedding()

    # 4. Batch Embed and Insert
    logger.info("Beginning batch embedding and insertion (batch_size=%d)...", args.batch_size)
    t0_embed = time.time()
    total_inserted = 0
    batch_size = max(1, args.batch_size)

    for i in range(0, len(bundle_chunks), batch_size):
        batch = bundle_chunks[i:i + batch_size]
        texts = [c.text for _, c in batch]

        # Embed batch
        emb_res = embedder.embed_documents(texts, batch_size=batch_size)
        dense_vecs = emb_res["dense"]
        sparse_vecs = emb_res["sparse"]

        entities = []
        for idx_in_batch, (b, c) in enumerate(batch):
            sparse_raw = sparse_vecs[idx_in_batch]
            clean_sparse: Dict[int, float] = {}
            if isinstance(sparse_raw, dict):
                for k, v in sparse_raw.items():
                    try:
                        ik = int(k)
                        if ik >= 0:
                            clean_sparse[ik] = float(v)
                    except (ValueError, TypeError):
                        continue

            entities.append({
                "text": str(c.text)[:14000],
                "source": str(c.source),
                "page": int(c.page),
                "summary": str(c.hierarchy_path or "")[:2048],
                "doc_date": str(b.effective_date or b.issued_date or "unknown"),
                "doc_type": str(b.doc_type or "unknown"),
                "authority": str(b.issued_by or "unknown"),
                "file_hash": str(b.pdf_sha256 or ""),
                "is_table": bool(c.is_table),
                "chunk_type": str(c.chunk_type),
                "parent_id": str(c.parent_id),
                "doc_number": str(c.doc_number),
                "doc_id": str(c.doc_id),
                "chunk_id": str(c.chunk_id),
                "bbox": str(c.bbox),
                "validity_status": str(c.validity_status),
                "legal_level": str(b.category),
                "hierarchy_path": str(c.hierarchy_path),
                "citation_count": 0,
                "project_code": "LEGAL_OKF",
                "discipline": "LEGAL",
                "doc_status": str(b.validity_status),
                "revision": 0,
                "synthetic_queries": "",
                "source_category": str(b.category),
                "vector": dense_vecs[idx_in_batch],
                "sparse_vector": clean_sparse,
            })

        if entities:
            client.insert(collection_name=col_name, data=entities)
            total_inserted += len(entities)

        if (i // batch_size + 1) % 10 == 0 or total_inserted == len(bundle_chunks):
            logger.info("Inserted %d/%d chunks (%.1f%%)...", total_inserted, len(bundle_chunks), (total_inserted / len(bundle_chunks)) * 100)

    embed_dur = time.time() - t0_embed
    logger.info("Loading collection '%s' into Milvus memory...", col_name)
    client.load_collection(col_name)

    stats = client.get_collection_stats(col_name)
    logger.info("Milvus collection '%s' stats: %s", col_name, stats)

    return {
        "collection": col_name,
        "bundles_count": len(bundles),
        "chunks_count": total_inserted,
        "chunk_duration_sec": chunk_dur,
        "embed_duration_sec": embed_dur,
        "stats": stats,
    }


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
            res = asyncio.run(sync_to_neo4j(bridge, bundles, uri=args.neo4j_uri))
            print("\n--- Neo4j Knowledge Graph Sync Report ---")
            print(f"  Nodes synchronized    : {res['nodes_synced']}")
            print(f"  Replaces relationships: {res['replaces_created']}")
            print(f"  Amends relationships  : {res['amends_created']}")
            print(f"  Guides relationships  : {res.get('guides_created', 0)}")
            print("-----------------------------------------\n")
        except Exception as e:
            logger.error("Neo4j synchronization failed: %s", e)
            return 1

    # 5. Milvus OKF Chunks Batch Ingestion (Verdict B')
    if args.ingest_milvus:
        logger.info("Beginning batch Milvus ingestion into '%s'...", args.milvus_collection)
        try:
            m_res = run_ingest_milvus(bridge, bundles, id_map, args)
            print("\n--- Milvus Knowledge Ingestion Report (Verdict B') ---")
            print(f"  Target Collection     : {m_res['collection']}")
            print(f"  Bundles Processed     : {m_res['bundles_count']}")
            print(f"  Total Chunks Inserted : {m_res['chunks_count']}")
            print(f"  Chunking Duration     : {m_res['chunk_duration_sec']:.2f}s")
            print(f"  Embedding Duration    : {m_res['embed_duration_sec']:.2f}s")
            print(f"  Collection Stats      : {m_res['stats']}")
            print("------------------------------------------------------\n")
        except Exception as e:
            logger.error("Milvus ingestion failed: %s", e)
            return 1

    # 6. Enqueue into Redis IngestionQueue
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
