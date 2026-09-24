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

    async def init_schema(self) -> None:
        """Initialize Neo4j schema constraints and indexes for Document nodes."""
        query_constraint = "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE"
        query_index = "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doc_number)"
        try:
            async with self._driver.session() as session:
                await session.run(query_constraint)
                await session.run(query_index)
            logger.info("Neo4j schema constraints and indexes initialized successfully.")
        except Exception as e:
            logger.warning(f"Neo4j schema initialization skipped: {e}")

    @property
    def driver(self) -> AsyncDriver:
        """Underlying Neo4j driver connection. Provided for internal graph timeline traversal."""
        return self._driver

    async def close(self) -> None:
        """Safely close underlying Neo4j driver."""
        if self._driver:
            try:
                await self._driver.close()
            except Exception as e:
                logger.debug(f"Error closing Neo4j driver: {e}")

    async def get_legal_timeline(self, doc_number: str, max_hops: int = 10) -> list[dict]:
        """Iterative Cypher traversal to retrieve legal timeline for a document node."""
        if not doc_number or not self._driver:
            return []

        query = """
        MATCH (start:Document)
        USING INDEX start:Document(doc_number)
        WHERE start.doc_number = $doc_number OR start.id = $doc_number
        MATCH path = (start)-[:AMENDS|REPLACES|REFERENCES*0..10]->(current)
        WITH path, current
        ORDER BY length(path) DESC
        LIMIT 1
        RETURN
            [i in range(0, length(path)) | {
                doc_number: nodes(path)[i].doc_number,
                id: nodes(path)[i].id,
                effective_date: coalesce(nodes(path)[i].effective_date, nodes(path)[i].date, 'unknown'),
                status: coalesce(nodes(path)[i].status, 'UNKNOWN'),
                relation_to_next: CASE
                    WHEN i < length(path) THEN type(relationships(path)[i])
                    ELSE null
                END
            }] AS timeline
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, doc_number=doc_number)
                record = await result.single()
                if record and "timeline" in record:
                    return record["timeline"]
        except Exception as e:
            logger.error(f"Failed to retrieve legal timeline for {doc_number}: {e}")
        return []

    async def get_document_relations(self, doc_id: str):
        query = """
        MATCH (d:Document)
        WHERE d.id CONTAINS $query_id
        OPTIONAL MATCH (d)-[r:REPLACES|AMENDS|REFERENCES|GUIDES*1..3]->(target:Document)
        OPTIONAL MATCH (source:Document)-[r2:REPLACES|AMENDS|GUIDES*1..3]->(d)
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
        MATCH (d:Document)<-[:GUIDES|REFERENCES*1..2]-(guided:Document)
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

    async def create_supersedes_relation(self, new_doc_id: str, old_doc_id: str) -> None:
        """Create a SUPERSEDES relationship from new_doc → old_doc.

        Uses MERGE to prevent duplicate relationships.
        Also ensures both Document nodes exist (MERGE on node too).

        Cypher:
            (new_doc)-[:SUPERSEDES]->(old_doc)
        """
        query = """
        MERGE (new_doc:Document {id: $new_doc_id})
        MERGE (old_doc:Document {id: $old_doc_id})
        MERGE (new_doc)-[:SUPERSEDES]->(old_doc)
        SET old_doc.status = 'SUPERSEDED',
            new_doc.supersedes = coalesce(new_doc.supersedes, []) + $old_doc_id
        """
        try:
            async with self._driver.session() as session:
                await session.run(query, new_doc_id=new_doc_id, old_doc_id=old_doc_id)
            logger.info(f"Neo4j: Created SUPERSEDES {new_doc_id} → {old_doc_id}")
        except Exception as e:
            logger.error(f"Failed to create SUPERSEDES relation {new_doc_id}→{old_doc_id}: {e}")
            raise

    async def create_amends_relation(self, new_doc_id: str, amended_doc_id: str) -> None:
        """Create an AMENDS relationship from new_doc → amended_doc.

        Uses MERGE to prevent duplicate relationships.
        Unlike SUPERSEDES, the amended document stays partially valid (OUTDATED).

        Cypher:
            (new_doc)-[:AMENDS]->(amended_doc)
        """
        query = """
        MERGE (new_doc:Document {id: $new_doc_id})
        MERGE (amended_doc:Document {id: $amended_doc_id})
        MERGE (new_doc)-[:AMENDS]->(amended_doc)
        SET amended_doc.status = 'OUTDATED'
        """
        try:
            async with self._driver.session() as session:
                await session.run(query, new_doc_id=new_doc_id, amended_doc_id=amended_doc_id)
            logger.info(f"Neo4j: Created AMENDS {new_doc_id} → {amended_doc_id}")
        except Exception as e:
            logger.error(f"Failed to create AMENDS relation {new_doc_id}→{amended_doc_id}: {e}")
            raise

    async def get_superseded_by(self, doc_id: str) -> list[dict]:
        """Find which document(s) supersede the given doc_id.

        Useful for UI: 'This document has been replaced by X'.
        Returns list of {id, title, effective_date} for replacement docs.
        """
        query = """
        MATCH (newer:Document)-[:SUPERSEDES]->(old:Document {id: $doc_id})
        RETURN newer.id AS id,
               coalesce(newer.title, '') AS title,
               coalesce(newer.effective_date, '') AS effective_date
        ORDER BY newer.effective_date DESC
        LIMIT 5
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, doc_id=doc_id)
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Neo4j get_superseded_by failed for {doc_id}: {e}")
            return []

    async def create_document_node(self, processed_doc) -> None:
        """Create or update a Document node and its relationships in Neo4j."""
        identity = processed_doc.identity
        metadata = processed_doc.metadata
        doc_id = identity.doc_id
        doc_number = identity.doc_number
        file_name = identity.file_name
        rel_path = identity.rel_path

        doc_type = getattr(metadata, "doc_type", "UNKNOWN")
        authority = getattr(metadata, "authority", "UNKNOWN")
        doc_date = getattr(metadata, "date", "UNKNOWN")
        validity = getattr(metadata, "validity_status", "ACTIVE")

        query = """
        MERGE (d:Document {id: $doc_id})
        SET d.doc_number = $doc_number,
            d.file_name = $file_name,
            d.rel_path = $rel_path,
            d.doc_type = $doc_type,
            d.authority = $authority,
            d.doc_date = $doc_date,
            d.status = $validity
        """
        try:
            async with self._driver.session() as session:
                await session.run(
                    query,
                    doc_id=doc_id,
                    doc_number=doc_number,
                    file_name=file_name,
                    rel_path=rel_path,
                    doc_type=doc_type,
                    authority=authority,
                    doc_date=doc_date,
                    validity=validity,
                )

                relationships = getattr(processed_doc, "relationships", None)
                if relationships:
                    rel_dict = relationships.to_dict() if hasattr(relationships, "to_dict") else dict(relationships)
                    for replaced in (rel_dict.get("replaces") or []):
                        target_id = str(replaced).strip() if replaced else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:REPLACES]->(target)
                                SET target.status = 'SUPERSEDED'
                            """, source_id=doc_id, target_id=target_id)

                    for amended in (rel_dict.get("amends") or []):
                        target_id = str(amended).strip() if amended else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:AMENDS]->(target)
                                SET target.status = 'OUTDATED'
                            """, source_id=doc_id, target_id=target_id)

                    for referenced in (rel_dict.get("references") or []):
                        target_id = str(referenced).strip() if referenced else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:REFERENCES]->(target)
                            """, source_id=doc_id, target_id=target_id)

                    for guided in (rel_dict.get("guides") or []):
                        target_id = str(guided).strip() if guided else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:GUIDES]->(target)
                            """, source_id=doc_id, target_id=target_id)
        except Exception as e:
            logger.error(f"Failed to create Document node in Neo4j for {doc_id}: {e}")
            raise

    async def delete_document_node(self, doc_id: str) -> None:
        """Detach and delete a Document node by id."""
        query = "MATCH (d:Document) WHERE d.id = $doc_id or d.doc_number = $doc_id DETACH DELETE d"
        try:
            async with self._driver.session() as session:
                await session.run(query, doc_id=doc_id)
        except Exception as e:
            logger.error(f"Failed to delete Document node in Neo4j for {doc_id}: {e}")
            raise
