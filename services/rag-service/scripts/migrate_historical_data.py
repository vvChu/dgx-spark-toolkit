import os
import sys
import hashlib
import logging
import asyncio
import json
import argparse
from sqlalchemy import text

# Add parent directories to path to import core and services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings
from core.database import state, lifespan
from ingestion.state_manager import PostgresStateManager
from services.lifecycle_service import LifecycleService
from repositories.neo4j_repo import Neo4jRepository
from repositories.milvus_repo import MilvusRepository

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SOURCE_DIR = "/app/data/legal_docs_source"


def get_file_hash(file_path):
    """MD5 hash logic matching pipeline.py"""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Error hashing {file_path}: {e}")
        return None


async def migrate(dry_run=True):
    settings = get_settings()

    # 1. Initialize DB connections using the existing lifespan logic (mocking FastAPI app)
    class MockApp:
        class State:
            pass
        state = State()

    app = MockApp()
    async with lifespan(app):
        state_mgr = app.state.state_manager
        neo4j_repo = Neo4jRepository(app.state.neo4j_driver)
        milvus_repo = MilvusRepository(app.state.milvus_client)
        lifecycle = LifecycleService(state_mgr, milvus_repo, neo4j_repo)

        logger.info(f"=== Starting Migration Utility (Dry Run: {dry_run}) ===")

        # PHASE 1: Backfill content_hash in Postgres
        logger.info("PHASE 1: Backfilling content_hash in PostgreSQL...")
        with state_mgr.Session() as session:
            # Find records where content_hash is null and status is COMPLETED
            result = session.execute(text(
                "SELECT file_path, doc_id FROM ingestion_state WHERE content_hash IS NULL AND status = 'COMPLETED'"
            ))
            records = result.fetchall()

            logger.info(f"Found {len(records)} records needing content_hash backfill.")

            for rel_path, doc_id in records:
                abs_path = os.path.join(SOURCE_DIR, rel_path)
                if not os.path.exists(abs_path):
                    logger.warning(f"  Orphan detected: {rel_path} (doc_id: {doc_id}) not found on disk.")
                    continue

                file_hash = get_file_hash(abs_path)
                if file_hash:
                    if not dry_run:
                        session.execute(text(
                            "UPDATE ingestion_state SET content_hash = :hash WHERE file_path = :path"
                        ), {"hash": file_hash, "path": rel_path})
                        logger.info(f"  Updated hash for {rel_path} -> {file_hash}")
                    else:
                        logger.info(f"  [DRY RUN] Would update hash for {rel_path} -> {file_hash}")

            if not dry_run:
                session.commit()

        # PHASE 2: Sync OUTDATED status based on Neo4j REPLACES relationships
        logger.info("\nPHASE 2: Syncing OUTDATED status from Neo4j topology...")

        # Query Neo4j for all destination nodes of REPLACES relationships
        # We want to find documents that SHOULD be outdated but might not be marked so in all stores.
        query = """
        MATCH (new:Document)-[:REPLACES]->(old:Document)
        RETURN old.id as outdated_id, new.id as newer_id
        """

        async with app.state.neo4j_driver.session() as session:
            result = await session.run(query)
            records = await result.data()

            logger.info(f"Found {len(records)} replacement links in Knowledge Graph.")

            for rec in records:
                old_id = rec["outdated_id"]
                new_id = rec["newer_id"]

                # Check status in Postgres (metadata column)
                with state_mgr.Session() as pg_session:
                    pg_res = pg_session.execute(text(
                        "SELECT metadata->>'validity_status' FROM ingestion_state WHERE doc_id = :doc_id LIMIT 1"
                    ), {"doc_id": old_id}).fetchone()

                    current_status = pg_res[0] if pg_res else "UNKNOWN"

                if current_status != "OUTDATED":
                    logger.info(f"  Document {old_id} (replaced by {new_id}) is currently {current_status}. Syncing to OUTDATED...")
                    if not dry_run:
                        try:
                            res = await lifecycle.sync_document_status(old_id, "OUTDATED")
                            logger.info(f"  Sync Result: {res.get('status')}")
                        except Exception as e:
                            logger.error(f"  Failed to sync status for {old_id}: {e}")
                    else:
                        logger.info(f"  [DRY RUN] Would sync {old_id} to OUTDATED across all stores.")
                else:
                    logger.info(f"  Document {old_id} is already marked OUTDATED. Skipping.")

        logger.info("\n=== Migration Utility Finished ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate historical RAG data.")
    parser.add_argument("--execute", action="store_true", help="Execute the migration (default is dry-run)")
    args = parser.parse_args()

    asyncio.run(migrate(dry_run=not args.execute))
