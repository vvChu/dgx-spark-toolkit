import os
from neo4j import AsyncDriver
import logging

logger = logging.getLogger(__name__)

class Neo4jRepository:
    """
    Repository pattern for encapsulating Neo4j Knowledge Graph queries.
    """
    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    @property
    def driver(self) -> AsyncDriver:
        """Expose the underlying driver for components that need direct access."""
        return self._driver

    async def get_document_relations(self, doc_id: str):
        query = """
        MATCH (d:Document)
        WHERE d.id CONTAINS $query_id
        OPTIONAL MATCH (d)-[r:REPLACES|AMENDS|REFERENCES*1..3]->(target:Document)
        OPTIONAL MATCH (source:Document)-[r2:REPLACES|AMENDS*1..3]->(d)
        RETURN d.id as id,
               CASE WHEN d.status IS NOT NULL THEN d.status ELSE 'UNKNOWN' END as status,
               [rel in coalesce(r, []) | type(rel)] as out_rels, [t in coalesce(target, []) | t.id] as targets,
               [rel in coalesce(r2, []) | type(rel)] as in_rels, [s in coalesce(source, []) | s.id] as sources
        LIMIT 10
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, query_id=doc_id)
                # Ensure we pull the data out fully while the session is alive
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return []
            
    async def get_guided_circulars(self, doc_id: str):
        query = """
        MATCH (d:Document)<-[:REFERENCES*1..2]-(guided:Document)
        WHERE d.id CONTAINS $query_id AND guided.doc_type = 'TT'
        RETURN d.id as source, guided.id as guided_id, guided.status as status
        LIMIT 15
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, query_id=doc_id)
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Graph guided circulars query failed: {e}")
            return []

    async def find_document_status(self, doc_ids: list[str]) -> dict[str, str]:
        """Fetch the status (ACTIVE, OUTDATED) for a list of document IDs."""
        status_map = {}
        query = "MATCH (d:Document) WHERE d.id IN $ids RETURN d.id as id, d.status as status"
        try:
            async with self._driver.session() as session:
                result = await session.run(query, ids=doc_ids)
                records = [record.data() async for record in result]
                for rec in records:
                    status_map[rec["id"]] = rec["status"]
            return status_map
        except Exception as e:
            logger.error(f"Failed to fetch document status from Graph: {e}")
            return {}

    async def update_node_status(self, doc_id: str, new_status: str):
        """Update the status property of a Document node."""
        query = "MATCH (d:Document {id: $doc_id}) SET d.status = $status"
        try:
            async with self._driver.session() as session:
                await session.run(query, doc_id=doc_id, status=new_status)
                logger.info(f"Successfully updated status to {new_status} for Document node: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to update Neo4j node status for {doc_id}: {e}")
            raise

    async def clear_db(self, confirm: bool = False):
        """Delete all nodes and relationships in Neo4j.

        Requires both ``confirm=True`` and the ``ALLOW_DB_CLEAR`` environment
        variable set to ``"1"`` to prevent accidental data loss.
        """
        if not confirm or os.environ.get("ALLOW_DB_CLEAR") != "1":
            raise RuntimeError(
                "clear_db() refused: pass confirm=True and set ALLOW_DB_CLEAR=1 to proceed."
            )
        query = "MATCH (n) DETACH DELETE n"
        try:
            async with self._driver.session() as session:
                await session.run(query)
                logger.info("Neo4j database cleared.")
        except Exception as e:
            logger.error(f"Failed to clear Neo4j DB: {e}")

    async def run_query(self, cypher: str, **params) -> list[dict]:
        """Execute an arbitrary read-only Cypher query and return all records as dicts.

        This provides a controlled escape hatch for routers that need custom
        queries (e.g. stats, graph visualization) without accessing _driver.
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(cypher, **params)
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Neo4j run_query failed: {e}")
            return []
