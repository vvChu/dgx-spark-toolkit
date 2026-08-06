from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os
import traceback

from core.database import lifespan
from core.config import get_settings
from core.logging_config import setup_logging
from api.routers import search, chat, admin, analysis
from api.routers import stats, graph, preview, evaluation
from api.routers import chat_stream, traces

__version__ = "2.0.0"

# Setup structured logging (JSON in prod, text in dev via LOG_FORMAT env)
setup_logging()
logger = logging.getLogger(__name__)

tags_metadata = [
    {"name": "General", "description": "General service information"},
    {"name": "Retrieval", "description": "Vector search and reranking operations"},
    {"name": "Generation", "description": "LLM interaction and RAG"},
    {"name": "Admin", "description": "Collection and document management"},
    {"name": "Visualization", "description": "Endpoints for graph and document preview"},
    {"name": "Monitoring", "description": "Service monitoring and statistics"}
]

app = FastAPI(
    title="BIM RAG Engine API (Refactored)",
    description="""
    Retrieval Augmented Generation service for BIM applications.
    Enterprise Architecture Version.
    """,
    version=__version__,
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

# Restrict CORS to the known frontend origin; uses Settings for single source of truth
_settings_cors = get_settings()
_allowed_origins = [o.strip() for o in _settings_cors.CORS_ALLOWED_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(analysis.router)
app.include_router(stats.router)
app.include_router(graph.router)
app.include_router(preview.router)
app.include_router(evaluation.router)
app.include_router(chat_stream.router)
app.include_router(traces.router)

# Rate Limiting
from core.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Monitoring - Prometheus Metrics
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, include_in_schema=False, tags=["Monitoring"])


# ── Global Exception Handler ────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — log the full traceback and return
    a structured 500 response.  Individual routers no longer need their own
    try/except for the generic case."""
    logger.error(
        "Unhandled %s on %s %s: %s",
        type(exc).__name__,
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/", tags=["General"])
async def root():
    return {"message": f"BIM RAG Service is running (v{__version__} Enterprise Structure)", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["General"])
async def health(request: Request):
    """Real health check — verifies Milvus and Neo4j connectivity."""
    checks = {}

    # Milvus — with auto-reconnect on channel failure
    milvus_client = getattr(request.app.state, "milvus_client", None)
    if milvus_client:
        try:
            await milvus_client.list_collections()
            checks["milvus"] = "ok"
        except Exception as e:
            err_msg = str(e)
            checks["milvus"] = f"error: {err_msg}"
            # Auto-reconnect on permanent channel/connection failures
            if "Channel is closed" in err_msg or "not ready" in err_msg:
                try:
                    from core.database import reconnect_milvus, state
                    await reconnect_milvus()
                    request.app.state.milvus_client = state.milvus_client
                    checks["milvus"] = "reconnected"
                except Exception as re_err:
                    checks["milvus"] = f"reconnect failed: {re_err}"
    else:
        checks["milvus"] = "not initialized"

    # Neo4j
    neo4j_driver = getattr(request.app.state, "neo4j_driver", None)
    if neo4j_driver:
        try:
            await neo4j_driver.verify_connectivity()
            checks["neo4j"] = "ok"
        except Exception as e:
            checks["neo4j"] = f"error: {e}"
    else:
        checks["neo4j"] = "not initialized"

    all_ok = all(v in ("ok", "reconnected") for v in checks.values())
    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if all_ok else "degraded", "version": __version__, "checks": checks}
    )


@app.get("/health/pipeline", tags=["Monitoring"])
async def pipeline_health(request: Request):
    """Health check for the ingestion pipeline subsystems (Redis queue, DB, state)."""
    checks = {}

    # Redis Queue (singleton from lifespan)
    rq = getattr(request.app.state, "redis_queue", None)
    if rq:
        try:
            checks["redis_queue"] = rq.health_check()
        except Exception as e:
            checks["redis_queue"] = {"status": "unavailable", "error": str(e)}
    else:
        checks["redis_queue"] = {"status": "unavailable", "error": "not initialized"}

    # Async PostgreSQL (singleton from lifespan)
    asm = getattr(request.app.state, "async_state_manager", None)
    if asm:
        try:
            checks["async_db"] = await asm.health_check()
            checks["async_db_summary"] = await asm.get_status_summary()
        except Exception as e:
            checks["async_db"] = {"status": "unavailable", "error": str(e)}
    else:
        checks["async_db"] = {"status": "unavailable", "error": "not initialized"}

    # Sync PostgreSQL (singleton from lifespan)
    sm = getattr(request.app.state, "state_manager", None)
    if sm:
        try:
            checks["sync_db"] = sm.health_check()
        except Exception as e:
            checks["sync_db"] = {"status": "unavailable", "error": str(e)}
    else:
        checks["sync_db"] = {"status": "unavailable", "error": "not initialized"}

    all_healthy = all(
        isinstance(v, dict) and v.get("status") == "healthy"
        for v in checks.values()
        if isinstance(v, dict) and "status" in v
    )
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={"pipeline_status": "healthy" if all_healthy else "degraded", "checks": checks}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)


@app.get("/health/circuits", tags=["Monitoring"])
async def circuit_breaker_health():
    """Health status of all LLM model circuit breakers.

    Returns state (closed/open/half_open), failure count, and recovery
    status for each model in the OCR fallback chain.
    """
    from core.circuit_breaker import all_circuit_statuses
    statuses = all_circuit_statuses()
    any_open = any(s.get("state") == "open" for s in statuses)
    return JSONResponse(
        status_code=503 if any_open else 200,
        content={
            "status": "degraded" if any_open else "ok",
            "circuits": statuses,
            "open_count": sum(1 for s in statuses if s.get("state") == "open"),
        }
    )


@app.get("/health/hitl", tags=["Monitoring"])
async def hitl_health():
    """HITL review queue status — shows pending expert review count."""
    try:
        from services.hitl_service import get_hitl_service
        hitl = get_hitl_service()
        queue_size = hitl.queue_size()
        pending = hitl.get_pending_reviews(limit=5)
        return {
            "status": "ok",
            "review_queue_size": queue_size,
            "sample_pending": [
                {
                    "query": p.get("query", "")[:80],
                    "reason": p.get("flagged_reason"),
                    "scores": p.get("retrieval_scores", []),
                }
                for p in pending
            ],
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})
