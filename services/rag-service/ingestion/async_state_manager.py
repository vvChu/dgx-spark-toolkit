"""Async PostgreSQL state manager using asyncpg.

Drop-in async replacement for PostgresStateManager. Uses raw asyncpg
connection pool (no SQLAlchemy) for maximum performance.

Usage:
    sm = AsyncStateManager()
    await sm.init()
    claimed = await sm.claim_file("path", "worker-1", hash="abc123")
"""
import asyncio
import hashlib
import json
import logging
import os
import re
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


def _parse_db_url(url: str) -> str:
    """Convert SQLAlchemy-style URL to asyncpg-compatible DSN.
    
    postgresql+psycopg2://user:pass@host:5432/db → postgresql://user:pass@host:5432/db
    """
    return re.sub(r'postgresql\+\w+://', 'postgresql://', url)


class AsyncStateManager:
    """Fully async state manager powered by asyncpg connection pool."""

    def __init__(self):
        raw_url = os.environ.get("DATABASE_URL", "")
        if not raw_url:
            raise RuntimeError("DATABASE_URL required for AsyncStateManager")
        self._dsn = _parse_db_url(raw_url)
        self._pool: Optional[asyncpg.Pool] = None

    async def init(self):
        """Initialize connection pool and schema. Call once at startup."""
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        await self._init_schema()
        logger.info("AsyncStateManager initialized (asyncpg pool)")

    async def close(self):
        if self._pool:
            await self._pool.close()

    # ── Schema ────────────────────────────────────────────────────────

    async def _init_schema(self):
        async with self._pool.acquire() as conn:
            await conn.execute("""
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
                CREATE INDEX IF NOT EXISTS idx_ingestion_status ON ingestion_state(status);
                CREATE INDEX IF NOT EXISTS idx_ingestion_claim ON ingestion_state(worker_id, claim_timestamp);
                CREATE INDEX IF NOT EXISTS idx_ingestion_docid ON ingestion_state(doc_id);
                CREATE INDEX IF NOT EXISTS idx_ingestion_completed ON ingestion_state(status, completed_timestamp);
            """)

    # ── Core Operations ───────────────────────────────────────────────

    async def claim_file(self, file_path: str, worker_id: str, content_hash: str = None, stale_minutes: int = 30) -> bool:
        """Atomic claim with row lock. Returns True if successfully claimed."""
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow("""
                    INSERT INTO ingestion_state (file_path, status, worker_id, claim_timestamp, content_hash)
                    VALUES ($1, 'CLAIMED', $2, NOW(), $3)
                    ON CONFLICT (file_path) DO UPDATE
                    SET status = 'CLAIMED', worker_id = $2, claim_timestamp = NOW(), updated_at = NOW(), content_hash = $3
                    WHERE ingestion_state.status = 'PENDING'
                       OR (ingestion_state.status = 'FAILED' AND ingestion_state.retry_count < 3)
                       OR (ingestion_state.status = 'CLAIMED'
                           AND ingestion_state.claim_timestamp < NOW() - make_interval(mins => $4))
                    RETURNING file_path;
                """, file_path, worker_id, content_hash, stale_minutes)
                return row is not None
            except Exception as e:
                logger.error(f"Error claiming file {file_path}: {e}")
                return False

    async def update_status(self, file_path: str, status: str, doc_id: str = None, metadata: dict = None, error: str = None):
        """Update the status of a file."""
        meta_json = json.dumps(metadata) if metadata else None
        async with self._pool.acquire() as conn:
            try:
                if status == 'FAILED':
                    await conn.execute("""
                        UPDATE ingestion_state 
                        SET status = $1, error_message = $2, updated_at = NOW(), 
                            retry_count = retry_count + 1
                        WHERE file_path = $3
                    """, status, error, file_path)
                else:
                    # Check doc_id collision
                    if doc_id:
                        collision = await conn.fetchrow(
                            "SELECT 1 FROM ingestion_state WHERE doc_id = $1 AND file_path != $2 LIMIT 1",
                            doc_id, file_path
                        )
                        if collision:
                            logger.info(f"doc_id collision: {doc_id}. Appending suffix.")
                            doc_id = f"{doc_id}_DUP_{hashlib.md5(file_path.encode()).hexdigest()[:6]}"

                    await conn.execute("""
                        UPDATE ingestion_state 
                        SET status = $1, 
                            doc_id = COALESCE($2, doc_id), 
                            metadata = COALESCE($3::jsonb, metadata),
                            completed_timestamp = CASE WHEN $1 = 'COMPLETED' THEN NOW() ELSE completed_timestamp END,
                            error_message = $4, 
                            updated_at = NOW()
                        WHERE file_path = $5
                    """, status, doc_id, meta_json, error, file_path)
            except Exception as e:
                logger.error(f"Error updating status for {file_path}: {e}")

    async def update_validity_status(self, doc_id: str, status: str):
        """Update the validity/legal status of a document."""
        if not doc_id:
            return
        async with self._pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE ingestion_state 
                    SET metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{validity_status}', $1::jsonb),
                        updated_at = NOW()
                    WHERE doc_id = $2
                """, json.dumps(status), doc_id)
            except Exception as e:
                logger.error(f"Error updating validity for {doc_id}: {e}")

    # ── Queries ───────────────────────────────────────────────────────

    async def get_existing_doc_hash(self, doc_id: str) -> Optional[str]:
        """Retrieve content_hash of a completed document by doc_id."""
        if not doc_id:
            return None
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT content_hash FROM ingestion_state WHERE doc_id = $1 AND status = 'COMPLETED' LIMIT 1",
                    doc_id
                )
                return row['content_hash'] if row and row['content_hash'] else None
            except Exception as e:
                logger.error(f"Error getting hash for {doc_id}: {e}")
                return None

    async def get_status(self, file_path: str) -> Optional[str]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM ingestion_state WHERE file_path = $1", file_path
            )
            return row['status'] if row else None

    async def get_all_state(self) -> dict:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT file_path, status, doc_id FROM ingestion_state")
            return {r['file_path']: {"status": r['status'], "doc_id": r['doc_id'] or "unknown"} for r in rows}

    async def get_status_summary(self) -> dict[str, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT status, COUNT(*) as cnt FROM ingestion_state GROUP BY status")
            return {r['status']: r['cnt'] for r in rows}

    # ── Admin ─────────────────────────────────────────────────────────

    async def reset_all(self):
        async with self._pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE ingestion_state")
            await conn.execute("TRUNCATE TABLE system_checkpoints")
            logger.info("Async ingestion state reset.")

    async def check_notification_milestone(self, milestone_step: int = 50):
        """Check if a new milestone has been reached."""
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow("""
                    WITH counts AS (
                        SELECT COUNT(*) as current_count FROM ingestion_state WHERE status = 'COMPLETED'
                    ), checkpoint AS (
                        SELECT coalesce((value->>'last_count')::int, 0) as last_count 
                        FROM system_checkpoints WHERE key = 'telegram_notified_count'
                    )
                    SELECT c.current_count, COALESCE(cp.last_count, 0) as last_count
                    FROM counts c LEFT JOIN checkpoint cp ON true
                """)
                if not row:
                    return None, None

                current, last = row['current_count'], row['last_count']
                if current < milestone_step or current < last + milestone_step:
                    return None, None

                files = await conn.fetch("""
                    SELECT file_path FROM ingestion_state 
                    WHERE status = 'COMPLETED' 
                    ORDER BY completed_timestamp DESC LIMIT $1
                """, milestone_step)
                file_list = [r['file_path'] for r in files]

                new_last = (current // milestone_step) * milestone_step
                await conn.execute("""
                    INSERT INTO system_checkpoints (key, value, updated_at)
                    VALUES ('telegram_notified_count', $1, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
                """, json.dumps({"last_count": new_last}))

                return current, file_list
            except Exception as e:
                logger.error(f"Milestone check error: {e}")
                return None, None

    # ── Monitoring ────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return {
                "status": "healthy",
                "pool_size": self._pool.get_size(),
                "pool_free": self._pool.get_idle_size(),
                "pool_min": self._pool.get_min_size(),
                "pool_max": self._pool.get_max_size(),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
