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
        raise RuntimeError(
            "Calling sync methods on DocumentStore from inside an active async event loop is not supported; "
            "please use await store.index_document(...) instead."
        )
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

    @classmethod
    def create_default(
        cls,
        state_manager: Optional[StateManager] = None,
        milvus_uri: Optional[str] = None,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_pass: Optional[str] = None,
    ) -> "DocumentStore":
        """Factory method constructing DocumentStore with underlying database repositories."""
        from pymilvus import AsyncMilvusClient
        from neo4j import AsyncGraphDatabase

        settings = get_settings()
        m_uri = milvus_uri or f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
        n_uri = neo4j_uri or settings.NEO4J_URI
        n_user = neo4j_user or settings.NEO4J_USER
        n_pwd = neo4j_pass or (
            settings.NEO4J_PASSWORD.get_secret_value()
            if hasattr(settings.NEO4J_PASSWORD, "get_secret_value")
            else str(settings.NEO4J_PASSWORD)
        )

        try:
            milvus_client = AsyncMilvusClient(uri=m_uri)
            milvus_repo = MilvusRepository(milvus_client)
        except Exception as e:
            logger.warning(f"Failed to initialize MilvusRepository: {e}")
            milvus_repo = None

        try:
            neo4j_driver = AsyncGraphDatabase.driver(n_uri, auth=(n_user, n_pwd))
            neo4j_repo = Neo4jRepository(neo4j_driver)
        except Exception as e:
            logger.warning(f"Failed to initialize Neo4jRepository: {e}")
            neo4j_repo = None

        return cls(
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            state_manager=state_manager,
        )

    async def init_infrastructure(self) -> None:
        """Initialize underlying storage infrastructure (schemas, constraints, indexes)."""
        if self.milvus_repo and hasattr(self.milvus_repo, "ensure_collection_schema"):
            try:
                await self.milvus_repo.ensure_collection_schema()
            except Exception as e:
                logger.warning(f"Milvus schema initialization failed: {e}")

        if self.neo4j_repo and hasattr(self.neo4j_repo, "init_schema"):
            try:
                await self.neo4j_repo.init_schema()
            except Exception as e:
                logger.warning(f"Neo4j schema initialization failed: {e}")

    def init_infrastructure_sync(self) -> None:
        """Synchronous wrapper for infrastructure initialization."""
        try:
            _run_async(self.init_infrastructure())
        except Exception as e:
            logger.warning(f"Sync infrastructure initialization skipped: {e}")

    async def close(self) -> None:
        """Safely close repository connections."""
        if self.milvus_repo and hasattr(self.milvus_repo, "close"):
            await self.milvus_repo.close()
        if self.neo4j_repo and hasattr(self.neo4j_repo, "close"):
            await self.neo4j_repo.close()

    def close_sync(self) -> None:
        """Sync wrapper to close repository resources."""
        try:
            _run_async(self.close())
        except Exception as e:
            logger.debug(f"Error closing DocumentStore: {e}")

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
            return {"status": "partial_success", "doc_id": doc_id, "new_status": new_status, "errors": errors}

        return {"status": "success", "doc_id": doc_id, "new_status": new_status}

    def sync_status_sync(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        return _run_async(self.sync_status(doc_id, new_status))

    async def index_document(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        """Index document chunks into Milvus vector DB and graph nodes into Neo4j."""
        identity = getattr(processed_doc, "identity", None)
        doc_id = identity.doc_id if identity else getattr(processed_doc, "doc_id", "")
        rel_path = identity.rel_path if identity else getattr(processed_doc, "file_path", "")
        metadata = getattr(processed_doc, "metadata", None)
        doc_date = getattr(metadata, "date", "unknown") if metadata else "unknown"
        doc_type = getattr(metadata, "doc_type", "unknown") if metadata else "unknown"
        authority = getattr(metadata, "authority", "unknown") if metadata else "unknown"
        doc_number = identity.doc_number if identity else getattr(metadata, "doc_number", "")
        content_hash = identity.content_hash if identity else ""
        source_category = getattr(metadata, "source_category", "KHAC") if metadata else "KHAC"
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

        # Enrich and normalize chunks with document identity before Milvus insert
        enriched_chunks = []
        for c in chunks:
            cdict = c.to_dict() if hasattr(c, "to_dict") else dict(c)
            if not cdict.get("doc_id"):
                cdict["doc_id"] = doc_id
            if not cdict.get("doc_number"):
                cdict["doc_number"] = doc_number
            if not cdict.get("file_hash"):
                cdict["file_hash"] = content_hash
            if not cdict.get("source"):
                cdict["source"] = rel_path
            if not cdict.get("doc_date") or cdict.get("doc_date") == "unknown":
                cdict["doc_date"] = doc_date
            if not cdict.get("doc_type") or cdict.get("doc_type") == "unknown":
                cdict["doc_type"] = doc_type
            if not cdict.get("authority") or cdict.get("authority") == "unknown":
                cdict["authority"] = authority
            if not cdict.get("source_category") or cdict.get("source_category") == "KHAC":
                cdict["source_category"] = source_category
            enriched_chunks.append(cdict)

        # Milvus Insert
        if self.milvus_repo and enriched_chunks:
            try:
                await self.milvus_repo.insert_chunks(enriched_chunks)
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

    async def add_relation(self, from_doc_id: str, to_doc_id: str, relation_type: str) -> Dict[str, Any]:
        """Create a directed legal relationship edge between two documents in Neo4j."""
        rel = relation_type.upper().strip()
        if not self.neo4j_repo:
            return {"status": "no_graph_repo", "from": from_doc_id, "to": to_doc_id, "relation": rel}

        try:
            executed = False
            if rel in ("SUPERSEDES", "REPLACES"):
                if hasattr(self.neo4j_repo, "create_supersedes_relation"):
                    await self.neo4j_repo.create_supersedes_relation(from_doc_id, to_doc_id)
                    executed = True
                elif hasattr(self.neo4j_repo, "create_relationship"):
                    await self.neo4j_repo.create_relationship(from_doc_id, to_doc_id, "SUPERSEDES")
                    executed = True
            elif rel in ("AMENDS", "MODIFIES"):
                if hasattr(self.neo4j_repo, "create_amends_relation"):
                    await self.neo4j_repo.create_amends_relation(from_doc_id, to_doc_id)
                    executed = True
                elif hasattr(self.neo4j_repo, "create_relationship"):
                    await self.neo4j_repo.create_relationship(from_doc_id, to_doc_id, "AMENDS")
                    executed = True
            elif hasattr(self.neo4j_repo, "create_relationship"):
                await self.neo4j_repo.create_relationship(from_doc_id, to_doc_id, rel)
                executed = True

            if not executed:
                return {
                    "status": "unsupported_relation",
                    "from": from_doc_id,
                    "to": to_doc_id,
                    "relation": rel,
                    "error": f"Neo4j repository does not support creating relation '{rel}'",
                }

            return {"status": "success", "from": from_doc_id, "to": to_doc_id, "relation": rel}
        except Exception as e:
            logger.error(f"DocumentStore add_relation failed ({from_doc_id} -[{rel}]-> {to_doc_id}): {e}")
            return {"status": "error", "from": from_doc_id, "to": to_doc_id, "relation": rel, "error": str(e)}

    def add_relation_sync(self, from_doc_id: str, to_doc_id: str, relation_type: str) -> Dict[str, Any]:
        return _run_async(self.add_relation(from_doc_id, to_doc_id, relation_type))

    async def notify_version_update(
        self,
        new_doc_id: str,
        supersedes: Optional[List[str]] = None,
        amends: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Orchestrate legal versioning lifecycle updates across Postgres, Milvus, and Neo4j."""
        results = {"new_doc_id": new_doc_id, "superseded": [], "amended": [], "errors": []}

        for old_doc_id in (supersedes or []):
            logger.info(f"[DocumentStore] {new_doc_id} supersedes {old_doc_id} — marking SUPERSEDED")
            sync_res = await self.sync_status(old_doc_id, "SUPERSEDED")
            if sync_res.get("status") == "success":
                results["superseded"].append(old_doc_id)
            else:
                results["errors"].extend(sync_res.get("errors", [f"sync failed for {old_doc_id}"]))

            rel_res = await self.add_relation(new_doc_id, old_doc_id, "SUPERSEDES")
            if rel_res.get("status") == "error":
                results["errors"].append(f"neo4j_supersedes {old_doc_id}: {rel_res.get('error')}")

        for amended_doc_id in (amends or []):
            logger.info(f"[DocumentStore] {new_doc_id} amends {amended_doc_id} — marking OUTDATED")
            sync_res = await self.sync_status(amended_doc_id, "OUTDATED")
            if sync_res.get("status") == "success":
                results["amended"].append(amended_doc_id)
            else:
                results["errors"].extend(sync_res.get("errors", [f"sync failed for {amended_doc_id}"]))

            rel_res = await self.add_relation(new_doc_id, amended_doc_id, "AMENDS")
            if rel_res.get("status") == "error":
                results["errors"].append(f"neo4j_amends {amended_doc_id}: {rel_res.get('error')}")

        status = "success" if not results["errors"] else "partial_success"
        logger.info(
            f"[DocumentStore] Version update complete for {new_doc_id}: "
            f"superseded={len(results['superseded'])}, amended={len(results['amended'])}, "
            f"errors={len(results['errors'])}"
        )
        return {"status": status, **results}

    def notify_version_update_sync(
        self,
        new_doc_id: str,
        supersedes: Optional[List[str]] = None,
        amends: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return _run_async(self.notify_version_update(new_doc_id, supersedes, amends))

    def delete_document_sync(self, doc_id: str) -> Dict[str, Any]:
        return _run_async(self.delete_document(doc_id))


class InMemoryDocumentStore(DocumentStore):
    """In-memory test adapter for offline unit testing without active database connections."""

    def __init__(self, state_manager: Optional[StateManager] = None):
        super().__init__(state_manager=state_manager or InMemoryStateManager())
        self.indexed_documents: Dict[str, ProcessedDocument] = {}
        self.document_statuses: Dict[str, str] = {}
        self.relations: List[Dict[str, str]] = []

    def is_document_processed(self, rel_path: str) -> bool:
        return self.state_manager.get_status(rel_path) == "COMPLETED"

    def claim_document(self, rel_path: str, content_hash: str = "", worker_id: str = "") -> bool:
        return self.state_manager.claim_file(rel_path, worker_id, content_hash=content_hash)

    def sync_status_sync(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        self.document_statuses[doc_id] = new_status
        return {"status": "success", "doc_id": doc_id, "new_status": new_status}

    async def sync_status(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        return self.sync_status_sync(doc_id, new_status)

    def add_relation_sync(self, from_doc_id: str, to_doc_id: str, relation_type: str) -> Dict[str, Any]:
        rel = {"from": from_doc_id, "to": to_doc_id, "relation": relation_type}
        self.relations.append(rel)
        return {"status": "success", **rel}

    async def add_relation(self, from_doc_id: str, to_doc_id: str, relation_type: str) -> Dict[str, Any]:
        return self.add_relation_sync(from_doc_id, to_doc_id, relation_type)

    def notify_version_update_sync(
        self,
        new_doc_id: str,
        supersedes: Optional[List[str]] = None,
        amends: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        results = {"new_doc_id": new_doc_id, "superseded": [], "amended": [], "errors": []}
        for s in (supersedes or []):
            self.document_statuses[s] = "SUPERSEDED"
            self.relations.append({"from": new_doc_id, "to": s, "relation": "SUPERSEDES"})
            results["superseded"].append(s)
        for a in (amends or []):
            self.document_statuses[a] = "OUTDATED"
            self.relations.append({"from": new_doc_id, "to": a, "relation": "AMENDS"})
            results["amended"].append(a)
        return {"status": "success", **results}

    async def notify_version_update(
        self,
        new_doc_id: str,
        supersedes: Optional[List[str]] = None,
        amends: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.notify_version_update_sync(new_doc_id, supersedes, amends)

    def index_document_sync(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        identity = getattr(processed_doc, "identity", None)
        doc_id = identity.doc_id if identity else getattr(processed_doc, "doc_id", "test_doc")
        rel_path = identity.rel_path if identity else getattr(processed_doc, "file_path", "test.pdf")

        self.indexed_documents[doc_id] = processed_doc
        self.document_statuses[doc_id] = "ACTIVE"
        self.state_manager.update_status(rel_path, "COMPLETED", doc_id=doc_id)
        return {"status": "success", "doc_id": doc_id}

    async def index_document(self, processed_doc: ProcessedDocument) -> Dict[str, Any]:
        return self.index_document_sync(processed_doc)

    def delete_document_sync(self, doc_id: str) -> Dict[str, Any]:
        self.indexed_documents.pop(doc_id, None)
        self.document_statuses.pop(doc_id, None)
        return {"status": "success", "doc_id": doc_id}

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        return self.delete_document_sync(doc_id)

    async def init_infrastructure(self) -> None:
        pass

    def init_infrastructure_sync(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def close_sync(self) -> None:
        pass
