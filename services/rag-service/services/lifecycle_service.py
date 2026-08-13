import logging
from typing import Optional
from ingestion.state_manager import StateManager
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from repositories.document_store import DocumentStore

logger = logging.getLogger(__name__)


class LifecycleService:
    """
    Orchestrates document lifecycle operations across all data stores via DocumentStore.
    """

    def __init__(
        self,
        state_manager: StateManager,
        milvus_repo: MilvusRepository,
        neo4j_repo: Neo4jRepository,
        document_store: Optional[DocumentStore] = None,
    ):
        self.state_manager = state_manager
        self.milvus_repo = milvus_repo
        self.neo4j_repo = neo4j_repo
        self.document_store = document_store or DocumentStore(
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            state_manager=state_manager,
        )

    async def sync_document_status(self, doc_id: str, new_status: str):
        """
        Synchronizes a document's legal status across Postgres, Milvus, and Neo4j via DocumentStore.
        Valid statuses typically include: ACTIVE, OUTDATED, REPLACED.
        """
        return await self.document_store.sync_status(doc_id, new_status)

    async def notify_new_document_ingested(
        self,
        new_doc_id: str,
        supersedes: list[str] | None = None,
        amends: list[str] | None = None,
    ) -> dict:
        """Automated versioning hook called after a new document is indexed.

        Automatically:
          1. Marks superseded docs as SUPERSEDED in Milvus + Neo4j + Postgres
          2. Creates SUPERSEDES / AMENDS relationships in Neo4j
          3. Returns a summary of all changes made

        Args:
            new_doc_id:  doc_id of the newly ingested document.
            supersedes:  List of doc_ids fully replaced by new_doc_id.
            amends:      List of doc_ids partially amended by new_doc_id.
        """
        results = {"new_doc_id": new_doc_id, "superseded": [], "amended": [], "errors": []}

        for old_doc_id in (supersedes or []):
            logger.info(f"[Lifecycle] {new_doc_id} supersedes {old_doc_id} — marking SUPERSEDED")
            try:
                await self.sync_document_status(old_doc_id, "SUPERSEDED")
                results["superseded"].append(old_doc_id)
            except Exception as e:
                results["errors"].append(f"supersede {old_doc_id}: {e}")

            # Create graph relationship
            try:
                await self.neo4j_repo.create_supersedes_relation(new_doc_id, old_doc_id)
            except Exception as e:
                results["errors"].append(f"neo4j_supersedes {old_doc_id}: {e}")
                logger.warning(f"[Lifecycle] Neo4j SUPERSEDES relation failed for {old_doc_id}: {e}")

        for amended_doc_id in (amends or []):
            logger.info(f"[Lifecycle] {new_doc_id} amends {amended_doc_id} — marking OUTDATED")
            try:
                await self.sync_document_status(amended_doc_id, "OUTDATED")
                results["amended"].append(amended_doc_id)
            except Exception as e:
                results["errors"].append(f"amend {amended_doc_id}: {e}")

            try:
                await self.neo4j_repo.create_amends_relation(new_doc_id, amended_doc_id)
            except Exception as e:
                results["errors"].append(f"neo4j_amends {amended_doc_id}: {e}")

        status = "success" if not results["errors"] else "partial_success"
        logger.info(
            f"[Lifecycle] Ingestion notification complete for {new_doc_id}: "
            f"superseded={len(results['superseded'])}, amended={len(results['amended'])}, "
            f"errors={len(results['errors'])}"
        )
        return {"status": status, **results}
