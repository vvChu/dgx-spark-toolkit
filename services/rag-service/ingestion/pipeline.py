"""Production ingestion pipeline for Vietnamese legal documents.

Unified deep DocumentIngestionPipeline module consolidating metadata, extraction,
chunking, embedding, indexing, graph, and queue worker execution behind a clean seam.
"""
import logging

if not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()],
    )
logger = logging.getLogger(__name__)

import os
import time
import hashlib
import re
import httpx
import threading
import contextlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor

from pymilvus import connections, Collection, utility, FieldSchema, CollectionSchema, DataType
from neo4j import GraphDatabase, AsyncGraphDatabase
from pymilvus import AsyncMilvusClient
from prometheus_client import start_http_server, Gauge, Counter, Histogram
import fitz

from core.config import get_settings
from ingestion.vision import VisionExtractor
from ingestion.chunking import DocumentChunker
from ingestion.exporter import DataExporter
from ingestion.text_normalizer import (
    rejoin_paragraphs, detect_garbled_table,
    strip_document_boilerplate, strip_noi_nhan_block, strip_signer_block,
)
from ingestion.legal_taxonomy import classify_all, classify_source_category
from ingestion.state_manager import StateManager, InMemoryStateManager
from ingestion.pipeline_config import (
    MAX_WORKERS, SOURCE_DIR, COLLECTION_NAME, MILVUS_HOST, MILVUS_PORT,
    NEO4J_URI, NEO4J_USER, NEO4J_PASS, JSON_MODEL, TEXT_METADATA_MODEL,
    SYNTHETIC_QUERY_MODEL, RELATIONSHIP_MODEL,
)
from ingestion import pipeline_config
from ingestion.cloud_vision import llm_extract_page as _llm_extract_page
from ingestion.pdf_classifier import classify_pdf, classify_page, PdfType
from ingestion.image_preprocessor import preprocess_page_image
from ingestion.json_parser import extract_json_from_response
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.lifecycle_service import LifecycleService
from ingestion.models import ProcessedDocument, DocumentIdentity, DocumentMetadata

# Prometheus Metrics
INGESTION_WORKERS_ACTIVE = Gauge('ingestion_workers_active', 'Number of active ingestion workers')
VISION_FALLBACK_COUNT = Counter('vision_fallback_pipeline_total', 'Total pages routed to Vision Fallback in pipeline')
PAGE_PROCESS_TOTAL = Counter('page_process_total', 'Total pages processed')
INGESTION_LATENCY = Gauge('ingestion_latency_seconds', 'Latency of last file processing')
STAGE_DURATION = Histogram(
    'rag_stage_duration_seconds',
    'Time spent in each pipeline stage',
    ['stage'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300]
)
STAGE_TOTAL = Counter(
    'rag_stage_total',
    'Pipeline stage executions',
    ['stage', 'status']
)
PIPELINE_TOTAL = Counter(
    'rag_pipeline_total',
    'Total pipeline runs',
    ['status']
)

_SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png', '.xls', '.xlsx'}
_LEGAL_SHORT_PATTERNS = re.compile(
    r'^\s*(Chương|Mục|Phần|Phụ\s*lục|Điều|Khoản|Hình|Bảng|Biểu)\s+[\w\d.]+',
    re.IGNORECASE | re.UNICODE,
)


class DocumentIngestionPipeline:
    """Unified deep module for Vietnamese legal document ingestion."""

    def __init__(self, state_manager: StateManager | None = None, settings: Any | None = None):
        pipeline_config._load()
        settings = settings or get_settings()

        self.vision = VisionExtractor()
        self.state_manager = state_manager or StateManager()

        from services.retrieval_service import get_embedding_model
        self.model = get_embedding_model()
        self.chunker = DocumentChunker()
        self.exporter = DataExporter(settings.EXPORT_DIR) if settings.EXPORT_PROCESSED_DATA else None
        self._http_client = httpx.Client(timeout=300)

        # Database connections (handled gracefully if offline)
        self.neo4j_driver = None
        self._async_milvus = None
        self._async_neo4j = None
        self.lifecycle_service = None
        self.collection = None

        if not isinstance(self.state_manager, InMemoryStateManager):
            try:
                self.neo4j_driver = GraphDatabase.driver(
                    pipeline_config.NEO4J_URI, auth=(pipeline_config.NEO4J_USER, pipeline_config.NEO4J_PASS)
                )
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
            except Exception as e:
                logger.warning(f"Database setup incomplete for pipeline: {e}")

        self.processed_cache: set = set()
        self._processed_cache_lock = threading.Lock()
        self.load_processed_cache()

    def close(self):
        try:
            if self.neo4j_driver:
                self.neo4j_driver.close()
            if self._async_neo4j:
                self._async_neo4j.close()
            if self._async_milvus:
                self._async_milvus.close()
            if self._http_client:
                self._http_client.close()
            logger.info("DocumentIngestionPipeline resources closed safely.")
        except Exception as e:
            logger.warning(f"Error during pipeline cleanup: {e}")

    def load_processed_cache(self):
        try:
            all_state = self.state_manager.get_all_state()
            new_cache = {f for f, s in all_state.items() if s["status"] == 'COMPLETED'}
            with self._processed_cache_lock:
                self.processed_cache = new_cache
            logger.info(f"Loaded {len(new_cache)} files into fast-skip cache.")
        except Exception as e:
            logger.error(f"Failed to load processed cache: {e}")

    def init_neo4j(self):
        if not self.neo4j_driver:
            return
        with self.neo4j_driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            session.run("CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doc_number)")

    def connect_milvus(self):
        try:
            connections.connect(host=pipeline_config.MILVUS_HOST, port=pipeline_config.MILVUS_PORT)
            logger.info(f"Connected to Milvus at {pipeline_config.MILVUS_HOST}:{pipeline_config.MILVUS_PORT}")
        except Exception as e:
            logger.warning(f"Milvus connection skipped: {e}")

    def setup_collection(self):
        try:
            if utility.has_collection(pipeline_config.COLLECTION_NAME):
                col = Collection(pipeline_config.COLLECTION_NAME)
                col.load()
                return col

            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=15000),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="page", dtype=DataType.INT64),
                FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=2048),
                FieldSchema(name="doc_date", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="authority", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="file_hash", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="is_table", dtype=DataType.BOOL),
                FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=16),
                FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="doc_number", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=256, default_value=""),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=512, default_value=""),
                FieldSchema(name="bbox", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="validity_status", dtype=DataType.VARCHAR, max_length=32, default_value="ACTIVE"),
                FieldSchema(name="legal_level", dtype=DataType.VARCHAR, max_length=32, default_value="UNKNOWN"),
                FieldSchema(name="hierarchy_path", dtype=DataType.VARCHAR, max_length=1024, default_value=""),
                FieldSchema(name="citation_count", dtype=DataType.INT64, default_value=0),
                FieldSchema(name="project_code", dtype=DataType.VARCHAR, max_length=64, default_value="GENERIC"),
                FieldSchema(name="discipline", dtype=DataType.VARCHAR, max_length=32, default_value="UNKNOWN"),
                FieldSchema(name="doc_status", dtype=DataType.VARCHAR, max_length=32, default_value="ACTIVE"),
                FieldSchema(name="revision", dtype=DataType.INT64, default_value=0),
                FieldSchema(name="synthetic_queries", dtype=DataType.VARCHAR, max_length=4095, default_value=""),
                FieldSchema(name="source_category", dtype=DataType.VARCHAR, max_length=64, default_value="KHAC"),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
            ]
            schema = CollectionSchema(fields, description="Vietnamese legal document chunks")
            col = Collection(pipeline_config.COLLECTION_NAME, schema)
            index_params = {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 200}}
            col.create_index(field_name="vector", index_params=index_params)
            col.load()
            return col
        except Exception as e:
            logger.warning(f"Could not setup Milvus collection: {e}")
            return None

    def get_file_hash(self, file_path: str | Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def claim_file(self, file_hash: str, rel_path: str) -> bool:
        worker_id = os.getenv("HOSTNAME", f"worker-{os.getpid()}")
        return self.state_manager.claim_file(rel_path, worker_id, content_hash=file_hash, stale_minutes=120)

    # ── Main Entry Points ──────────────────────────────────────────────

    def safe_process(self, f: str):
        INGESTION_WORKERS_ACTIVE.inc()
        start_time = time.time()
        try:
            self.run_pipeline(f)
            INGESTION_LATENCY.set(time.time() - start_time)
        except Exception as e:
            logger.error(f"Failed to process {f}: {e}")
            try:
                rel_path = os.path.relpath(f, SOURCE_DIR)
                self.state_manager.update_status(rel_path, 'FAILED', error=str(e))
            except Exception as inner_e:
                logger.error(f"Could not update failure status for {f}: {inner_e}")
        finally:
            INGESTION_WORKERS_ACTIVE.dec()

    async def ingest_file(self, file_path: str | Path, force_reprocess: bool = False) -> ProcessedDocument | None:
        """Main public async entry point."""
        return self.run_pipeline(str(file_path))

    def run_pipeline(self, file_path: str) -> ProcessedDocument | None:
        """Execute all 9 processing stages sequentially."""
        rel_path = os.path.relpath(file_path, SOURCE_DIR)
        doc = ProcessedDocument(
            identity=DocumentIdentity(
                doc_number="",
                namespace="",
                content_hash="",
                file_name=os.path.basename(file_path),
                rel_path=rel_path,
            ),
            file_path=file_path,
        )

        stages: list[tuple[str, Callable]] = [
            ("s01_intake", self._stage_intake),
            ("s02_ocr", self._stage_ocr),
            ("s03_metadata", self._stage_metadata),
            ("s04_identity", self._stage_identity),
            ("s05_chunking", self._stage_chunking),
            ("s06_enrichment", self._stage_enrichment),
            ("s07_embedding", self._stage_embedding),
            ("s08_indexing", self._stage_indexing),
            ("s09_export", self._stage_export),
        ]

        for stage_name, stage_fn in stages:
            t0 = time.time()
            try:
                result = stage_fn(doc)
                elapsed = time.time() - t0
                STAGE_DURATION.labels(stage=stage_name).observe(elapsed)

                if result is None:
                    STAGE_TOTAL.labels(stage=stage_name, status="skip").inc()
                    PIPELINE_TOTAL.labels(status="skipped").inc()
                    logger.info(f"  [{stage_name}] Skipped ({elapsed:.2f}s)")
                    return None

                STAGE_TOTAL.labels(stage=stage_name, status="success").inc()
                doc = result
                doc.stage = stage_name
            except Exception as e:
                elapsed = time.time() - t0
                STAGE_DURATION.labels(stage=stage_name).observe(elapsed)
                STAGE_TOTAL.labels(stage=stage_name, status="error").inc()
                PIPELINE_TOTAL.labels(status="failed").inc()
                logger.error(f"  [{stage_name}] FAILED in {elapsed:.2f}s: {e}")
                raise Exception(f"Stage '{stage_name}' failed: {e}") from e

        PIPELINE_TOTAL.labels(status="completed").inc()
        return doc

    # ── Internal Stage Steps ──────────────────────────────────────────

    def _stage_intake(self, doc: ProcessedDocument) -> ProcessedDocument | None:
        file_hash = self.get_file_hash(doc.file_path)
        doc.identity.content_hash = file_hash

        with self._processed_cache_lock:
            if doc.identity.rel_path in self.processed_cache:
                return None

        if not self.claim_file(file_hash, doc.identity.rel_path):
            return None

        return doc

    def _stage_ocr(self, doc: ProcessedDocument) -> ProcessedDocument:
        ext = os.path.splitext(doc.file_path)[1].lower()
        if ext == '.pdf':
            doc.pages = self._extract_pdf_pages(doc.file_path)
        elif ext in ('.docx', '.doc'):
            text = self._extract_docx_text(doc.file_path)
            doc.pages = [{"page": 1, "text": text, "route": "docx", "is_table": False, "bbox": ""}]
        elif ext in ('.jpg', '.jpeg', '.png'):
            text = _llm_extract_page(doc.file_path, page_num=1)
            doc.pages = [{"page": 1, "text": text, "route": "image_ocr", "is_table": False, "bbox": ""}]
        else:
            doc.pages = []
        return doc

    def _stage_metadata(self, doc: ProcessedDocument) -> ProcessedDocument:
        raw_meta = self._parse_metadata(doc.identity.file_name)
        full_text = "\n".join(p["text"] for p in doc.pages[:3]) if doc.pages else ""

        if raw_meta.get("doc_number"):
            doc.identity.doc_number = raw_meta["doc_number"]
            doc.metadata = DocumentMetadata(
                doc_type=raw_meta.get("type", "UNKNOWN"),
                authority=raw_meta.get("authority", "UNKNOWN"),
                date=raw_meta.get("date", "UNKNOWN"),
                doc_number=raw_meta["doc_number"],
                source_category=classify_source_category(doc.identity.rel_path),
            )
        else:
            refined = self._parse_metadata_from_text(full_text[:4000])
            doc.identity.doc_number = refined.get("doc_number", raw_meta.get("doc_number", "UNKNOWN"))
            doc.metadata = DocumentMetadata(
                doc_type=refined.get("type", "UNKNOWN"),
                authority=refined.get("authority", "UNKNOWN"),
                date=refined.get("date", "UNKNOWN"),
                doc_number=doc.identity.doc_number,
                source_category=classify_source_category(doc.identity.rel_path),
            )
        return doc

    def _stage_identity(self, doc: ProcessedDocument) -> ProcessedDocument:
        doc.identity.namespace = "VBPL"
        return doc

    def _stage_chunking(self, doc: ProcessedDocument) -> ProcessedDocument:
        full_text = "\n".join(p["text"] for p in doc.pages) if doc.pages else ""
        doc.raw_chunks = self.chunker.chunk_document(full_text, doc.identity.file_name, 1, doc.identity.doc_number)
        return doc

    def _stage_enrichment(self, doc: ProcessedDocument) -> ProcessedDocument:
        doc.relationships = self._parse_relationships_llm("\n".join(p["text"] for p in doc.pages[:5]))
        return doc

    def _stage_embedding(self, doc: ProcessedDocument) -> ProcessedDocument:
        if not doc.raw_chunks:
            return doc
        texts = [c["text"] for c in doc.raw_chunks]
        try:
            embeddings = self.model.embed_documents(texts)
            for chunk, emb in zip(doc.raw_chunks, embeddings):
                chunk["vector"] = emb.get("dense", []) if isinstance(emb, dict) else emb
                chunk["sparse_vector"] = emb.get("sparse", {}) if isinstance(emb, dict) else {}
        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
        return doc

    def _stage_indexing(self, doc: ProcessedDocument) -> ProcessedDocument:
        if self.collection and doc.raw_chunks:
            try:
                entities = []
                for chunk in doc.raw_chunks:
                    entities.append({
                        "text": chunk.get("text", "")[:14000],
                        "source": doc.identity.rel_path,
                        "page": chunk.get("page", 1),
                        "summary": chunk.get("summary", "")[:2000],
                        "doc_date": doc.metadata.date,
                        "doc_type": doc.metadata.doc_type,
                        "authority": doc.metadata.authority,
                        "file_hash": doc.identity.content_hash,
                        "is_table": chunk.get("is_table", False),
                        "chunk_type": chunk.get("chunk_type", "TEXT"),
                        "parent_id": doc.identity.doc_id,
                        "doc_number": doc.identity.doc_number,
                        "doc_id": doc.identity.doc_id,
                        "chunk_id": f"{doc.identity.doc_id}::p{chunk.get('page', 1)}",
                        "bbox": "",
                        "validity_status": "ACTIVE",
                        "legal_level": "UNKNOWN",
                        "hierarchy_path": "",
                        "citation_count": 0,
                        "project_code": "GENERIC",
                        "discipline": "UNKNOWN",
                        "doc_status": "ACTIVE",
                        "revision": 0,
                        "synthetic_queries": "",
                        "source_category": doc.metadata.source_category,
                        "vector": chunk.get("vector", [0.0] * 1024),
                    })
                if entities:
                    self.collection.insert(entities)
                    self.collection.flush()
            except Exception as e:
                logger.warning(f"Milvus indexing skipped: {e}")

        self.state_manager.update_status(
            doc.identity.rel_path,
            'COMPLETED',
            doc_id=doc.identity.doc_id,
            metadata={"pages": len(doc.pages), "chunks": len(doc.raw_chunks)}
        )
        with self._processed_cache_lock:
            self.processed_cache.add(doc.identity.rel_path)
        return doc

    def _stage_export(self, doc: ProcessedDocument) -> ProcessedDocument:
        if self.exporter:
            try:
                self.exporter.export_document(doc)
            except Exception as e:
                logger.warning(f"Export failed: {e}")
        return doc

    # ── Helper Extractors & Parsers ───────────────────────────────────

    def _extract_pdf_pages(self, file_path: str) -> list[dict]:
        pages = []
        try:
            doc = fitz.open(file_path)
            for idx, page in enumerate(doc):
                text = page.get_text("text") or ""
                pages.append({
                    "page": idx + 1,
                    "text": text,
                    "route": "digital" if text.strip() else "ocr",
                    "is_table": False,
                    "bbox": "",
                })
            doc.close()
        except Exception as e:
            logger.error(f"Error extracting PDF pages from {file_path}: {e}")
        return pages

    def _extract_docx_text(self, file_path: str) -> str:
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            logger.error(f"Error reading docx {file_path}: {e}")
            return ""

    def _parse_metadata(self, filename: str) -> dict:
        meta = {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}
        date_match = re.match(r'(\d{8})[_\-]', filename)
        if date_match:
            d = date_match.group(1)
            meta["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"

        doc_match = re.search(r'([A-Z]{2,4})(\d+)[-/]([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)', filename)
        if doc_match:
            meta["type"] = doc_match.group(1)
            number = doc_match.group(2)
            authority_part = doc_match.group(3)

            auth_parts = authority_part.split('-')
            non_year = [p for p in auth_parts if not re.match(r'^\d{4}$', p)]
            if non_year:
                meta["authority"] = non_year[-1]

            year_parts = [p for p in auth_parts if re.match(r'^\d{4}$', p)]
            year = year_parts[0] if year_parts else (meta["date"][:4] if meta["date"] != "unknown" else "")

            type_vn = meta["type"]
            auth = meta["authority"]
            if year and year != "unknown":
                meta["doc_number"] = f"{number}/{year}/{type_vn}-{auth}"
            else:
                meta["doc_number"] = f"{number}/{type_vn}-{auth}"
        return meta

    def _parse_metadata_from_text(self, text: str) -> dict:
        try:
            payload = {
                "model": TEXT_METADATA_MODEL,
                "messages": [
                    {"role": "system", "content": "Extract legal document metadata as JSON: title, type, authority, date, doc_number."},
                    {"role": "user", "content": f"Extract metadata JSON from:\n\n{text[:3000]}"}
                ],
                "max_tokens": 1024,
                "temperature": 0.0,
            }
            resp = self._http_client.post(self.vision.api_url, json=payload, headers={"Authorization": f"Bearer {self.vision.api_key}"})
            resp.raise_for_status()
            return extract_json_from_response(resp.json()) or {}
        except Exception as e:
            logger.warning(f"Metadata extraction fallback: {e}")
            return {}

    def _parse_relationships_llm(self, text: str) -> dict:
        try:
            payload = {
                "model": RELATIONSHIP_MODEL,
                "messages": [
                    {"role": "system", "content": "Extract relationships between documents as JSON: replaces, amends, references."},
                    {"role": "user", "content": f"Extract relationship JSON:\n\n{text[:4000]}"}
                ],
                "max_tokens": 2048,
                "temperature": 0.0,
            }
            resp = self._http_client.post(self.vision.api_url, json=payload, headers={"Authorization": f"Bearer {self.vision.api_key}"})
            resp.raise_for_status()
            return extract_json_from_response(resp.json()) or {"replaces": [], "amends": [], "references": []}
        except Exception as e:
            logger.warning(f"Relationship extraction fallback: {e}")
            return {"replaces": [], "amends": [], "references": []}

    # ── Runner Loop ───────────────────────────────────────────────────

    def run(self):
        """Worker loop entry point."""
        logger.info("Starting DocumentIngestionPipeline worker loop...")
        try:
            from ingestion.queue import RedisQueue
            queue = RedisQueue()
            logger.info("Connected to Redis Queue ✓")
            while True:
                messages = queue.claim_next(count=1, block_ms=5000)
                if messages:
                    for msg_id, file_path in messages:
                        try:
                            self.safe_process(file_path)
                            queue.ack(msg_id)
                        except Exception as e:
                            queue.nack(msg_id, str(e))
                else:
                    time.sleep(1)
        except Exception as e:
            logger.warning(f"Redis queue worker loop unavailable: {e}")


# Backward compatibility alias
ProductionIngestor = DocumentIngestionPipeline


if __name__ == "__main__":
    try:
        start_http_server(8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as e:
        logger.error(f"Could not start prometheus server: {e}")

    time.sleep(1)
    pipeline = DocumentIngestionPipeline()
    pipeline.run()
