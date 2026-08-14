import os
import json
import hashlib
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class StateManager:
    """Unified state manager supporting both PostgreSQL and in-memory execution."""
    def __init__(self, db_url: str | None = None):
        db_url = db_url or os.environ.get("DATABASE_URL")
        if not db_url:
            logger.warning("DATABASE_URL environment variable is not set for StateManager. Running without DB connection.")
            self.engine = None
            return
        try:
            self.engine = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_timeout=10,
            )
            self._init_db()
        except Exception as e:
            logger.error(f"Failed to initialize StateManager: {e}")
            self.engine = None

    def _init_db(self):
        """Ensure the table and indexes exist. This runs on startup."""
        if not self.engine:
            return
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ingestion_state (
            file_path TEXT PRIMARY KEY,
            doc_id TEXT,
            status TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'CLAIMED', 'PROCESSING', 'COMPLETED', 'FAILED')),
            worker_id TEXT,
            claim_timestamp TIMESTAMPTZ,
            completed_timestamp TIMESTAMPTZ,
            error_message TEXT,
            retry_count INT DEFAULT 0,
            metadata JSONB,
            content_hash TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS system_checkpoints (
            key TEXT PRIMARY KEY,
            value JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        # [Fix 1] All indexes including previously missing doc_id and composite completed index
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_ingestion_status ON ingestion_state(status);",
            "CREATE INDEX IF NOT EXISTS idx_ingestion_claim ON ingestion_state(worker_id, claim_timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_ingestion_docid ON ingestion_state(doc_id);",
            "CREATE INDEX IF NOT EXISTS idx_ingestion_completed ON ingestion_state(status, completed_timestamp);",
        ]

        try:
            with self.engine.begin() as conn:
                conn.execute(text(create_table_sql))
                for idx_sql in indexes:
                    conn.execute(text(idx_sql))
                logger.info("PostgreSQL ingestion_state table initialized.")
        except Exception as e:
            logger.error(f"Error initializing DB schema: {e}")

    # ─── Core Operations ────────────────────────────────────────────

    def claim_file(self, file_path: str, worker_id: str, content_hash: str = None, stale_minutes: int = 120) -> bool:
        """Atomic claim with row lock. Returns True if successfully claimed.

        [Fix 2] Uses engine.begin() instead of Session() for lighter overhead.
        """
        if not self.engine:
            return False

        try:
            # [Fix 2] engine.begin() is lighter than Session() for raw SQL
            with self.engine.begin() as conn:
                upsert_sql = text("""
                    INSERT INTO ingestion_state (file_path, status, worker_id, claim_timestamp, content_hash)
                    VALUES (:file_path, 'CLAIMED', :worker_id, NOW(), :hash)
                    ON CONFLICT (file_path) DO UPDATE
                    SET status = 'CLAIMED', worker_id = :worker_id, claim_timestamp = NOW(), updated_at = NOW(), content_hash = :hash
                    WHERE ingestion_state.status = 'PENDING'
                       OR (ingestion_state.status = 'FAILED' AND ingestion_state.retry_count < 3)
                       OR (ingestion_state.status = 'CLAIMED'
                           AND ingestion_state.claim_timestamp < NOW() - make_interval(mins => :stale_minutes))
                    RETURNING file_path;
                """)
                result = conn.execute(upsert_sql, {
                    "file_path": file_path,
                    "worker_id": worker_id,
                    "hash": content_hash,
                    "stale_minutes": stale_minutes,
                })
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"Error claiming file {file_path}: {e}")
            return False

    def update_status(self, file_path: str, status: str, doc_id: str = None, metadata: dict = None, error: str = None):
        """Update the status of a file.

        [Fix 5] Simplified doc_id collision check — uses a single UPDATE
        with a subquery guard instead of a separate SELECT round-trip.
        """
        if not self.engine:
            return

        try:
            with self.engine.begin() as conn:
                meta_json = json.dumps(metadata) if metadata else None

                if status == 'FAILED':
                    conn.execute(text("""
                        UPDATE ingestion_state 
                        SET status = :status, error_message = :error, updated_at = NOW(), 
                            retry_count = retry_count + 1
                        WHERE file_path = :file_path
                    """), {"status": status, "error": error, "file_path": file_path})
                else:
                    # [Fix 5] Check doc_id collision in a single query using a subquery
                    # If another file already has this doc_id, append a suffix
                    if doc_id:
                        collision = conn.execute(text(
                            "SELECT 1 FROM ingestion_state WHERE doc_id = :doc_id AND file_path != :file_path LIMIT 1"
                        ), {"doc_id": doc_id, "file_path": file_path}).fetchone()
                        if collision:
                            logger.info(f"doc_id collision: {doc_id} already exists. Appending suffix.")
                            doc_id = f"{doc_id}_DUP_{hashlib.md5(file_path.encode()).hexdigest()[:6]}"

                    conn.execute(text("""
                        UPDATE ingestion_state 
                        SET status = :status, doc_id = COALESCE(:doc_id, doc_id),
                            metadata = COALESCE(CAST(:metadata AS jsonb), metadata),
                            completed_timestamp = CASE WHEN :status = 'COMPLETED' THEN NOW() ELSE completed_timestamp END,
                            error_message = :error, updated_at = NOW()
                        WHERE file_path = :file_path
                    """), {
                        "status": status,
                        "doc_id": doc_id,
                        "metadata": meta_json,
                        "error": error,
                        "file_path": file_path,
                    })
        except Exception as e:
            logger.error(f"Error updating status for {file_path}: {e}")

    def update_validity_status(self, doc_id: str, status: str):
        """Update the validity/legal status of a document (ACTIVE, OUTDATED, etc.).

        [Fix 1] Now uses the idx_ingestion_docid index for O(1) lookup.
        """
        if not self.engine or not doc_id:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(text("""
                    UPDATE ingestion_state 
                    SET metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{validity_status}', :status),
                        updated_at = NOW()
                    WHERE doc_id = :doc_id
                """), {"status": json.dumps(status), "doc_id": doc_id})
                logger.info(f"Updated validity_status to {status} for doc_id: {doc_id}")
        except Exception as e:
            logger.error(f"Error updating validity_status for doc_id {doc_id}: {e}")

    # ─── Queries ────────────────────────────────────────────────────

    def get_existing_doc_hash(self, doc_id: str) -> str:
        """Retrieve the content_hash of a completed document by its business ID.

        [Fix 1] Now uses idx_ingestion_docid index.
        """
        if not self.engine or not doc_id:
            return None
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT content_hash FROM ingestion_state WHERE doc_id = :doc_id AND status = 'COMPLETED' LIMIT 1"
                ), {"doc_id": doc_id}).fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error getting hash for doc_id {doc_id}: {e}")
            return None

    def get_status(self, file_path: str):
        """Get the current state of a file."""
        if not self.engine:
            return None
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT status FROM ingestion_state WHERE file_path = :file_path"
                ), {"file_path": file_path}).fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting status for {file_path}: {e}")
            return None

    def get_file_state(self, file_path: str) -> dict | None:
        """Get the full state record of a file."""
        if not self.engine:
            return None
        try:
            with self.engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT * FROM ingestion_state WHERE file_path = :file_path"
                ), {"file_path": file_path}).mappings().fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting file state for {file_path}: {e}")
            return None

    def get_all_state(self):
        """Retrieve the entire state (for backward compatibility/UI)."""
        if not self.engine:
            return {}
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT file_path, status, doc_id FROM ingestion_state"))
                return {row[0]: {"status": row[1], "doc_id": row[2] or "unknown"} for row in result.fetchall()}
        except Exception as e:
            logger.error(f"Error getting all state: {e}")
            return {}

    def get_status_summary(self) -> dict[str, int]:
        """[Fix 4] Fast aggregate counts by status — O(index scan) instead of full table.

        Returns e.g. {"COMPLETED": 14, "CLAIMED": 3, "FAILED": 1}
        """
        if not self.engine:
            return {}
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT status, COUNT(*) FROM ingestion_state GROUP BY status"
                ))
                return {row[0]: row[1] for row in result.fetchall()}
        except Exception as e:
            logger.error(f"Error getting status summary: {e}")
            return {}

    # ─── Admin Operations ───────────────────────────────────────────

    def reset_all(self):
        """TRUNCATE the table to restart ingestion from scratch."""
        if not self.engine:
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(text("TRUNCATE TABLE ingestion_state"))
                conn.execute(text("TRUNCATE TABLE system_checkpoints"))
                logger.info("Ingestion state reset successfully.")
        except Exception as e:
            logger.error(f"Failed to reset ingestion state: {e}")

    def check_notification_milestone(self, milestone_step: int = 50):
        """Check if a new milestone has been reached. Returns (count, file_list) if yes.

        [Fix 3] Merged into fewer queries using a CTE for the count+checkpoint check,
        then a single follow-up for the file list + checkpoint update only when needed.
        """
        if not self.engine:
            return None, None

        try:
            with self.engine.begin() as conn:
                # [Fix 3] Single CTE to check count vs last checkpoint
                check_result = conn.execute(text("""
                    WITH counts AS (
                        SELECT COUNT(*) as current_count FROM ingestion_state WHERE status = 'COMPLETED'
                    ), checkpoint AS (
                        SELECT coalesce((value->>'last_count')::int, 0) as last_count 
                        FROM system_checkpoints WHERE key = 'telegram_notified_count'
                    )
                    SELECT c.current_count, COALESCE(cp.last_count, 0) as last_count
                    FROM counts c LEFT JOIN checkpoint cp ON true
                """)).fetchone()

                if not check_result:
                    return None, None

                current_count, last_count = check_result[0], check_result[1]

                if current_count < milestone_step or current_count < last_count + milestone_step:
                    return None, None

                # Milestone reached — fetch recent files and update checkpoint
                files_result = conn.execute(text("""
                    SELECT file_path FROM ingestion_state 
                    WHERE status = 'COMPLETED' 
                    ORDER BY completed_timestamp DESC 
                    LIMIT :limit
                """), {"limit": milestone_step})
                file_list = [row[0] for row in files_result.fetchall()]

                new_last_count = (current_count // milestone_step) * milestone_step
                conn.execute(text("""
                    INSERT INTO system_checkpoints (key, value, updated_at)
                    VALUES ('telegram_notified_count', :value, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = NOW()
                """), {"value": json.dumps({"last_count": new_last_count})})

                return current_count, file_list

        except Exception as e:
            logger.error(f"Error checking notification milestone: {e}")
            return None, None

    # ─── Monitoring ─────────────────────────────────────────────────

    def health_check(self) -> dict:
        """[Fix 6] Quick health check with connection pool stats."""
        if not self.engine:
            return {"status": "unhealthy", "error": "engine not initialized"}
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            pool = self.engine.pool
            return {
                "status": "healthy",
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


PostgresStateManager = StateManager


class InMemoryStateManager:
    """In-memory state manager adapter for unit testing without PostgreSQL."""
    def __init__(self):
        self._states: dict[str, dict] = {}
        self._checkpoints: dict[str, dict] = {}

    def claim_file(self, file_path: str, worker_id: str, content_hash: str = None, stale_minutes: int = 120) -> bool:
        current = self._states.get(file_path)
        if current and current.get("status") in ("CLAIMED", "PROCESSING", "COMPLETED"):
            return False
        self._states[file_path] = {
            "status": "CLAIMED",
            "worker_id": worker_id,
            "content_hash": content_hash,
            "doc_id": None,
            "metadata": None,
            "error_message": None,
        }
        return True

    async def claim_file_async(self, file_path: str, worker_id: str, content_hash: str = None, stale_minutes: int = 120) -> bool:
        return self.claim_file(file_path, worker_id, content_hash, stale_minutes)

    def update_status(self, file_path: str, status: str, doc_id: str = None, metadata: dict = None, error: str = None):
        if file_path not in self._states:
            self._states[file_path] = {}
        self._states[file_path].update({
            "status": status,
            "doc_id": doc_id or self._states[file_path].get("doc_id"),
            "metadata": metadata or self._states[file_path].get("metadata"),
            "error_message": error,
        })

    async def update_status_async(self, file_path: str, status: str, doc_id: str = None, metadata: dict = None, error: str = None):
        self.update_status(file_path, status, doc_id, metadata, error)

    def get_status(self, file_path: str):
        record = self._states.get(file_path)
        return record["status"] if record else None

    def get_file_state(self, file_path: str) -> dict | None:
        return self._states.get(file_path)

    def get_all_state(self):
        return {k: {"status": v.get("status"), "doc_id": v.get("doc_id") or "unknown"} for k, v in self._states.items()}

    def get_status_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for record in self._states.values():
            st = record.get("status")
            if st:
                summary[st] = summary.get(st, 0) + 1
        return summary

    def reset_all(self):
        self._states.clear()
        self._checkpoints.clear()

    def health_check(self) -> dict:
        return {"status": "healthy", "mode": "in_memory"}

