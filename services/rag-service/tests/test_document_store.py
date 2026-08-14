"""Unit tests for the deep DocumentStore module and InMemoryDocumentStore adapter."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from ingestion.models import ProcessedDocument, DocumentIdentity, DocumentMetadata, Chunk
from repositories.document_store import DocumentStore, InMemoryDocumentStore


class TestDocumentStore:
    def test_in_memory_document_store_lifecycle(self):
        import asyncio

        async def _test():
            store = InMemoryDocumentStore()
            identity = DocumentIdentity(
                doc_number="01/2024/TT-BXD",
                namespace="VBPL",
                content_hash="hash123",
                file_name="01_2024_TT-BXD.pdf",
                rel_path="01_2024_TT-BXD.pdf",
            )
            doc = ProcessedDocument(
                identity=identity,
                metadata=DocumentMetadata(doc_number="01/2024/TT-BXD", doc_type="TT", authority="BXD"),
                chunks=[Chunk(text="Điều 1", source="01_2024_TT-BXD.pdf", page=1)],
                file_path="01_2024_TT-BXD.pdf",
            )

            # 1. Claim
            assert store.claim_document(doc.identity.rel_path, content_hash="hash123", worker_id="test-worker") is True

            # 2. Index
            index_res = await store.index_document(doc)
            assert index_res["status"] == "success"
            assert store.is_document_processed(doc.identity.rel_path) is True

            # 3. Status Sync
            sync_res = await store.sync_status(doc.identity.doc_id, "OUTDATED")
            assert sync_res["status"] == "success"
            assert store.document_statuses[doc.identity.doc_id] == "OUTDATED"

            # 4. Delete
            del_res = await store.delete_document(doc.identity.doc_id)
            assert del_res["status"] == "success"
            assert doc.identity.doc_id not in store.indexed_documents

        asyncio.run(_test())

    def test_document_store_with_mocked_repos(self):
        import asyncio

        async def _test():
            mock_milvus = MagicMock()
            mock_milvus.insert_chunks = AsyncMock(return_value=1)
            mock_milvus.delete_by_doc_id = AsyncMock()
            mock_milvus.update_doc_validity = AsyncMock()

            mock_neo4j = MagicMock()
            mock_neo4j.create_document_node = AsyncMock()
            mock_neo4j.delete_document_node = AsyncMock()
            mock_neo4j.update_node_status = AsyncMock()

            mock_state = MagicMock()
            mock_state.update_status = MagicMock()
            mock_state.update_validity_status = MagicMock()
            mock_state.claim_file = MagicMock(return_value=True)

            store = DocumentStore(
                milvus_repo=mock_milvus,
                neo4j_repo=mock_neo4j,
                state_manager=mock_state,
            )

            identity = DocumentIdentity(
                doc_number="02/2024/ND-CP",
                namespace="VBPL",
                content_hash="hash456",
                file_name="02_2024_ND-CP.pdf",
                rel_path="02_2024_ND-CP.pdf",
            )
            doc = ProcessedDocument(
                identity=identity,
                metadata=DocumentMetadata(doc_number="02/2024/ND-CP", doc_type="ND", authority="CP"),
                chunks=[Chunk(text="Điều 1", source="02_2024_ND-CP.pdf", page=1)],
                file_path="02_2024_ND-CP.pdf",
            )

            # Index
            res = await store.index_document(doc)
            assert res["status"] == "success"
            assert mock_milvus.insert_chunks.call_count == 1
            assert mock_neo4j.create_document_node.call_count == 1
            assert mock_state.update_status.call_count == 2  # PROCESSING then COMPLETED

            # Status sync
            await store.sync_status("VBPL/02_2024_ND-CP", "EXPIRED")
            assert mock_milvus.update_doc_validity.call_count == 1
            assert mock_neo4j.update_node_status.call_count == 1
            assert mock_state.update_validity_status.call_count == 1

            # Delete
            await store.delete_document("VBPL/02_2024_ND-CP")
            assert mock_milvus.delete_by_doc_id.call_count == 1
            assert mock_neo4j.delete_document_node.call_count == 1

        asyncio.run(_test())

    def test_document_store_sync_helpers(self):
        store = InMemoryDocumentStore()
        identity = DocumentIdentity(
            doc_number="03/2024/TT-BXD",
            namespace="VBPL",
            content_hash="hash789",
            file_name="03_2024_TT-BXD.pdf",
            rel_path="03_2024_TT-BXD.pdf",
        )
        doc = ProcessedDocument(
            identity=identity,
            metadata=DocumentMetadata(doc_number="03/2024/TT-BXD"),
            chunks=[Chunk(text="Điều 1", source="03_2024_TT-BXD.pdf", page=1)],
            file_path="03_2024_TT-BXD.pdf",
        )

        # Test sync wrappers
        res = store.index_document_sync(doc)
        assert res["status"] == "success"

        sync_res = store.sync_status_sync(doc.identity.doc_id, "OUTDATED")
        assert sync_res["status"] == "success"

        del_res = store.delete_document_sync(doc.identity.doc_id)
        assert del_res["status"] == "success"
