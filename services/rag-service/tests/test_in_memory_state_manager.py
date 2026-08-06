"""Unit tests for InMemoryStateManager and StateManager adapter."""
import pytest
from ingestion.state_manager import InMemoryStateManager, StateManager


class TestInMemoryStateManager:
    def test_claim_file_and_status(self):
        sm = InMemoryStateManager()
        assert sm.claim_file("doc1.pdf", "worker-1", content_hash="hash123") is True
        assert sm.get_status("doc1.pdf") == "CLAIMED"

    def test_double_claim_fails(self):
        sm = InMemoryStateManager()
        sm.claim_file("doc1.pdf", "worker-1", content_hash="hash123")
        # Double claim while claimed should fail
        assert sm.claim_file("doc1.pdf", "worker-2", content_hash="hash123") is False

    def test_update_status_and_completed(self):
        sm = InMemoryStateManager()
        sm.claim_file("doc1.pdf", "worker-1")
        sm.update_status("doc1.pdf", "COMPLETED", doc_id="VBPL/123", metadata={"pages": 5})
        assert sm.get_status("doc1.pdf") == "COMPLETED"

        summary = sm.get_status_summary()
        assert summary.get("COMPLETED") == 1

    def test_reset_all(self):
        sm = InMemoryStateManager()
        sm.claim_file("doc1.pdf", "worker-1")
        sm.reset_all()
        assert sm.get_status("doc1.pdf") is None
        assert sm.get_status_summary() == {}

    def test_health_check(self):
        sm = InMemoryStateManager()
        res = sm.health_check()
        assert res["status"] == "healthy"
