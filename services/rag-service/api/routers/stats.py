"""Dashboard aggregate stats endpoint."""
from fastapi import APIRouter, Depends
from core.config import get_settings
from core.database import get_milvus_repo, get_neo4j_repo
from models.schemas import StatsResponse
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Monitoring"])


@router.get("/stats", tags=["Monitoring"], response_model=StatsResponse)
async def get_stats(
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
):
    """Aggregate stats from Milvus + Neo4j for the dashboard header."""
    settings = get_settings()
    collection = settings.MILVUS_COLLECTION
    stats = {"neo4j_docs": 0, "neo4j_rels": 0, "milvus_entities": 0, "total_target": 8870}

    try:
        info = await milvus_repo._client.get_collection_stats(collection)
        stats["milvus_entities"] = info.get("row_count", 0)
    except Exception as e:
        logger.warning(f"Milvus stats error: {e}")

    try:
        async with neo4j_repo._driver.session() as session:
            result = await session.run(
                "MATCH (d:Document) RETURN count(d) AS docs"
            )
            record = await result.single()
            stats["neo4j_docs"] = record["docs"] if record else 0

            result = await session.run(
                "MATCH ()-[r]->() RETURN count(r) AS rels"
            )
            record = await result.single()
            stats["neo4j_rels"] = record["rels"] if record else 0
    except Exception as e:
        logger.warning(f"Neo4j stats error: {e}")

    return stats
