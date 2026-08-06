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
