"""Deep IngestionQueue module consolidating Redis Streams & DB state."""
import logging
import time
from typing import Optional, List, Dict, Any

from ingestion.queue import RedisQueue
from ingestion.state_manager import StateManager, InMemoryStateManager

logger = logging.getLogger(__name__)


class IngestionQueue:
    """Deep queue module managing Redis stream dispatch & state updates."""

    def __init__(
        self,
        redis_queue: Optional[RedisQueue] = None,
        state_manager: Optional[StateManager] = None,
    ):
        self.redis_queue = redis_queue or RedisQueue()
        self.state_manager = state_manager or StateManager()

    def enqueue(self, file_path: str, content_hash: str, rel_path: str) -> str:
        """Enqueue file for worker processing and record PENDING state."""
        msg_id = self.redis_queue.enqueue(file_path, content_hash, rel_path)
        if hasattr(self.state_manager, "update_status"):
            self.state_manager.update_status(file_path, "PENDING")
        return msg_id

    def enqueue_batch(self, files: List[Dict[str, str]]) -> int:
        """Batch enqueue files."""
        count = self.redis_queue.enqueue_batch(files)
        for f in files:
            if hasattr(self.state_manager, "update_status"):
                self.state_manager.update_status(f["file_path"], "PENDING")
        return count

    def claim_next(
        self,
        count: int = 1,
        block_ms: int = 5000,
        worker_id: str = "worker-1",
    ) -> List[Dict[str, Any]]:
        """Claim next message(s) from queue and set state to CLAIMED."""
        messages = self.redis_queue.claim_next(count=count, block_ms=block_ms)
        claimed_messages = []
        for msg in messages:
            file_path = msg.get("file_path", "")
            content_hash = msg.get("content_hash", "")
            if file_path:
                claimed = self.state_manager.claim_file(
                    file_path, worker_id, content_hash=content_hash
                )
                if claimed:
                    msg["worker_id"] = worker_id
                    claimed_messages.append(msg)
            else:
                claimed_messages.append(msg)
        return claimed_messages

    def acknowledge(
        self,
        msg_id: str,
        file_path: str,
        doc_id: str = "",
        metadata: Optional[dict] = None,
    ):
        """Acknowledge successful completion of worker task."""
        self.redis_queue.ack(msg_id)
        if file_path and hasattr(self.state_manager, "update_status"):
            self.state_manager.update_status(
                file_path, "COMPLETED", doc_id=doc_id, metadata=metadata
            )

    def nack(self, msg_id: str, file_path: str, error: str = ""):
        """Nack message and record error/FAILED state in StateManager."""
        self.redis_queue.nack(msg_id, error=error)
        if file_path and hasattr(self.state_manager, "update_status"):
            self.state_manager.update_status(file_path, "FAILED", error=error)

    def get_stats(self) -> Dict[str, Any]:
        """Unified queue and state metrics."""
        return {
            "queue_depth": self.redis_queue.get_queue_depth(),
            "pending_count": self.redis_queue.get_pending_count(),
            "dead_letter_count": self.redis_queue.get_dead_letter_count(),
        }

    def health_check(self) -> Dict[str, Any]:
        """Check health of underlying queue storage."""
        if hasattr(self.redis_queue, "health_check"):
            return self.redis_queue.health_check()
        return {"status": "healthy", "type": "in_memory"}


class InMemoryIngestionQueue(IngestionQueue):
    """In-memory adapter for testing without Redis or PostgreSQL."""

    def __init__(self):
        self.state_manager = InMemoryStateManager()
        self.queue = []
        self.dead_letter = []
        self.claimed = {}
        self.consumer_id = "test-worker"

    def enqueue(self, file_path: str, content_hash: str, rel_path: str) -> str:
        msg_id = f"msg-{len(self.queue) + 1}"
        item = {
            "msg_id": msg_id,
            "file_path": file_path,
            "rel_path": rel_path,
            "content_hash": content_hash,
            "enqueued_at": str(time.time()),
        }
        self.queue.append(item)
        self.state_manager.update_status(file_path, "PENDING")
        return msg_id

    def claim_next(
        self,
        count: int = 1,
        block_ms: int = 0,
        worker_id: str = "test-worker",
    ) -> List[Dict[str, Any]]:
        claimed = []
        while self.queue and len(claimed) < count:
            msg = self.queue.pop(0)
            file_path = msg["file_path"]
            if self.state_manager.claim_file(
                file_path, worker_id, content_hash=msg.get("content_hash")
            ):
                msg["worker_id"] = worker_id
                self.claimed[msg["msg_id"]] = msg
                claimed.append(msg)
        return claimed

    def acknowledge(
        self,
        msg_id: str,
        file_path: str,
        doc_id: str = "",
        metadata: Optional[dict] = None,
    ):
        if msg_id in self.claimed:
            del self.claimed[msg_id]
        if file_path:
            self.state_manager.update_status(
                file_path, "COMPLETED", doc_id=doc_id, metadata=metadata
            )

    def nack(self, msg_id: str, file_path: str, error: str = ""):
        if msg_id in self.claimed:
            msg = self.claimed.pop(msg_id)
            self.dead_letter.append(msg)
        if file_path:
            self.state_manager.update_status(
                file_path, "FAILED", error=error
            )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "queue_depth": len(self.queue),
            "pending_count": len(self.claimed),
            "dead_letter_count": len(self.dead_letter),
        }
