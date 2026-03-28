"""Redis Streams queue for distributed work coordination.

Replaces filesystem polling + PostgreSQL claim_file() with an atomic,
ordered, consumer-group-based work queue.

Architecture:
  - Producer: file watcher → redis.xadd("ingest:queue", ...)
  - Consumer: worker → redis.xreadgroup("ingest:queue", group, consumer_id)
  - ACK: after successful processing → redis.xack(...)

Uses litellm-redis on DB 1 (DB 0 is reserved for LiteLLM).
"""
import logging
import os
import time
from typing import Optional

import redis

from prometheus_client import Gauge

logger = logging.getLogger(__name__)

# Metrics
QUEUE_DEPTH = Gauge('rag_queue_depth', 'Number of pending files in Redis queue')
QUEUE_PENDING = Gauge('rag_queue_pending', 'Files claimed but not yet acknowledged')

# Constants
STREAM_KEY = "ingest:queue"
GROUP_NAME = "rag-workers"
DEAD_LETTER_KEY = "ingest:dead_letter"
MAX_RETRIES = 3


class RedisQueue:
    """Redis Streams-based work queue for document ingestion."""

    def __init__(self, redis_url: str = None):
        url = redis_url or os.environ.get("REDIS_URL", "redis://litellm-redis:6379/1")
        self.redis = redis.from_url(url, decode_responses=True)
        self.consumer_id = os.getenv("HOSTNAME", f"worker-{os.getpid()}")
        self._ensure_group()
        logger.info(f"RedisQueue initialized: stream={STREAM_KEY}, consumer={self.consumer_id}")

    def _ensure_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            self.redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
            logger.info(f"Created consumer group '{GROUP_NAME}'")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass  # Group already exists
            else:
                raise

    # ── Producer ──────────────────────────────────────────────────────

    def enqueue(self, file_path: str, content_hash: str, rel_path: str) -> str:
        """Add a file to the ingestion queue. Returns the message ID."""
        msg_id = self.redis.xadd(STREAM_KEY, {
            "file_path": file_path,
            "rel_path": rel_path,
            "content_hash": content_hash,
            "enqueued_at": str(time.time()),
        })
        logger.debug(f"Enqueued: {rel_path} → {msg_id}")
        return msg_id

    def enqueue_batch(self, files: list[dict]) -> int:
        """Bulk enqueue files. Each dict must have file_path, content_hash, rel_path."""
        pipe = self.redis.pipeline()
        for f in files:
            pipe.xadd(STREAM_KEY, {
                "file_path": f["file_path"],
                "rel_path": f["rel_path"],
                "content_hash": f["content_hash"],
                "enqueued_at": str(time.time()),
            })
        results = pipe.execute()
        logger.info(f"Enqueued {len(results)} files in batch")
        return len(results)

    # ── Consumer ──────────────────────────────────────────────────────

    def claim_next(self, count: int = 1, block_ms: int = 5000) -> list[dict]:
        """Claim the next message(s) from the queue.
        
        Returns list of dicts: [{"msg_id": "...", "file_path": "...", ...}]
        """
        try:
            results = self.redis.xreadgroup(
                GROUP_NAME, self.consumer_id,
                {STREAM_KEY: ">"},
                count=count,
                block=block_ms,
            )
            if not results:
                return []

            messages = []
            for stream_name, entries in results:
                for msg_id, data in entries:
                    data["msg_id"] = msg_id
                    messages.append(data)
            return messages
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                logger.warning("Consumer group missing — recreating...")
                self._ensure_group()
                return []  # Will succeed on next poll cycle
            logger.error(f"Error claiming from queue: {e}")
            return []
        except Exception as e:
            logger.error(f"Error claiming from queue: {e}")
            return []

    def ack(self, msg_id: str):
        """Acknowledge successful processing of a message."""
        self.redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
        logger.debug(f"ACK: {msg_id}")

    def nack(self, msg_id: str, error: str = ""):
        """Mark a message as failed. After MAX_RETRIES, move to dead letter."""
        try:
            # Check retry count
            msg = self.redis.xrange(STREAM_KEY, msg_id, msg_id)
            if msg:
                data = msg[0][1]
                retries = int(data.get("retries", 0)) + 1

                if retries >= MAX_RETRIES:
                    # Move to dead letter queue
                    data["error"] = error
                    data["retries"] = str(retries)
                    self.redis.xadd(DEAD_LETTER_KEY, data)
                    self.redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    logger.warning(f"Dead letter: {data.get('rel_path', msg_id)} after {retries} retries")
                else:
                    # Re-enqueue with incremented retry count
                    data["retries"] = str(retries)
                    data["last_error"] = error
                    self.redis.xadd(STREAM_KEY, data)
                    self.redis.xack(STREAM_KEY, GROUP_NAME, msg_id)
                    logger.info(f"Retry {retries}/{MAX_RETRIES}: {data.get('rel_path', msg_id)}")
        except Exception as e:
            logger.error(f"Error in nack: {e}")

    # ── Monitoring ────────────────────────────────────────────────────

    def get_queue_depth(self) -> int:
        """Total messages in the stream."""
        try:
            return self.redis.xlen(STREAM_KEY)
        except Exception:
            return 0

    def get_pending_count(self) -> int:
        """Messages claimed but not yet acknowledged."""
        try:
            info = self.redis.xpending(STREAM_KEY, GROUP_NAME)
            return info.get("pending", 0) if isinstance(info, dict) else 0
        except Exception:
            return 0

    def get_dead_letter_count(self) -> int:
        """Messages in the dead letter queue."""
        try:
            return self.redis.xlen(DEAD_LETTER_KEY)
        except Exception:
            return 0

    def update_metrics(self):
        """Push current queue stats to Prometheus."""
        QUEUE_DEPTH.set(self.get_queue_depth())
        QUEUE_PENDING.set(self.get_pending_count())

    def health_check(self) -> dict:
        """Quick health check."""
        try:
            self.redis.ping()
            return {
                "status": "healthy",
                "queue_depth": self.get_queue_depth(),
                "pending": self.get_pending_count(),
                "dead_letter": self.get_dead_letter_count(),
                "consumer_id": self.consumer_id,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    # ── Admin ─────────────────────────────────────────────────────────

    def flush_queue(self):
        """Delete the entire stream and dead letter queue. Use with caution."""
        self.redis.delete(STREAM_KEY, DEAD_LETTER_KEY)
        self._ensure_group()
        logger.info("Queue flushed")

    def is_file_queued(self, rel_path: str) -> bool:
        """Check if a file is already in the queue (approximate)."""
        try:
            # Check in a Redis set for O(1) lookup
            return self.redis.sismember("ingest:queued_files", rel_path)
        except Exception:
            return False

    def mark_queued(self, rel_path: str):
        """Mark a file as enqueued in the tracking set."""
        try:
            self.redis.sadd("ingest:queued_files", rel_path)
        except Exception:
            pass

    def clear_queued_set(self):
        """Clear the tracking set (for reset)."""
        try:
            self.redis.delete("ingest:queued_files")
        except Exception:
            pass
