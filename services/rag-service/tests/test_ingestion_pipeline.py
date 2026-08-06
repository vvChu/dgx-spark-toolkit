"""Unit tests for the deep DocumentIngestionPipeline module using InMemoryStateManager."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ingestion.pipeline import DocumentIngestionPipeline, ProductionIngestor
from ingestion.state_manager import InMemoryStateManager


class TestDocumentIngestionPipeline:
    def test_pipeline_initialization_with_in_memory_state(self):
        state_mgr = InMemoryStateManager()
        pipeline = DocumentIngestionPipeline(state_manager=state_mgr)
        assert pipeline.state_manager is state_mgr
        assert pipeline.state_manager.health_check()["status"] == "healthy"

    def test_backward_compatibility_alias(self):
        assert ProductionIngestor is DocumentIngestionPipeline

    def test_ingest_file_dry_run(self, tmp_path):
        import asyncio
        sample_pdf = tmp_path / "20250101_QD100-TTg_TestDoc.pdf"
        sample_pdf.write_bytes(b"%PDF-1.4 dummy content")

        state_mgr = InMemoryStateManager()
        pipeline = DocumentIngestionPipeline(state_manager=state_mgr)

        # Mock PDF page extraction and model embeddings for fast offline testing
        with patch.object(pipeline, "_extract_pdf_pages") as mock_pdf, \
             patch.object(pipeline, "_parse_relationships_llm", return_value={"replaces": []}):
            mock_pdf.return_value = [{"page": 1, "text": "Điều 1. Quy định chung", "route": "digital", "is_table": False, "bbox": ""}]
            pipeline.model = MagicMock()
            pipeline.model.embed_documents.return_value = [{"dense": [0.1] * 1024, "sparse": {}}]

            doc = asyncio.run(pipeline.ingest_file(sample_pdf))
            assert doc is not None
            assert doc.identity.file_name == "20250101_QD100-TTg_TestDoc.pdf"
            assert state_mgr.get_status(doc.identity.rel_path) == "COMPLETED"

    def test_fast_skip_already_processed_file(self):
        state_mgr = InMemoryStateManager()
        state_mgr.claim_file("already_done.pdf", "worker-1")
        state_mgr.update_status("already_done.pdf", "COMPLETED")

        pipeline = DocumentIngestionPipeline(state_manager=state_mgr)
        # Check fast skip cache
        assert "already_done.pdf" in pipeline.processed_cache
