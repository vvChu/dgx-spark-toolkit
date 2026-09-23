"""Unit tests for the deep DocumentStore module and InMemoryDocumentStore adapter."""
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
            inserted_chunks = mock_milvus.insert_chunks.call_args[0][0]
            assert len(inserted_chunks) == 1
            assert inserted_chunks[0]["doc_id"] == "VBPL/02/2024/ND-CP"
            assert inserted_chunks[0]["doc_number"] == "02/2024/ND-CP"
            assert inserted_chunks[0]["file_hash"] == "hash456"
            assert inserted_chunks[0]["doc_type"] == "ND"
            assert inserted_chunks[0]["authority"] == "CP"
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

    def test_in_memory_document_store_version_update(self):
        import asyncio

        async def _test():
            store = InMemoryDocumentStore()
            res = await store.notify_version_update(
                new_doc_id="VBPL/02_2025_TT-BXD",
                supersedes=["VBPL/01_2024_TT-BXD"],
                amends=["VBPL/03_2023_TT-BXD"],
            )
            assert res["status"] == "success"
            assert "VBPL/01_2024_TT-BXD" in res["superseded"]
            assert "VBPL/03_2023_TT-BXD" in res["amended"]
            assert store.document_statuses["VBPL/01_2024_TT-BXD"] == "SUPERSEDED"
            assert store.document_statuses["VBPL/03_2023_TT-BXD"] == "OUTDATED"
            assert len(store.relations) == 2

        asyncio.run(_test())

    def test_document_store_relations_with_mock(self):
        import asyncio

        async def _test():
            mock_neo4j = MagicMock()
            mock_neo4j.create_supersedes_relation = AsyncMock()
            mock_neo4j.create_amends_relation = AsyncMock()
            mock_neo4j.update_node_status = AsyncMock()

            mock_milvus = MagicMock()
            mock_milvus.update_doc_validity = AsyncMock()

            mock_state = MagicMock()
            mock_state.update_validity_status = MagicMock()

            store = DocumentStore(
                milvus_repo=mock_milvus,
                neo4j_repo=mock_neo4j,
                state_manager=mock_state,
            )

            res = await store.notify_version_update(
                new_doc_id="VBPL/NEW",
                supersedes=["VBPL/OLD_1"],
                amends=["VBPL/OLD_2"],
            )
            assert res["status"] == "success"
            assert mock_neo4j.create_supersedes_relation.call_count == 1
            assert mock_neo4j.create_amends_relation.call_count == 1
            assert mock_milvus.update_doc_validity.call_count == 2

        asyncio.run(_test())


class TestDocumentStoreSyncAndFailures:
    """Test DocumentStore.sync_status error handling across multiple data stores."""

    def _make_store(self):
        state_mgr = MagicMock()
        milvus_repo = AsyncMock()
        neo4j_repo = AsyncMock()
        store = DocumentStore(
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            state_manager=state_mgr,
        )
        return store, state_mgr, milvus_repo, neo4j_repo

    def test_sync_all_success(self):
        import asyncio
        store, state_mgr, milvus_repo, neo4j_repo = self._make_store()
        result = asyncio.run(store.sync_status("BXD/01-2024", "OUTDATED"))
        assert result["status"] == "success"
        assert result["doc_id"] == "BXD/01-2024"
        assert result["new_status"] == "OUTDATED"
        state_mgr.update_validity_status.assert_called_once_with("BXD/01-2024", "OUTDATED")
        milvus_repo.update_doc_validity.assert_awaited_once_with("BXD/01-2024", "OUTDATED")
        neo4j_repo.update_node_status.assert_awaited_once_with("BXD/01-2024", "OUTDATED")

    def test_partial_failure_postgres(self):
        import asyncio
        store, state_mgr, milvus_repo, neo4j_repo = self._make_store()
        state_mgr.update_validity_status.side_effect = Exception("DB down")
        result = asyncio.run(store.sync_status("BXD/01-2024", "ACTIVE"))
        assert result["status"] == "partial_success"
        assert result["doc_id"] == "BXD/01-2024"
        assert result["new_status"] == "ACTIVE"
        assert len(result["errors"]) == 1
        assert "Postgres" in result["errors"][0]

    def test_partial_failure_milvus(self):
        import asyncio
        store, state_mgr, milvus_repo, neo4j_repo = self._make_store()
        milvus_repo.update_doc_validity.side_effect = Exception("Milvus timeout")
        result = asyncio.run(store.sync_status("BXD/01-2024", "REPLACED"))
        assert result["status"] == "partial_success"
        assert result["doc_id"] == "BXD/01-2024"
        assert result["new_status"] == "REPLACED"
        assert any("Milvus" in e for e in result["errors"])
        neo4j_repo.update_node_status.assert_awaited_once_with("BXD/01-2024", "REPLACED")

    def test_all_stores_fail(self):
        import asyncio
        store, state_mgr, milvus_repo, neo4j_repo = self._make_store()
        state_mgr.update_validity_status.side_effect = Exception("pg")
        milvus_repo.update_doc_validity.side_effect = Exception("mv")
        neo4j_repo.update_node_status.side_effect = Exception("n4j")
        result = asyncio.run(store.sync_status("X/Y", "OUTDATED"))
        assert result["status"] == "partial_success"
        assert result["doc_id"] == "X/Y"
        assert result["new_status"] == "OUTDATED"
        assert len(result["errors"]) == 3

    def test_notify_new_document_ingested_via_document_store(self):
        import asyncio
        store = InMemoryDocumentStore()
        res = asyncio.run(store.notify_version_update(
            new_doc_id="VBPL/NEW_2025",
            supersedes=["VBPL/OLD_2020"],
            amends=["VBPL/AMENDED_2022"],
        ))
        assert res["status"] == "success"
        assert "VBPL/OLD_2020" in res["superseded"]
        assert "VBPL/AMENDED_2022" in res["amended"]
        assert store.document_statuses["VBPL/OLD_2020"] == "SUPERSEDED"
        assert store.document_statuses["VBPL/AMENDED_2022"] == "OUTDATED"

    def test_init_collection_invokes_milvus_schema(self):
        import asyncio
        mock_milvus = MagicMock()
        mock_milvus.ensure_collection_schema = AsyncMock(return_value=True)
        mock_neo4j = MagicMock()
        mock_neo4j.init_schema = AsyncMock(return_value=True)

        store = DocumentStore(milvus_repo=mock_milvus, neo4j_repo=mock_neo4j)
        asyncio.run(store.init_collection())
        mock_milvus.ensure_collection_schema.assert_called_once()
        mock_neo4j.init_schema.assert_called_once()

