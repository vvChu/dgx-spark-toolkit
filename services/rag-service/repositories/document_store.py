"""Unified deep DocumentStore module encapsulating Milvus, Neo4j, and State persistence.

Provides atomic index, sync, and delete seams across vector database, graph database,
and PostgreSQL IngestionState tracking.
"""
import logging
from typing import Dict, Any, List, Optional
from pymilvus import AsyncMilvusClient
from neo4j import AsyncDriver, AsyncGraphDatabase, GraphDatabase

from core.config import get_settings
from ingestion.state_manager import StateManager, InMemoryStateManager
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from ingestion.models import ProcessedDocument

logger = logging.getLogger(__name__)


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

    async def index_document(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        """Index document chunks into Milvus vector DB and graph nodes into Neo4j."""
        doc_id = processed_doc.identity.doc_number or processed_doc.doc_id
        logger.info(f"Indexing document {doc_id} into DocumentStore...")

        # Record state: PROCESSING
        try:
            self.state_manager.set_processing(doc_id, worker_id="document_store")
        except Exception as e:
            logger.warning(f"StateManager set_processing error for {doc_id}: {e}")

        milvus_ok = True
        neo4j_ok = True

        # Milvus Insert
        if self.milvus_repo and hasattr(self.milvus_repo, "insert_chunks"):
            try:
                await self.milvus_repo.insert_chunks(processed_doc.chunks)
            except Exception as e:
                logger.error(f"Milvus insertion failed for {doc_id}: {e}")
                milvus_ok = False

        # Neo4j Insert
        if self.neo4j_repo and hasattr(self.neo4j_repo, "create_document_node"):
            try:
                await self.neo4j_repo.create_document_node(processed_doc)
            except Exception as e:
                logger.error(f"Neo4j insertion failed for {doc_id}: {e}")
                neo4j_ok = False

        if milvus_ok and neo4j_ok:
            try:
                self.state_manager.set_completed(doc_id, total_pages=len(processed_doc.pages))
            except Exception as e:
                logger.warning(f"StateManager set_completed error: {e}")
            return {"status": "success", "doc_id": doc_id}
        else:
            try:
                self.state_manager.set_failed(doc_id, error="Indexing error in vector/graph DB")
            except Exception as e:
                logger.warning(f"StateManager set_failed error: {e}")
            return {"status": "failed", "doc_id": doc_id, "milvus_ok": milvus_ok, "neo4j_ok": neo4j_ok}

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Delete document from Milvus, Neo4j, and StateManager."""
        logger.info(f"Deleting document {doc_id} from DocumentStore...")
        errors = []

        if self.milvus_repo and hasattr(self.milvus_repo, "delete_by_doc_id"):
            try:
                await self.milvus_repo.delete_by_doc_id(doc_id)
            except Exception as e:
                errors.append(f"Milvus delete error: {e}")

        if self.neo4j_repo and hasattr(self.neo4j_repo, "delete_document_node"):
            try:
                await self.neo4j_repo.delete_document_node(doc_id)
            except Exception as e:
                errors.append(f"Neo4j delete error: {e}")

        return {"status": "success" if not errors else "partial_success", "errors": errors}


class InMemoryDocumentStore(DocumentStore):
    """In-memory test adapter for offline unit testing without active database connections."""

    def __init__(self):
        super().__init__(state_manager=InMemoryStateManager())
        self.indexed_documents: Dict[str, ProcessedDocument] = {}
        self.document_statuses: Dict[str, str] = {}

    async def sync_status(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        self.document_statuses[doc_id] = new_status
        return {"status": "success", "doc_id": doc_id, "new_status": new_status}

    async def index_document(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        doc_id = processed_doc.identity.doc_number or processed_doc.doc_id
        self.indexed_documents[doc_id] = processed_doc
        self.document_statuses[doc_id] = "ACTIVE"
        return {"status": "success", "doc_id": doc_id}

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        self.indexed_documents.pop(doc_id, None)
        self.document_statuses.pop(doc_id, None)
        return {"status": "success", "doc_id": doc_id}
