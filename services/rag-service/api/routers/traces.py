"""API endpoints for query reasoning trace inspection.

Provides visibility into how the RAG pipeline processed each query,
including cache decisions, retrieval scores, and latency breakdown.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Request, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/traces", tags=["Monitoring"])


@router.get("/recent")
async def get_recent_traces(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return the most recent query traces."""
    trace_store = getattr(request.app.state, "trace_store", None)
    if not trace_store:
        return {"traces": [], "error": "Trace store not initialized"}
    traces = await trace_store.get_recent(limit=limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/session/{session_id}")
async def get_session_traces(
    request: Request,
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return traces for a specific session."""
    trace_store = getattr(request.app.state, "trace_store", None)
    if not trace_store:
        return {"traces": [], "error": "Trace store not initialized"}
    traces = await trace_store.get_by_session(session_id, limit=limit)
    return {"traces": traces, "count": len(traces), "session_id": session_id}
