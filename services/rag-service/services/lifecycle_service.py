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
