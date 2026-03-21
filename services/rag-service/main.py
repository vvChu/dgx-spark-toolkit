from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from core.database import lifespan
from api.routers import search, chat, admin, analysis, visualization

# Setup logging
logging.basicConfig(level=logging.INFO)
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
    version="2.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

# Restrict CORS to the known frontend origin; fall back to env var for flexibility
_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(analysis.router)
app.include_router(visualization.router)

# Monitoring - Prometheus Metrics
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, include_in_schema=False, tags=["Monitoring"])

@app.get("/", tags=["General"])
async def root():
    return {"message": "BIM RAG Service is running (v2.0 Enterprise Structure)", "docs": "/docs", "health": "/health"}

@app.get("/health", tags=["General"])
async def health(request: Request):
    """Real health check — verifies Milvus and Neo4j connectivity."""
    checks = {}

    # Milvus
    milvus_client = getattr(request.app.state, "milvus_client", None)
    if milvus_client:
        try:
            await milvus_client.list_collections()
            checks["milvus"] = "ok"
        except Exception as e:
            checks["milvus"] = f"error: {e}"
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

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if all_ok else "degraded", "version": "2.0.0", "checks": checks}
    )

@app.get("/health/pipeline", tags=["Monitoring"])
async def pipeline_health():
    """Health check for the ingestion pipeline subsystems (Redis queue, DB, state)."""
    checks = {}

    # Redis Queue
    try:
        from ingestion.queue import RedisQueue
        q = RedisQueue()
        checks["redis_queue"] = q.health_check()
    except Exception as e:
        checks["redis_queue"] = {"status": "unavailable", "error": str(e)}

    # Async PostgreSQL
    try:
        from ingestion.async_state_manager import AsyncStateManager
        sm = AsyncStateManager()
        await sm.init()
        checks["async_db"] = await sm.health_check()
        checks["async_db_summary"] = await sm.get_status_summary()
        await sm.close()
    except Exception as e:
        checks["async_db"] = {"status": "unavailable", "error": str(e)}

    # Sync PostgreSQL (existing)
    try:
        from ingestion.state_manager import PostgresStateManager
        sync_sm = PostgresStateManager()
        checks["sync_db"] = sync_sm.health_check()
    except Exception as e:
        checks["sync_db"] = {"status": "unavailable", "error": str(e)}

    from fastapi.responses import JSONResponse
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
    uvicorn.run("main:app", host="0.0.0.0", port=8006, reload=True)
