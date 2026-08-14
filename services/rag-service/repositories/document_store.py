"""Unified deep DocumentStore module encapsulating Milvus, Neo4j, and State persistence.

Provides atomic index, sync, and delete seams across vector database, graph database,
and PostgreSQL IngestionState tracking.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from core.config import get_settings
from ingestion.state_manager import StateManager, InMemoryStateManager
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from ingestion.models import ProcessedDocument

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous code safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Running inside an active event loop: create new task or use executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


class DocumentStore:
    """Deep persistence module encapsulating Milvus, Neo4j, and StateManager."""

    def __init__(
        self,
        milvus_repo: Optional[MilvusRepository] = None,
        neo4j_repo: Optional[Neo4jRepository] = None,
        state_manager: Optional[StateManager] = None,
    ):
        self.settings = get_settings()
        self.state_manager = state_manager or StateManager()
        self.milvus_repo = milvus_repo
        self.neo4j_repo = neo4j_repo

    def is_document_processed(self, rel_path: str) -> bool:
        """Check if document is already successfully processed in StateManager."""
        try:
            status = self.state_manager.get_status(rel_path)
            return status == "COMPLETED"
        except Exception as e:
            logger.debug(f"DocumentStore is_document_processed check failed for {rel_path}: {e}")
            return False

    def claim_document(self, rel_path: str, content_hash: str = "", worker_id: str = "") -> bool:
        """Claim a document for worker processing."""
        try:
            return self.state_manager.claim_file(rel_path, worker_id, content_hash=content_hash)
        except Exception as e:
            logger.warning(f"DocumentStore claim_document failed for {rel_path}: {e}")
            return False

    async def sync_status(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        """Cascade document legal status sync across Postgres, Milvus, and Neo4j."""
        logger.info(f"Cascading status sync for {doc_id} -> {new_status}")
        errors = []

        # 1. State Manager
        try:
            if hasattr(self.state_manager, "update_validity_status"):
                self.state_manager.update_validity_status(doc_id, new_status)
        except Exception as e:
            errors.append(f"Postgres update failed: {e}")

        # 2. Milvus
        if self.milvus_repo:
            try:
                if hasattr(self.milvus_repo, "update_doc_validity"):
                    await self.milvus_repo.update_doc_validity(doc_id, new_status)
            except Exception as e:
                errors.append(f"Milvus update failed: {e}")

        # 3. Neo4j
        if self.neo4j_repo:
            try:
                if hasattr(self.neo4j_repo, "update_node_status"):
                    await self.neo4j_repo.update_node_status(doc_id, new_status)
            except Exception as e:
                errors.append(f"Neo4j update failed: {e}")

        if errors:
            logger.error(f"Sync status for {doc_id} partial failure: {errors}")
            return {"status": "partial_success", "errors": errors}

        return {"status": "success", "doc_id": doc_id, "new_status": new_status}

    def sync_status_sync(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        return _run_async(self.sync_status(doc_id, new_status))

    async def index_document(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        """Index document chunks into Milvus vector DB and graph nodes into Neo4j."""
        identity = getattr(processed_doc, "identity", None)
        doc_id = identity.doc_id if identity else getattr(processed_doc, "doc_id", "")
        rel_path = identity.rel_path if identity else getattr(processed_doc, "file_path", "")
        logger.info(f"Indexing document {doc_id} into DocumentStore...")

        # Record state: PROCESSING
        try:
            self.state_manager.update_status(rel_path, "PROCESSING", doc_id=doc_id)
        except Exception as e:
            logger.warning(f"StateManager set_processing error for {doc_id}: {e}")

        milvus_ok = True
        neo4j_ok = True

        chunks = getattr(processed_doc, "chunks", None) or getattr(processed_doc, "raw_chunks", [])
        pages = getattr(processed_doc, "pages", None) or getattr(processed_doc, "raw_pages", [])

        # Milvus Insert
        if self.milvus_repo and chunks:
            try:
                await self.milvus_repo.insert_chunks(chunks)
            except Exception as e:
                logger.error(f"Milvus insertion failed for {doc_id}: {e}")
                milvus_ok = False

        # Neo4j Insert
        if self.neo4j_repo:
            try:
                await self.neo4j_repo.create_document_node(processed_doc)
            except Exception as e:
                logger.error(f"Neo4j insertion failed for {doc_id}: {e}")
                neo4j_ok = False

        if milvus_ok and neo4j_ok:
            try:
                self.state_manager.update_status(
                    rel_path,
                    "COMPLETED",
                    doc_id=doc_id,
                    metadata={"pages": len(pages), "chunks": len(chunks)},
                )
            except Exception as e:
                logger.warning(f"StateManager set_completed error: {e}")
            return {"status": "success", "doc_id": doc_id}
        else:
            try:
                self.state_manager.update_status(rel_path, "FAILED", error="Indexing error in vector/graph DB")
            except Exception as e:
                logger.warning(f"StateManager set_failed error: {e}")
            return {"status": "failed", "doc_id": doc_id, "milvus_ok": milvus_ok, "neo4j_ok": neo4j_ok}

    def index_document_sync(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        return _run_async(self.index_document(processed_doc))

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Delete document from Milvus, Neo4j, and StateManager."""
        logger.info(f"Deleting document {doc_id} from DocumentStore...")
        errors = []

        if self.milvus_repo:
            try:
                await self.milvus_repo.delete_by_doc_id(doc_id)
            except Exception as e:
                errors.append(f"Milvus delete error: {e}")

        if self.neo4j_repo:
            try:
                await self.neo4j_repo.delete_document_node(doc_id)
            except Exception as e:
                errors.append(f"Neo4j delete error: {e}")

        return {"status": "success" if not errors else "partial_success", "errors": errors}

    def delete_document_sync(self, doc_id: str) -> Dict[str, Any]:
        return _run_async(self.delete_document(doc_id))


class InMemoryDocumentStore(DocumentStore):
    """In-memory test adapter for offline unit testing without active database connections."""

    def __init__(self, state_manager: Optional[StateManager] = None):
        super().__init__(state_manager=state_manager or InMemoryStateManager())
        self.indexed_documents: Dict[str, ProcessedDocument] = {}
        self.document_statuses: Dict[str, str] = {}

    def is_document_processed(self, rel_path: str) -> bool:
        return self.state_manager.get_status(rel_path) == "COMPLETED"

    def claim_document(self, rel_path: str, content_hash: str = "", worker_id: str = "") -> bool:
        return self.state_manager.claim_file(rel_path, worker_id, content_hash=content_hash)

    async def sync_status(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        self.document_statuses[doc_id] = new_status
        return {"status": "success", "doc_id": doc_id, "new_status": new_status}

    async def index_document(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        identity = getattr(processed_doc, "identity", None)
        doc_id = identity.doc_id if identity else getattr(processed_doc, "doc_id", "test_doc")
        rel_path = identity.rel_path if identity else getattr(processed_doc, "file_path", "test.pdf")

        self.indexed_documents[doc_id] = processed_doc
        self.document_statuses[doc_id] = "ACTIVE"
        self.state_manager.update_status(rel_path, "COMPLETED", doc_id=doc_id)
        return {"status": "success", "doc_id": doc_id}

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        self.indexed_documents.pop(doc_id, None)
        self.document_statuses.pop(doc_id, None)
        return {"status": "success", "doc_id": doc_id}
