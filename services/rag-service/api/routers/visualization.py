"""Visualization & dashboard endpoints — stats, graph, preview, evaluate, feedback."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from core.database import get_milvus_repo, get_neo4j_repo, get_http_client
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from models.schemas import EvaluationRequest, EvaluationResponse, FeedbackRequest

import base64
import fitz  # PyMuPDF
import httpx
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Visualization"])

COLLECTION = os.getenv("MILVUS_COLLECTION", "legal_docs_v9")
PDF_DIR = os.getenv("PDF_DIR", "/app/data/pdf")


# ── Stats ───────────────────────────────────────────────────────────────
@router.get("/stats", tags=["Monitoring"])
async def get_stats(
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
):
    """Aggregate stats from Milvus + Neo4j for the dashboard header."""
    stats = {"neo4j_docs": 0, "neo4j_rels": 0, "milvus_entities": 0, "total_target": 8870}

    try:
        info = await milvus_repo._client.get_collection_stats(COLLECTION)
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


# ── Graph Data ──────────────────────────────────────────────────────────
@router.get("/graph/data", tags=["Visualization"])
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


@router.get("/graph/neighbors/{node_id}", tags=["Visualization"])
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


# ── Document Preview ────────────────────────────────────────────────────
@router.get("/preview", tags=["Visualization"])
async def preview_page(
    source: str = Query(..., description="Document ID"),
    page: int = Query(1, ge=1),
):
    """Render a PDF page as a base64-encoded PNG image."""
    # Try to find the PDF by doc_id pattern
    pdf_path = _resolve_pdf(source)
    if not pdf_path:
        raise HTTPException(status_code=404, detail=f"PDF not found for {source}")

    try:
        doc = fitz.open(pdf_path)
        if page > len(doc):
            page = len(doc)
        pix = doc[page - 1].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()
        return {
            "source": source,
            "page": page,
            "image_b64": base64.b64encode(img_bytes).decode(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render error: {e}")


def _resolve_pdf(source: str) -> str | None:
    """Find a PDF file matching the given document ID."""
    # Direct match
    candidate = os.path.join(PDF_DIR, f"{source}.pdf")
    if os.path.isfile(candidate):
        return candidate
    # Search recursively
    for root, _, files in os.walk(PDF_DIR):
        for f in files:
            if f.endswith(".pdf") and source in f:
                return os.path.join(root, f)
    return None


# ── Evaluation ──────────────────────────────────────────────────────────
@router.post("/evaluate", response_model=EvaluationResponse, tags=["Monitoring"])
async def evaluate(
    request: EvaluationRequest,
    http_client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    Evaluate RAG answer quality (faithfulness + relevancy) using the LLM.
    Lightweight LLM-as-judge implementation.
    """
    from core.config import get_settings
    settings = get_settings()
    gateway_url = settings.VLLM_API_BASE
    model = settings.DEFAULT_RAG_MODEL

    context_text = "\n---\n".join(request.context[:5])  # Cap context length

    eval_prompt = f"""You are an expert evaluator for a Vietnamese legal RAG system.

Given:
- Question: {request.query}
- Answer: {request.answer}
- Retrieved Context: {context_text}

Evaluate on two dimensions:
1. **Faithfulness** (0.0-1.0): Is the answer fully supported by the context? No hallucinations?
2. **Relevancy** (0.0-1.0): Does the answer address the question using the context?

Respond in JSON:
{{"faithfulness": <float>, "relevancy": <float>, "faithfulness_reason": "<1 sentence>", "relevancy_reason": "<1 sentence>", "suggestions": ["<optional improvement>"]}}
"""

    try:
        resp = await http_client.post(
            f"{gateway_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": eval_prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        import json
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
        return EvaluationResponse(**result)
    except Exception as e:
        logger.error(f"Evaluation error: {e}", exc_info=True)
        return EvaluationResponse(
            faithfulness=0.5,
            relevancy=0.5,
            faithfulness_reason="Evaluation failed — returning default scores.",
            relevancy_reason=str(e),
            suggestions=["Retry evaluation"],
        )


# ── Feedback ────────────────────────────────────────────────────────────
@router.post("/feedback", tags=["Monitoring"])
async def submit_feedback(request: FeedbackRequest):
    """
    Log user feedback. Currently writes to structured log;
    can be extended to persist in PostgreSQL.
    """
    logger.info(
        "USER_FEEDBACK",
        extra={
            "query": request.query[:200],
            "is_positive": request.is_positive,
            "comment": request.comment,
        },
    )
    return {"status": "ok", "message": "Feedback recorded"}
