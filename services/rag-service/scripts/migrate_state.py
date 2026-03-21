import json
import os
import logging
from ingestion.state_manager import PostgresStateManager
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATE_FILE = "ingestion_state.json"

def migrate():
    if not os.path.exists(STATE_FILE):
        logger.info(f"No {STATE_FILE} found. Nothing to migrate.")
        return

    logger.info(f"Found {STATE_FILE}. Starting migration to PostgreSQL...")
    state_manager = PostgresStateManager()
    if not state_manager.engine:
        logger.error("Could not connect to database. Aborting migration.")
        return

    with open(STATE_FILE, "r") as f:
        try:
            old_state = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON state file.")
            return

    processed_files = old_state.get("processed_files", {})
    partial_failures = old_state.get("partial_failures", {})

    migrated_count = 0
    with state_manager.Session() as session:
        # Migrate processed files
        for rel_path_or_hash, timestamp in processed_files.items():
            # In old state, keys were hashes, but we don't have rel_paths easily for all of them.
            # If the json has hashes, we just use the hash as file_path for historical records.
            # Or we can just insert them as COMPLETED.
            session.execute(text("""
                INSERT INTO ingestion_state (file_path, status, completed_timestamp, created_at, updated_at)
                VALUES (:fp, 'COMPLETED', to_timestamp(:ts), NOW(), NOW())
                ON CONFLICT (file_path) DO NOTHING
            """), {"fp": rel_path_or_hash, "ts": timestamp})
            migrated_count += 1

        # Migrate partial failures
        for file_hash, fail_data in partial_failures.items():
            rel_path = fail_data.get("file", file_hash)
            err_msg = f"Failed pages: {fail_data.get('failed_pages', [])}"
            session.execute(text("""
                INSERT INTO ingestion_state (file_path, status, error_message, created_at, updated_at)
                VALUES (:fp, 'FAILED', :err, NOW(), NOW())
                ON CONFLICT (file_path) DO UPDATE SET status = 'FAILED', error_message = :err
            """), {"fp": rel_path, "err": err_msg})
            migrated_count += 1

        session.commit()
    logger.info(f"Successfully migrated {migrated_count} records to PostgreSQL.")

if __name__ == "__main__":
    migrate()
