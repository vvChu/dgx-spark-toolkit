"""Unit tests for the deep IngestionQueue module and InMemoryIngestionQueue adapter."""
import pytest
from ingestion.ingestion_queue import IngestionQueue, InMemoryIngestionQueue


def test_in_memory_ingestion_queue_lifecycle():
    queue = InMemoryIngestionQueue()
    assert queue.get_stats()["queue_depth"] == 0

    # 1. Enqueue file
    msg_id = queue.enqueue("/tmp/doc1.pdf", "hash123", "doc1.pdf")
    assert msg_id == "msg-1"
    assert queue.get_stats()["queue_depth"] == 1

    # Check PENDING state in state_manager
    assert queue.state_manager.get_status("/tmp/doc1.pdf") == "PENDING"

    # 2. Claim next file
    claimed = queue.claim_next(count=1, worker_id="worker-test")
    assert len(claimed) == 1
    assert claimed[0]["file_path"] == "/tmp/doc1.pdf"
    assert claimed[0]["worker_id"] == "worker-test"

    # Check CLAIMED state
    assert queue.state_manager.get_status("/tmp/doc1.pdf") == "CLAIMED"

    # 3. Acknowledge completion
    queue.acknowledge(msg_id, "/tmp/doc1.pdf", doc_id="DOC-001", metadata={"chunks": 10})
    assert queue.get_stats()["pending_count"] == 0

    # Check COMPLETED state
    assert queue.state_manager.get_status("/tmp/doc1.pdf") == "COMPLETED"


def test_in_memory_ingestion_queue_nack():
    queue = InMemoryIngestionQueue()
    queue.enqueue("/tmp/doc2.pdf", "hash456", "doc2.pdf")

    claimed = queue.claim_next(count=1, worker_id="worker-fail")
    assert len(claimed) == 1

    # Nack failure
    queue.nack(claimed[0]["msg_id"], "/tmp/doc2.pdf", error="OCR Failure")
    assert queue.get_stats()["dead_letter_count"] == 1

    # Check FAILED state
    assert queue.state_manager.get_status("/tmp/doc2.pdf") == "FAILED"


def test_ingestion_queue_is_paused_backpressure():
    from unittest.mock import MagicMock

    mock_redis = MagicMock()
    mock_redis_queue = MagicMock()
    mock_redis_queue.redis = mock_redis

    queue = IngestionQueue(redis_queue=mock_redis_queue)

    # 1. Flag not set
    mock_redis.get.return_value = None
    assert queue.is_paused() is False

    # 2. Flag set to "1"
    mock_redis.get.return_value = "1"
    assert queue.is_paused() is True

    # 3. Flag set to bytes b"1"
    mock_redis.get.return_value = b"1"
    assert queue.is_paused() is True

    # 4. In-memory queue is never paused
    in_mem_queue = InMemoryIngestionQueue()
    assert in_mem_queue.is_paused() is False
