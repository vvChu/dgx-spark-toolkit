"""Knowledge graph visualization endpoints."""
from fastapi import APIRouter, Depends, Query
from core.database import get_neo4j_repo
from repositories.neo4j_repo import Neo4jRepository
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["Visualization"])


@router.get("/data", tags=["Visualization"])
async def get_graph_data(
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    limit: int = Query(200, ge=1, le=2000),
):
    """Return nodes and links for the force-directed graph visualization."""
    nodes, links = [], []

    try:
        async with neo4j_repo._driver.session() as session:
            result = await session.run(
                "MATCH (d:Document) RETURN d.doc_id AS id, d.title AS name, d.doc_type AS group LIMIT $limit",
                limit=limit,
            )
            records = [r async for r in result]
            for r in records:
                nodes.append({"id": r["id"], "name": r["name"] or r["id"], "group": r["group"] or "other"})

            result = await session.run(
                "MATCH (a:Document)-[r]->(b:Document) RETURN a.doc_id AS source, b.doc_id AS target, type(r) AS type LIMIT $limit",
                limit=limit * 3,
            )
            records = [r async for r in result]
            for r in records:
                links.append({"source": r["source"], "target": r["target"], "type": r["type"]})
    except Exception as e:
        logger.warning(f"Graph data error: {e}")

    return {"nodes": nodes, "links": links}


@router.get("/neighbors/{node_id}", tags=["Visualization"])
async def get_graph_neighbors(
    node_id: str,
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
):
    """Expand a node — return its immediate neighbors and connecting edges."""
    nodes, links = [], []

    try:
        async with neo4j_repo._driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Document {doc_id: $node_id})-[r]-(n:Document)
                RETURN n.doc_id AS id, n.title AS name, n.doc_type AS group,
                       type(r) AS rtype, startNode(r).doc_id AS src, endNode(r).doc_id AS tgt
                """,
                node_id=node_id,
            )
            records = [r async for r in result]
            seen = set()
            for r in records:
                nid = r["id"]
                if nid not in seen:
                    nodes.append({"id": nid, "name": r["name"] or nid, "group": r["group"] or "other"})
                    seen.add(nid)
                links.append({"source": r["src"], "target": r["tgt"], "type": r["rtype"]})
    except Exception as e:
        logger.warning(f"Graph neighbors error: {e}")

    return {"nodes": nodes, "links": links}
