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
    _log_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "ingestion.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(_os.path.normpath(_log_path)),
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

    Primary path: safe_process() → PipelineOrchestrator → 9 stages
    Legacy path:  safe_process() → process_file() (monolithic fallback)
    """

    def __init__(self):
        # Load settings-dependent config (Milvus host/port, collection name, etc.)
        pipeline_config._load()
        from core.config import get_settings
        settings = get_settings()

        self.vision = VisionExtractor()
        logger.info("Initializing Embedding Model using qwen3.5-9b-rag")

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
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def safe_process(self, f):
        INGESTION_WORKERS_ACTIVE.inc()
        start_time = time.time()

        try:
            if not hasattr(self, '_orchestrator'):
                try:
                    from ingestion.orchestrator import PipelineOrchestrator
                    self._orchestrator = PipelineOrchestrator(self)
                    logger.info("Using stage-based PipelineOrchestrator ✓")
                except ImportError:
                    self._orchestrator = None
                    logger.info("Orchestrator not available — using legacy process_file()")

            if self._orchestrator:
                self._orchestrator.run_pipeline(f)
            else:
                self.process_file(f)
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

    # ─── Legacy Fallback ─────────────────────────────────────────────────
    # The process_file() method below is the original monolithic pipeline.
    # It is only used when the stage-based orchestrator fails to import.
    # New features should be added to the stage files in ingestion/stages/.

    def process_file(self, file_path):
        rel_path = os.path.relpath(file_path, SOURCE_DIR)

        with self._processed_cache_lock:
            if rel_path in self.processed_cache:
                return

        logger.info(f"Evaluating file: {rel_path}")
        file_hash = self.get_file_hash(file_path)

        if not self.claim_file(file_hash, rel_path):
            logger.info(f"[Distributed Skip] {rel_path}")
            return

        logger.info(f"Processing: {rel_path}")
        ext = os.path.splitext(file_path)[1].lower()

        raw_chunks = []
        failed_pages = []
        _ext_dispatch = {
            '.pdf': 'extract_pdf',
            '.docx': 'extract_docx',
            '.doc': None,  # handled separately via doc_converter
            '.jpg': 'extract_image',
            '.jpeg': 'extract_image',
            '.png': 'extract_image',
            '.xls': 'extract_spreadsheet',
            '.xlsx': 'extract_spreadsheet',
        }
        method_name = _ext_dispatch.get(ext)
        if ext == '.doc':
            try:
                from ingestion.doc_converter import extract_doc
                raw_chunks, failed_pages = extract_doc(file_path)
            except Exception as e:
                logger.error(f"DOC extraction failed: {e}")
                failed_pages = [0]
        elif method_name and hasattr(self, method_name):
            raw_chunks, failed_pages = getattr(self, method_name)(file_path)
        else:
            logger.warning(f"Unsupported file format: {ext} for {rel_path}")
            return

        # [doc_boundary] Strip issuing Thông tư/QĐ pages for technical standards
        if raw_chunks:
            from ingestion.doc_boundary import strip_issuing_document, detect_technical_standard
            _std_id = detect_technical_standard(raw_chunks)
            if _std_id:
                _before = len(raw_chunks)
                raw_chunks = strip_issuing_document(raw_chunks, doc_type=None)
                if len(raw_chunks) < _before:
                    logger.info(f"  [doc_boundary] '{_std_id}': stripped {_before - len(raw_chunks)} issuing-doc pages")

        if failed_pages:
            logger.warning(f"  {rel_path} HAS FAILED PAGES: {failed_pages}")
            self.state_manager.update_status(rel_path, 'FAILED', error=f"Failed pages: {failed_pages}")

        if not raw_chunks:
            if not failed_pages:
                self.state_manager.update_status(rel_path, 'FAILED', error="No raw chunks extracted")
            return

        # Parallel LLM calls: metadata, summary, relationships
        full_text_head = "\n".join([c["text"] for c in raw_chunks[:2]])
        full_text_summary = "\n".join([c["text"] for c in raw_chunks[:5]])
        head_tail_rels = "\n".join([c["text"] for c in raw_chunks[:5] + raw_chunks[-3:]])

        meta = self.parse_metadata(os.path.basename(file_path))
        meta["file_name"] = os.path.basename(file_path)

        with ThreadPoolExecutor(max_workers=3) as llm_executor:
            meta_future = llm_executor.submit(self.parse_metadata_from_text, full_text_head)
            summary_future = llm_executor.submit(self.vision.generate_summary, full_text_summary)
            rels_future = llm_executor.submit(self.parse_relationships_llm, head_tail_rels)

            _LLM_TIMEOUT = 360
            refined_meta = meta_future.result(timeout=_LLM_TIMEOUT)
            summary = summary_future.result(timeout=_LLM_TIMEOUT)
            relationships = rels_future.result(timeout=_LLM_TIMEOUT)

        if refined_meta:
            new_num = refined_meta.get("doc_number", "")
            old_num = meta.get("doc_number", "")
            is_new_suspicious = bool(re.match(r'^\d+$', str(new_num))) and len(str(new_num)) <= 2
            is_old_robust = '/' in str(old_num) or len(str(old_num)) > 4
            if is_new_suspicious and is_old_robust:
                logger.warning(f"  Rejected suspicious doc_number: '{new_num}' vs '{old_num}'")
                refined_meta.pop("doc_number", None)

            llm_date = refined_meta.get("date") or refined_meta.get("doc_date", "")
            if llm_date and llm_date != "unknown":
                if not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$|^\d{4}-\d{2}-\d{2}$', str(llm_date)):
                    refined_meta.pop("date", None)
                    refined_meta.pop("doc_date", None)
                elif llm_date in ("2025-01-01", "01/01/2025", "01-01-2025"):
                    refined_meta.pop("date", None)
                    refined_meta.pop("doc_date", None)
            meta.update({k: v for k, v in refined_meta.items() if v and v != "unknown"})

        if not meta.get("doc_number"):
            regex_doc_num = self.extract_doc_number_regex(full_text_head)
            if regex_doc_num:
                meta["doc_number"] = regex_doc_num

        taxonomy = classify_all(
            doc_number=meta.get("doc_number", ""),
            filename=os.path.basename(file_path),
            authority=meta.get("authority", ""),
            text_head=full_text_head,
        )
        meta["type"] = taxonomy["doc_type"]
        meta["legal_level"] = taxonomy["legal_level"]
        meta["discipline"] = taxonomy["discipline"]

        meta["source_category"] = classify_source_category(rel_path)

        # Resolve doc_id
        raw_doc_num = meta.get("doc_number", "").strip()
        namespace = rel_path.split(os.sep)[0] if os.sep in rel_path else "ROOT"
        is_legal_pattern = bool(re.match(r'^\d+/', raw_doc_num))

        if is_legal_pattern:
            doc_id = f"{namespace}/{raw_doc_num}"
        else:
            fn_doc_num = meta.get("doc_number", "").strip()
            if fn_doc_num and re.match(r'^\d+/', fn_doc_num):
                doc_id = f"{namespace}/{fn_doc_num}"
            else:
                clean_fn = os.path.splitext(os.path.basename(file_path))[0].replace(' ', '_')
                doc_id = f"{namespace}/{raw_doc_num}_{clean_fn}" if raw_doc_num else f"{namespace}/{clean_fn}"

        if not doc_id:
            doc_id = f"{namespace}/{os.path.splitext(os.path.basename(file_path))[0].replace(' ', '_')}"
        doc_id = re.sub(r'[^\w\d\-_/.]', '_', doc_id)

        # De-duplication check
        existing_hash = self.state_manager.get_existing_doc_hash(doc_id)
        if existing_hash:
            if existing_hash == file_hash:
                logger.info(f"[Safe Skip] {rel_path} → doc_id {doc_id} matches existing hash.")
                self.state_manager.update_status(rel_path, 'COMPLETED', doc_id=doc_id, metadata=meta)
                with self._processed_cache_lock:
                    self.processed_cache.add(rel_path)
                return
            else:
                doc_id = f"{doc_id}_{file_hash[:6]}"
                logger.warning(f"[Collision] Using: {doc_id}")

        self.sync_to_graph(doc_id, meta, relationships)

        # Semantic chunking with normalization
        semantic_chunks = []
        for chunk in raw_chunks:
            text = strip_document_boilerplate(chunk["text"])
            text = strip_noi_nhan_block(text)
            text = strip_signer_block(text)
            text = rejoin_paragraphs(text)

            is_tabular = (
                chunk.get("is_table", False)
                or bool(re.search(r'\|.*\|.*\n\|[-:\s|]+\|', text))
                or detect_garbled_table(text)
            )
            if is_tabular:
                semantic_chunks.append({
                    "text": text.strip(), "source": os.path.basename(file_path),
                    "page": chunk["page"], "is_table": True, "chunk_type": "parent",
                    "hierarchy_path": f"[{doc_id} > Table > Page {chunk['page']}]",
                })
            else:
                doc_chunks = self.chunker.chunk_document(
                    text, os.path.basename(file_path), chunk["page"], doc_id,
                    layout=chunk.get("layout"),
                )
                semantic_chunks.extend(doc_chunks)

        # Dedup parent chunks
        seen_fps = set()
        deduped = []
        for c in semantic_chunks:
            if c.get("chunk_type") == "parent":
                fp = hash(c.get("text", "").strip())
                if fp in seen_fps:
                    continue
                seen_fps.add(fp)
            deduped.append(c)
        semantic_chunks = deduped

        # Central identity assignment
        raw_doc_number = meta.get("doc_number", "")
        for idx, c in enumerate(semantic_chunks):
            c["doc_id"] = doc_id
            c["doc_number"] = raw_doc_number
            if "chunk_id" not in c:
                c["chunk_id"] = f"{doc_id}::p{c.get('page', 0)}::{c.get('chunk_type', 'parent')}_{idx}"

        # Synthetic query generation
        parent_chunks = [c for c in semantic_chunks if c.get("chunk_type") == "parent" and len(c.get("text", "")) > 300]
        parent_chunks.sort(key=lambda x: len(x.get("text", "")), reverse=True)
        target_chunks = parent_chunks[:30]
        if target_chunks:
            from concurrent.futures import as_completed
            with ThreadPoolExecutor(max_workers=min(len(target_chunks), 8)) as synth_executor:
                futures = {synth_executor.submit(self.generate_synthetic_queries, c["text"]): c for c in target_chunks}
                for future in as_completed(futures):
                    chunk_obj = futures[future]
                    try:
                        chunk_obj["synthetic_queries"] = future.result()
                    except Exception as e:
                        logger.error(f"  Synthetic query generation failed: {e}")
                        chunk_obj["synthetic_queries"] = ""
        for c in semantic_chunks:
            if "synthetic_queries" not in c:
                c["synthetic_queries"] = ""

        if semantic_chunks:
            self.index_chunks(semantic_chunks, summary, meta, file_hash)

        if not failed_pages:
            self.state_manager.update_status(rel_path, 'COMPLETED', doc_id=doc_id, metadata=meta)
            with self._processed_cache_lock:
                self.processed_cache.add(rel_path)
            self.mark_file_done(file_hash)
            if self.exporter:
                try:
                    self.exporter.export(rel_path, doc_id, meta, summary, semantic_chunks)
                except Exception as e:
                    logger.error(f"Failed to export data for {doc_id}: {e}")

            # Telegram notification
            try:
                count, file_list = self.state_manager.check_notification_milestone(milestone_step=50)
                if count and file_list:
                    from core.notifier import notifier
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(notifier.notify_milestone(count, file_list))
                        else:
                            loop.run_until_complete(notifier.notify_milestone(count, file_list))
                    except RuntimeError:
                        asyncio.run(notifier.notify_milestone(count, file_list))
            except Exception as e:
                logger.error(f"Failed milestone notification: {e}")


if __name__ == "__main__":
    try:
        start_http_server(8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as e:
        logger.error(f"Could not start prometheus server: {e}")

    time.sleep(5)
    ingestor = ProductionIngestor()
    ingestor.run()
