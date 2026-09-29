"""Knowledge graph visualization endpoints."""
from typing import Optional
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
        node_records = await neo4j_repo.run_query(
            "MATCH (d:Document) RETURN d.doc_id AS id, d.title AS name, d.doc_type AS group LIMIT $limit",
            limit=limit,
        )
        for r in node_records:
            nodes.append({"id": r["id"], "name": r["name"] or r["id"], "group": r["group"] or "other"})

        link_records = await neo4j_repo.run_query(
            "MATCH (a:Document)-[r]->(b:Document) RETURN a.doc_id AS source, b.doc_id AS target, type(r) AS type LIMIT $limit",
            limit=limit * 3,
        )
        for r in link_records:
            links.append({"source": r["source"], "target": r["target"], "type": r["type"]})
    except Exception as e:
        logger.warning(f"Graph data error: {e}")

    return {"nodes": nodes, "links": links}


@router.get("/neighbors", tags=["Visualization"])
@router.get("/neighbors/{node_id:path}", tags=["Visualization"])
async def get_graph_neighbors(
    node_id: Optional[str] = None,
    id: Optional[str] = Query(None),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
):
    """Expand a node — return its immediate neighbors and connecting edges."""
    target_id = (node_id or id or "").strip()
    nodes, links = [], []
    if not target_id:
        return {"nodes": nodes, "links": links}

    try:
        records = await neo4j_repo.run_query(
            """
            MATCH (d:Document)
            WHERE d.id = $node_id OR d.doc_number = $node_id OR d.id = ('VBPL/' + $node_id)
            OPTIONAL MATCH (d)-[r]-(n:Document)
            RETURN d.id AS target_id, coalesce(d.title, d.doc_number, d.id) AS target_name, coalesce(d.doc_type, 'target') AS target_group,
                   n.id AS id, coalesce(n.title, n.doc_number, n.id) AS name, coalesce(n.doc_type, 'other') AS group,
                   type(r) AS rtype, startNode(r).id AS src, endNode(r).id AS tgt
            """,
            node_id=target_id,
        )
        seen = set()
        for r in records:
            tid = r.get("target_id")
            if tid and tid not in seen:
                nodes.append({"id": tid, "name": r.get("target_name") or tid, "group": r.get("target_group") or "target"})
                seen.add(tid)
            nid = r.get("id")
            if nid and nid not in seen:
                nodes.append({"id": nid, "name": r.get("name") or nid, "group": r.get("group") or "other"})
                seen.add(nid)
            if r.get("src") and r.get("tgt"):
                links.append({"source": r["src"], "target": r["tgt"], "type": r.get("rtype")})
    except Exception as e:
        logger.warning(f"Graph neighbors error: {e}")

    return {"nodes": nodes, "links": links}
