import logging
from typing import Optional, List, Dict, Any
from repositories.document_store import DocumentStore, InMemoryDocumentStore

logger = logging.getLogger(__name__)


class LifecycleService:
    """
    Orchestrates document lifecycle and versioning operations via DocumentStore.
    """

    def __init__(
        self,
        state_manager: Any = None,
        milvus_repo: Any = None,
        neo4j_repo: Any = None,
        document_store: Optional[DocumentStore] = None,
    ):
        if document_store is not None:
            self.document_store = document_store
        elif state_manager is not None or milvus_repo is not None or neo4j_repo is not None:
            self.document_store = DocumentStore(
                milvus_repo=milvus_repo,
                neo4j_repo=neo4j_repo,
                state_manager=state_manager,
            )
        else:
            self.document_store = InMemoryDocumentStore()

        self.state_manager = getattr(self.document_store, "state_manager", None)
        self.milvus_repo = getattr(self.document_store, "milvus_repo", None)
        self.neo4j_repo = getattr(self.document_store, "neo4j_repo", None)

    async def sync_document_status(self, doc_id: str, new_status: str) -> Dict[str, Any]:
        """
        Synchronizes a document's legal status across Postgres, Milvus, and Neo4j via DocumentStore.
        Valid statuses typically include: ACTIVE, OUTDATED, SUPERSEDED, REPLACED.
        """
        return await self.document_store.sync_status(doc_id, new_status)

    async def notify_new_document_ingested(
        self,
        new_doc_id: str,
        supersedes: Optional[List[str]] = None,
        amends: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Automated versioning hook called after a new document is indexed."""
        return await self.document_store.notify_version_update(
            new_doc_id=new_doc_id,
            supersedes=supersedes,
            amends=amends,
        )
