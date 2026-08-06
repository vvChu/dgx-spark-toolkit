import logging
from ingestion.state_manager import PostgresStateManager
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository

logger = logging.getLogger(__name__)


class LifecycleService:
    """
    Orchestrates document lifecycle operations across all data stores.
    """

    def __init__(
        self,
        state_manager: PostgresStateManager,
        milvus_repo: MilvusRepository,
        neo4j_repo: Neo4jRepository
    ):
        self.state_manager = state_manager
        self.milvus_repo = milvus_repo
        self.neo4j_repo = neo4j_repo

    async def sync_document_status(self, doc_id: str, new_status: str):
        """
        Synchronizes a document's legal status across Postgres, Milvus, and Neo4j.
        Valid statuses typically include: ACTIVE, OUTDATED, REPLACED.
        """
        logger.info(f"Starting cascading status sync for doc_id: {doc_id} -> {new_status}")

        errors = []

        # 1. Update Postgres State (Source of truth for ingestion files)
        try:
            self.state_manager.update_validity_status(doc_id, new_status)
        except Exception as e:
            errors.append(f"Postgres update failed: {e}")

        # 2. Update Milvus (Affects retrieval filtering/boosting)
        try:
            await self.milvus_repo.update_doc_validity(doc_id, new_status)
        except Exception as e:
            errors.append(f"Milvus update failed: {e}")

        # 3. Update Neo4j (Affects Knowledge Graph relationships and properties)
        try:
            await self.neo4j_repo.update_node_status(doc_id, new_status)
        except Exception as e:
            errors.append(f"Neo4j update failed: {e}")

        if errors:
            logger.error(f"Cascading sync for {doc_id} encountered errors: {errors}")
            return {"status": "partial_success", "errors": errors}

        logger.info(f"Successfully synchronized status for {doc_id} across all stores.")
        return {"status": "success", "doc_id": doc_id, "new_status": new_status}

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
