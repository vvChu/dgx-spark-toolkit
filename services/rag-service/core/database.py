from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager
from neo4j import AsyncGraphDatabase
from pymilvus import AsyncMilvusClient
import httpx
import logging

from core.config import get_settings
from repositories.neo4j_repo import Neo4jRepository
from repositories.milvus_repo import MilvusRepository
from ingestion.state_manager import PostgresStateManager

logger = logging.getLogger(__name__)

# Global state holder for the application lifecycle


class AppState:
    neo4j_driver = None
    milvus_client = None
    _milvus_uri: str = None
    state_manager: PostgresStateManager = None
    http_client: httpx.AsyncClient = None
    redis_queue = None
    async_state_manager = None


state = AppState()


async def _create_milvus_client(uri: str) -> AsyncMilvusClient:
    """Create a new AsyncMilvusClient. Factored out for reconnect reuse."""
    return AsyncMilvusClient(uri=uri)


async def reconnect_milvus():
    """Tear down a dead Milvus client and create a fresh one.

    Called automatically by the /health endpoint when it detects
    'Channel is closed' or similar unrecoverable gRPC errors.
    """
    if state.milvus_client:
        try:
            await state.milvus_client.close()
        except Exception:
            pass  # channel is already dead, ignore
    state.milvus_client = await _create_milvus_client(state._milvus_uri)
    logger.warning("Milvus client reconnected to %s", state._milvus_uri)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle startup and shutdown of database connections globally.
    """
    settings = get_settings()

    # Init Neo4j
    try:
        neo4j_pwd = settings.NEO4J_PASSWORD.get_secret_value()
        state.neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, neo4j_pwd)
        )
        logger.info("Successfully connected to Neo4j.")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        state.neo4j_driver = None

    # Init Milvus
    try:
        uri = f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}"
        state._milvus_uri = uri
        state.milvus_client = await _create_milvus_client(uri)
        logger.info(f"Successfully connected to Milvus at {uri}.")
    except Exception as e:
        logger.error(f"Failed to connect to Milvus: {e}")
        state.milvus_client = None

    # Init Postgres State Manager
    try:
        state.state_manager = PostgresStateManager()
        logger.info("Successfully initialized PostgresStateManager.")
    except Exception as e:
        logger.error(f"Failed to initialize PostgresStateManager: {e}")
        state.state_manager = None

    # Shared HTTP client — reuses connection pool across all requests
    state.http_client = httpx.AsyncClient(timeout=120.0)

    # Init Redis Queue (singleton — avoids per-request connection leak)
    try:
        from ingestion.queue import RedisQueue
        state.redis_queue = RedisQueue()
        logger.info("Successfully initialized RedisQueue.")
    except Exception as e:
        logger.error(f"Failed to initialize RedisQueue: {e}")
        state.redis_queue = None

    # Init IngestionQueue (unified deep queue)
    try:
        from ingestion.ingestion_queue import IngestionQueue
        state.ingestion_queue = IngestionQueue(redis_queue=state.redis_queue, state_manager=state.state_manager)
        logger.info("Successfully initialized IngestionQueue.")
    except Exception as e:
        logger.error(f"Failed to initialize IngestionQueue: {e}")
        state.ingestion_queue = None

    # Init Async State Manager (singleton — avoids per-request pool leak)
    state.async_state_manager = state.state_manager

    # ── Context Lake Services ──────────────────────────────────────────
    redis_url = settings.REDIS_URL

    # Session Memory (Redis DB 2)
    try:
        from retrieval.session_memory import SessionMemory
        state.session_memory = SessionMemory(redis_url, ttl_seconds=settings.SESSION_MEMORY_TTL)
        logger.info("Context Lake: SessionMemory initialized (DB 2, TTL=%ds).", settings.SESSION_MEMORY_TTL)
    except Exception as e:
        logger.error(f"Failed to initialize SessionMemory: {e}")
        state.session_memory = None

    # Query Trace Store (Redis DB 2)
    try:
        from retrieval.query_tracer import TraceStore
        state.trace_store = TraceStore(redis_url)
        logger.info("Context Lake: TraceStore initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize TraceStore: {e}")
        state.trace_store = None

    # Context Accumulator (Redis DB 2)
    try:
        from retrieval.context_accumulator import ContextAccumulator
        state.context_accumulator = ContextAccumulator(redis_url)
        logger.info("Context Lake: ContextAccumulator initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize ContextAccumulator: {e}")
        state.context_accumulator = None

    # Attach to app state for requests
    app.state.neo4j_driver = state.neo4j_driver
    app.state.milvus_client = state.milvus_client
    app.state.state_manager = state.state_manager
    app.state.http_client = state.http_client
    app.state.redis_queue = state.redis_queue
    app.state.ingestion_queue = getattr(state, "ingestion_queue", None)
    app.state.async_state_manager = state.async_state_manager
    app.state.session_memory = getattr(state, "session_memory", None)
    app.state.trace_store = getattr(state, "trace_store", None)
    app.state.context_accumulator = getattr(state, "context_accumulator", None)

    yield

    # Shutdown
    for name in ("session_memory", "trace_store", "context_accumulator"):
        svc = getattr(state, name, None)
        if svc and hasattr(svc, "close"):
            await svc.close()
            logger.info(f"Context Lake: {name} closed.")
    if state.async_state_manager:
        await state.async_state_manager.close()
        logger.info("AsyncStateManager closed.")
    if state.neo4j_driver:
        await state.neo4j_driver.close()
        logger.info("Neo4j connection closed.")
    if state.milvus_client:
        await state.milvus_client.close()
        logger.info("Milvus connection closed.")
    if state.http_client:
        await state.http_client.aclose()
        logger.info("HTTP client closed.")

# --- Dependencies for FastAPI Routers ---


async def get_neo4j_repo(request: Request) -> Neo4jRepository:
    """Dependency to inject the Neo4jRepository."""
    if not request.app.state.neo4j_driver:
        raise RuntimeError("Neo4j driver is not initialized.")
    return Neo4jRepository(request.app.state.neo4j_driver)


async def get_milvus_repo(request: Request) -> MilvusRepository:
    """Dependency to inject the MilvusRepository."""
    if not request.app.state.milvus_client:
        raise RuntimeError("Milvus client is not initialized.")
    return MilvusRepository(request.app.state.milvus_client)


async def get_state_manager(request: Request) -> PostgresStateManager:
    """Dependency to inject the PostgresStateManager."""
    if not request.app.state.state_manager:
        raise RuntimeError("Postgres state manager is not initialized.")
    return request.app.state.state_manager


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Dependency to inject the shared HTTP client."""
    return request.app.state.http_client


async def get_legal_analysis_service(
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    http_client: httpx.AsyncClient = Depends(get_http_client)
) -> "LegalAnalysisService":
    """Dependency to inject the LegalAnalysisService."""
    from services.legal_analysis_service import LegalAnalysisService
    from retrieval.graph_timeline_retriever import AdvancedGraphRAG

    graph_rag = AdvancedGraphRAG(neo4j_repo.driver, http_client)
    return LegalAnalysisService(milvus_repo, graph_rag, http_client)


async def get_compliance_service(
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    http_client: httpx.AsyncClient = Depends(get_http_client)
) -> "ComplianceService":
    """Dependency to inject the ComplianceService."""
    from services.compliance_service import ComplianceService
    from retrieval.graph_timeline_retriever import AdvancedGraphRAG

    graph_rag = AdvancedGraphRAG(neo4j_repo.driver, http_client)
    return ComplianceService(milvus_repo, graph_rag, http_client)


async def get_search_pipeline(
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
):
    """Dependency to inject deep SearchPipeline."""
    from retrieval.search_pipeline import SearchPipeline
    return SearchPipeline(milvus_repo, neo4j_repo)


async def get_retrieval_service(
    pipeline=Depends(get_search_pipeline),
):
    """Dependency alias for backward compatibility."""
    return pipeline


async def get_chat_service(
    request: Request,
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> "ChatService":
    """Dependency to inject the ChatService with Context Lake services."""
    from services.chat_service import ChatService
    return ChatService(
        milvus_repo, neo4j_repo, http_client,
        session_memory=getattr(request.app.state, "session_memory", None),
        trace_store=getattr(request.app.state, "trace_store", None),
        context_accumulator=getattr(request.app.state, "context_accumulator", None),
    )


async def get_ingestion_queue(request: Request):
    """Dependency to inject deep IngestionQueue."""
    return getattr(request.app.state, "ingestion_queue", None)

