"""Production ingestion pipeline for Vietnamese legal documents.

This is the main entry point for the RAG ingestion workers. The ProductionIngestor
class composes focused mixins for metadata, extraction, indexing, graph, and runner
logic. The legacy process_file() method is kept as a fallback when the stage-based
orchestrator (ingestion/orchestrator.py + ingestion/stages/) is unavailable.

Usage (Docker):
    python -m ingestion.pipeline
"""
import logging
import os as _os

# Only configure root logger if it has no handlers yet (avoids clobbering FastAPI/uvicorn logging).
if not logging.root.handlers:
    from logging.handlers import RotatingFileHandler as _RotatingHandler
    _log_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "ingestion.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            _RotatingHandler(
                _os.path.normpath(_log_path),
                maxBytes=50 * 1024 * 1024,  # 50 MB per file
                backupCount=3,
            ),
            logging.StreamHandler()
        ]
    )
logger = logging.getLogger(__name__)

import os
import time
import hashlib
import re
import httpx
import threading
from concurrent.futures import ThreadPoolExecutor
from pymilvus import connections
from neo4j import GraphDatabase
from pymilvus import AsyncMilvusClient
from neo4j import AsyncGraphDatabase
from prometheus_client import start_http_server, Gauge, Counter

from core.config import get_settings
from ingestion.vision import VisionExtractor
from ingestion.chunking import DocumentChunker
from ingestion.exporter import DataExporter
from ingestion.text_normalizer import (
    rejoin_paragraphs, detect_garbled_table,
    strip_document_boilerplate, strip_noi_nhan_block, strip_signer_block,
)
from ingestion.legal_taxonomy import classify_all, classify_source_category
from ingestion.state_manager import PostgresStateManager
from ingestion.pipeline_config import (
    MAX_WORKERS, SOURCE_DIR,
)
from ingestion import pipeline_config
from ingestion.mixins import (
    MetadataMixin, ExtractionMixin, IndexingMixin, GraphMixin, RunnerMixin,
)
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.lifecycle_service import LifecycleService

# Prometheus Metrics
INGESTION_WORKERS_ACTIVE = Gauge('ingestion_workers_active', 'Number of active ingestion workers')
VISION_FALLBACK_COUNT = Counter('vision_fallback_pipeline_total', 'Total pages routed to Vision Fallback in pipeline')
PAGE_PROCESS_TOTAL = Counter('page_process_total', 'Total pages processed')
INGESTION_LATENCY = Gauge('ingestion_latency_seconds', 'Latency of last file processing')


class ProductionIngestor(MetadataMixin, ExtractionMixin, IndexingMixin, GraphMixin, RunnerMixin):
    """Main ingestion orchestrator composing focused mixins.

    Pipeline: safe_process() → PipelineOrchestrator → 9 stages
    """

    def __init__(self):
        # Load settings-dependent config (Milvus host/port, collection name, etc.)
        pipeline_config._load()
        from core.config import get_settings
        settings = get_settings()

        self.vision = VisionExtractor()
        vllm_model = os.environ.get("VLLM_MODEL", "rag-core")
        logger.info(f"Initializing LLM via Gateway: {vllm_model} | Embedding: BAAI/bge-m3")

        from services.retrieval_service import get_embedding_model
        self.model = get_embedding_model()
        self.chunker = DocumentChunker()
        self.state_manager = PostgresStateManager()
        self.exporter = DataExporter(settings.EXPORT_DIR) if settings.EXPORT_PROCESSED_DATA else None
        self.neo4j_driver = GraphDatabase.driver(
            pipeline_config.NEO4J_URI, auth=(pipeline_config.NEO4J_USER, pipeline_config.NEO4J_PASS)
        )
        self._http_client = httpx.Client(timeout=300)

        # Async Bridge for lifecycle management
        self._async_milvus = AsyncMilvusClient(
            uri=f"http://{pipeline_config.MILVUS_HOST}:{pipeline_config.MILVUS_PORT}"
        )
        self._async_neo4j = AsyncGraphDatabase.driver(
            pipeline_config.NEO4J_URI, auth=(pipeline_config.NEO4J_USER, pipeline_config.NEO4J_PASS)
        )
        self.lifecycle_service = LifecycleService(
            self.state_manager,
            MilvusRepository(self._async_milvus),
            Neo4jRepository(self._async_neo4j),
        )

        self.init_neo4j()
        self.connect_milvus()
        self.collection = self.setup_collection()
        self.processed_cache: set = set()
        self._processed_cache_lock = threading.Lock()
        self.load_processed_cache()

        # Initialize the stage-based orchestrator
        from ingestion.orchestrator import PipelineOrchestrator
        self._orchestrator = PipelineOrchestrator(self)
        logger.info("PipelineOrchestrator initialized ✓")

    def close(self):
        """Explicitly close all resource pools."""
        try:
            if hasattr(self, 'neo4j_driver') and self.neo4j_driver:
                self.neo4j_driver.close()
            if hasattr(self, '_async_neo4j') and self._async_neo4j:
                self._async_neo4j.close()
            if hasattr(self, '_async_milvus') and self._async_milvus:
                self._async_milvus.close()
            if hasattr(self, '_http_client') and self._http_client:
                self._http_client.close()
            logger.info("ProductionIngestor resources closed safely.")
        except Exception as e:
            logger.warning(f"Error during ProductionIngestor cleanup: {e}")

    def load_processed_cache(self):
        """Load all COMPLETED file paths from Postgres to allow fast skipping."""
        try:
            all_state = self.state_manager.get_all_state()
            new_cache = {f for f, s in all_state.items() if s["status"] == 'COMPLETED'}
            with self._processed_cache_lock:
                self.processed_cache = new_cache
            logger.info(f"Loaded {len(new_cache)} files into fast-skip cache.")
        except Exception as e:
            logger.error(f"Failed to load processed cache: {e}")

    def init_neo4j(self):
        with self.neo4j_driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            session.run("CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doc_number)")
        logger.info("Neo4j initialized")

    def connect_milvus(self):
        connections.connect(host=pipeline_config.MILVUS_HOST, port=pipeline_config.MILVUS_PORT)
        logger.info(f"Connected to Milvus at {pipeline_config.MILVUS_HOST}:{pipeline_config.MILVUS_PORT}")

    def claim_file(self, file_hash, rel_path):
        """Try to claim a file for processing using PostgreSQL to coordinate between workers."""
        worker_id = os.getenv("HOSTNAME", "worker-" + str(os.getpid()))
        return self.state_manager.claim_file(rel_path, worker_id, content_hash=file_hash)

    def mark_file_done(self, file_hash):
        try:
            with self.neo4j_driver.session() as session:
                session.run(
                    "MATCH (f:File {hash: $hash}) SET f.status = 'PROCESSED', f.processed_at = timestamp()",
                    hash=file_hash,
                )
        except Exception as e:
            logger.error(f"Error marking file as done in Neo4j: {e}")

    def get_file_hash(self, file_path):
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def safe_process(self, f):
        INGESTION_WORKERS_ACTIVE.inc()
        start_time = time.time()

        try:
            self._orchestrator.run_pipeline(f)
            INGESTION_LATENCY.set(time.time() - start_time)
        except Exception as e:
            logger.error(f"  Failed to process {f}: {e}")
            try:
                rel_path = os.path.relpath(f, SOURCE_DIR)
                self.state_manager.update_status(rel_path, 'FAILED', error=str(e))
            except Exception as inner_e:
                logger.error(f"  Critical: Could not update failure status for {f}: {inner_e}")
        finally:
            INGESTION_WORKERS_ACTIVE.dec()


if __name__ == "__main__":
    try:
        start_http_server(8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as e:
        logger.error(f"Could not start prometheus server: {e}")

    time.sleep(5)
    ingestor = ProductionIngestor()
    ingestor.run()
