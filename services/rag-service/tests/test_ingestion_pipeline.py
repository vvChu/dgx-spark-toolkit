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

    def test_parse_relationships_llm_includes_guides(self):
        pipeline = DocumentIngestionPipeline(state_manager=InMemoryStateManager())
        # Test fallback on exception includes guides
        with patch.object(pipeline._http_client, "post", side_effect=Exception("network error")):
            result = pipeline._parse_relationships_llm("test text")
            assert "guides" in result
            assert result["guides"] == []
            assert "replaces" in result
            assert "amends" in result
            assert "references" in result

        # Test prompt structure includes guides
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"replaces": [], "amends": [], "references": [], "guides": ["ND/15/2021/ND-CP"]}'
                }
            }]
        }
        with patch.object(pipeline._http_client, "post", return_value=mock_resp) as mock_post:
            result = pipeline._parse_relationships_llm("Nghị định này hướng dẫn Luật Xây dựng")
            assert result["guides"] == ["ND/15/2021/ND-CP"]
            call_kwargs = mock_post.call_args.kwargs
            system_msg = call_kwargs["json"]["messages"][0]["content"]
            assert "guides" in system_msg

        # Test partial and null responses are normalized
        mock_resp_partial = MagicMock()
        mock_resp_partial.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"replaces": ["  ND/01/2021  "], "amends": null, "guides": ["  TT/05/2022  ", ""]}'
                }
            }]
        }
        with patch.object(pipeline._http_client, "post", return_value=mock_resp_partial):
            res_partial = pipeline._parse_relationships_llm("partial text")
            assert res_partial["replaces"] == ["ND/01/2021"]
            assert res_partial["amends"] == []
            assert res_partial["references"] == []
            assert res_partial["guides"] == ["TT/05/2022"]
