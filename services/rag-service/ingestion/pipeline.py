import logging
import os as _os

# Only configure root logger if it has no handlers yet (avoids clobbering FastAPI/uvicorn logging).
# Use an absolute path for the log file so it lands in /app regardless of cwd.
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
import json
import hashlib
import re
import fitz  # PyMuPDF
import httpx
from pymilvus import connections, Collection, utility, FieldSchema, CollectionSchema, DataType

from sentence_transformers import SentenceTransformer
from neo4j import GraphDatabase
from ingestion.vision import VisionExtractor, hybrid_extract_page
from ingestion.cloud_vision import llm_extract_page as _llm_extract_page
from core.config import get_settings
from ingestion.chunking import DocumentChunker
from ingestion.cleaning_utils import clean_llm_text
from ingestion.exporter import DataExporter
from ingestion.text_normalizer import rejoin_paragraphs, detect_garbled_table, strip_document_boilerplate, strip_noi_nhan_block, strip_signer_block
from ingestion.legal_taxonomy import classify_all
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import torch
from concurrent.futures import ThreadPoolExecutor
from prometheus_client import start_http_server, Gauge, Counter
import asyncio
from pymilvus import AsyncMilvusClient
from neo4j import AsyncGraphDatabase
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from services.lifecycle_service import LifecycleService

# Prometheus Metrics
INGESTION_WORKERS_ACTIVE = Gauge('ingestion_workers_active', 'Number of active ingestion workers')
VISION_FALLBACK_COUNT = Counter('vision_fallback_pipeline_total', 'Total pages routed to Vision Fallback in pipeline')
PAGE_PROCESS_TOTAL = Counter('page_process_total', 'Total pages processed')
INGESTION_LATENCY = Gauge('ingestion_latency_seconds', 'Latency of last file processing')

# Config (Sync with rag-service settings)
settings = get_settings()
MILVUS_HOST = os.getenv("MILVUS_HOST", settings.MILVUS_HOST)
MILVUS_PORT = os.getenv("MILVUS_PORT", settings.MILVUS_PORT)
MAX_OCR_CONCURRENCY = settings.MAX_OCR_CONCURRENCY
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
MAX_DIGITAL_WORKERS = int(os.getenv("MAX_DIGITAL_WORKERS", "10"))
COLLECTION_NAME = settings.MILVUS_COLLECTION
from ingestion.state_manager import PostgresStateManager
SOURCE_DIR = "/app/data/legal_docs_source"
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j-graph:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS", "")
JSON_MODEL = os.getenv("JSON_MODEL", "qwen3.5-35b")  # Local Qwen for structured JSON tasks
# LLM Vision is always used for scanned pages (Qwen primary → Gemini fallback)

def _extract_json_from_response(data):
    """Robustly extract JSON from Qwen 3.5 API response.
    
    Qwen 3.5 with reasoning-parser often outputs a long chain-of-thought
    before the actual JSON. This function handles all common patterns:
    - JSON inside ```json ... ``` markdown blocks
    - JSON inside ``` ... ``` blocks
    - Raw JSON objects {} anywhere in the response
    - JSON with JS-style comments
    """
    if not isinstance(data, dict) or "choices" not in data or not data["choices"]:
        raise ValueError(f"Invalid API response structure: {data}")
        
    choice = data["choices"][0]
    if not isinstance(choice, dict):
        raise ValueError(f"Invalid choice structure: {choice}")
        
    msg = choice.get("message", {})
    content = msg.get("content") or ""
    if not content.strip():
        content = msg.get("reasoning_content") or ""
    
    content = content.strip()
    if not content:
        raise ValueError("Empty response from LLM")

    # PRE-PROCESSING: Use robust global cleaning to remove thoughts and conversational noise
    content = clean_llm_text(content)

    # Strategy 1: Find JSON inside markdown code blocks (most reliable)
    json_blocks = re.findall(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content)
    if json_blocks:
        # Filter out blocks that looks like examples/templates (e.g. contain "...")
        actual_blocks = [b for b in json_blocks if "..." not in b]
        json_str = actual_blocks[-1] if actual_blocks else json_blocks[-1]
        json_str = re.sub(r'//.*?$|/\*.*?\*/', '', json_str, flags=re.MULTILINE)
        try:
            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            pass

    # Strategy 2: Find the LAST standalone JSON object {} in the text
    # This catches cases where Qwen outputs thinking then raw JSON at the end
    all_objects = re.findall(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', content)
    if all_objects:
        # Filter out "template" objects with "..."
        data_objects = [obj for obj in all_objects if "..." not in obj]
        search_list = reversed(data_objects) if data_objects else reversed(all_objects)
        
        for obj_str in search_list:
            obj_str = re.sub(r'//.*?$|/\*.*?\*/', '', obj_str, flags=re.MULTILINE)
            try:
                return json.loads(obj_str.strip())
            except json.JSONDecodeError:
                continue

    # Strategy 3: Greedy — find the largest possible JSON substring
    first_brace = content.find('{')
    if first_brace != -1:
        last_brace = content.rfind('}')
        if last_brace > first_brace:
            candidate = content[first_brace:last_brace + 1]
            candidate = re.sub(r'//.*?$|/\*.*?\*/', '', candidate, flags=re.MULTILINE)
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                pass

    raise ValueError(f"No valid JSON found in response (check for truncation): {content[:300]}...")


class ProductionIngestor:
    def __init__(self):
        self.vision = VisionExtractor()
        device = "cpu" # Force CPU for embeddings to avoid OOM with large Vision models
        logger.info(f"Initializing Pseudo Embedding Model using qwen3.5-9b-rag")

        from services.retrieval_service import get_embedding_model
        self.model = get_embedding_model()
        self.chunker = DocumentChunker()
        self.state_manager = PostgresStateManager()
        self.exporter = DataExporter(settings.EXPORT_DIR) if settings.EXPORT_PROCESSED_DATA else None
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        # H3: shared HTTP client — reused across all LLM calls instead of per-call creation
        self._http_client = httpx.Client(timeout=300)
        
        # --- Lifecycle Management (Async Bridge) ---
        self._async_milvus = AsyncMilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
        self._async_neo4j = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self.lifecycle_service = LifecycleService(
            self.state_manager,
            MilvusRepository(self._async_milvus),
            Neo4jRepository(self._async_neo4j)
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
            
            # --- Async Resource Cleanup ---
            if hasattr(self, '_async_neo4j') and self._async_neo4j:
                self._async_neo4j.close()
            if hasattr(self, '_async_milvus') and self._async_milvus:
                self._async_milvus.close()

            if hasattr(self, '_http_client') and self._http_client:
                self._http_client.close()
            logger.info("ProductionIngestor resources closed safely (Sync & Async).")
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
            # Index on doc_number speeds up the timeline traversal query in graph_timeline_retriever
            session.run("CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doc_number)")
        logger.info("Neo4j initialized")

    def connect_milvus(self):
        connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
        logger.info(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")

    def claim_file(self, file_hash, rel_path):
        """Try to claim a file for processing using PostgreSQL to coordinate between workers."""
        worker_id = os.getenv("HOSTNAME", "worker-" + str(os.getpid()))
        return self.state_manager.claim_file(rel_path, worker_id, content_hash=file_hash)

    def mark_file_done(self, file_hash):
        try:
            with self.neo4j_driver.session() as session:
                session.run("MATCH (f:File {hash: $hash}) SET f.status = 'PROCESSED', f.processed_at = timestamp()", hash=file_hash)
        except Exception as e:
            logger.error(f"Error marking file as done in Neo4j: {e}")

    def setup_collection(self):
        if utility.has_collection(COLLECTION_NAME):
            # Check if schema matches v10 (with doc_id + chunk_id identity fields)
            col = Collection(COLLECTION_NAME)
            required_fields = ["sparse_vector", "bbox", "validity_status", "project_code", "synthetic_queries", "hierarchy_path", "doc_id", "chunk_id", "source_category"]
            has_required = all(any(f.name == rf for f in col.schema.fields) for rf in required_fields)
            
            if not has_required:
                logger.info("Outdated schema (v9 or earlier) detected — missing doc_id/chunk_id. Dropping and recreating with v10...")
                utility.drop_collection(COLLECTION_NAME)
            else:
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
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR)
        ]
        schema = CollectionSchema(fields, "Production Legal Documents v10 - Unified Identity Architecture")
        col = Collection(COLLECTION_NAME, schema)
        
        # Index for Dense Vector
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 500}
        }
        col.create_index(field_name="vector", index_params=index_params)
        
        # Index for Sparse Vector (using BM25 compatible index)
        sparse_index_params = {
            "metric_type": "IP",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"drop_ratio_build": 0.2}
        }
        col.create_index(field_name="sparse_vector", index_params=sparse_index_params)
        
        # Scalar Indexes for filtering
        col.create_index(field_name="doc_number", index_params={"index_type": "INVERTED", "params": {}})
        col.create_index(field_name="doc_id", index_params={"index_type": "INVERTED", "params": {}})
        col.create_index(field_name="validity_status", index_params={"index_type": "INVERTED", "params": {}})
        col.create_index(field_name="project_code", index_params={"index_type": "INVERTED", "params": {}})

        
        col.load()
        logger.info(f"Created collection {COLLECTION_NAME} with Hybrid Search (Dense+Sparse) and V9 Schema")
        return col

    def parse_metadata(self, filename):
        """Extract metadata from Vietnamese legal doc filenames.
        Common patterns:
          20250610_QD1111-TTg_Title.pdf
          20250404_QD08-TTg_Che do boi duong giam dinh tu phap_ththeQD01-2014.pdf
          TT01-2023-BTP_Quy dinh che do BC thi hanh PL ve XLVPHC_16-01-2023.pdf
        """
        meta = {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}
        
        # [Change 6] Anchor date extraction to start of filename to avoid
        # matching 8-digit sequences in dates like "_16-01-2023.pdf"
        date_match = re.match(r'(\d{8})[_\-]', filename)
        if date_match:
            d = date_match.group(1)
            meta["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            
        # Extract doc type + number + authority
        # Pattern: QD08-TTg, TT01-2023-BTP, ND15-2021-CP, CV656-TTg-KSTT
        doc_match = re.search(r'([A-Z]{2,4})(\d+)[-/]([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)', filename)
        if doc_match:
            meta["type"] = doc_match.group(1)  # QD, TT, ND, CV
            number = doc_match.group(2)          # 08, 01, 15
            authority_part = doc_match.group(3)   # TTg, 2023-BTP, 2021-CP
            
            # Parse authority: take the last segment after any year
            auth_parts = authority_part.split('-')
            # Filter out pure year segments
            non_year = [p for p in auth_parts if not re.match(r'^\d{4}$', p)]
            if non_year:
                meta["authority"] = non_year[-1]  # TTg, BTP, CP
            
            # Build the proper doc_number: "08/2025/QĐ-TTg" or "08/QĐ-TTg"
            year_parts = [p for p in auth_parts if re.match(r'^\d{4}$', p)]
            year = year_parts[0] if year_parts else (meta["date"][:4] if meta["date"] != "unknown" else "")
            
            type_vn = meta["type"]
            auth = meta["authority"]
            if year and year != "unknown":
                meta["doc_number"] = f"{number}/{year}/{type_vn}-{auth}"
            else:
                meta["doc_number"] = f"{number}/{type_vn}-{auth}"

        return meta
    def parse_metadata_from_text(self, text):
        """Use LLM to refine metadata from document text."""
        try:
            payload = {
                "model": JSON_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a precise JSON extractor. You MUST output ONLY raw JSON. Do NOT include any 'Thinking Process', 'Analysis', 'Observation', or preamble. NO text before or after the JSON block. Start EXACTLY with '{' and end EXACTLY with '}'."},
                    {"role": "user", "content": f"Extract V9 metadata as JSON for this Vietnamese document: {text[:4000]}\n\nRequired format:\n{{\"doc_number\": \"Full official document number (e.g. 123/QD-UBND or 123/2024/TT-BTP). Do NOT extract single digits or page numbers.\", \"doc_date\": \"YYYY-MM-DD\", \"doc_type\": \"...\", \"authority\": \"...\", \"validity_status\": \"ACTIVE\", \"project_code\": \"GENERIC\", \"discipline\": \"UNKNOWN\", \"doc_status\": \"ACTIVE\", \"revision\": 0}}"}
                ],
                "max_tokens": 4096,
                "temperature": 0.0,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            }
            headers = {"Authorization": f"Bearer {self.vision.api_key}"}
            max_retries = 3
            retry_delay = 5
            for attempt in range(max_retries):
                try:
                    resp = self._http_client.post(self.vision.api_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"Rate limited (429) in parse_metadata. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    refined = _extract_json_from_response(data)
                    if not refined:
                        raise ValueError("No refined metadata extracted")

                    # Normalize keys (case-insensitive, handle common LLM key variations)
                    normalized = {}
                    for k, v in refined.items():
                        k_lower = k.lower()
                        if "number" in k_lower or "hiệu" in k_lower:
                            normalized["doc_number"] = v
                        elif "date" in k_lower or "hành" in k_lower:
                            normalized["doc_date"] = v
                        elif "type" in k_lower or "loại" in k_lower:
                            normalized["doc_type"] = v
                        elif "authority" in k_lower or "quyền" in k_lower:
                            normalized["authority"] = v
                        else:
                            # Pass through fields that match exactly (validity_status, etc.)
                            normalized[k_lower] = v

                    def regularize(val, default):
                        if not val or str(val).lower() in ["unknown", "n/a", "none", "chưa rõ"]:
                            return default
                        return val

                    return {
                        "date": regularize(normalized.get("doc_date"), "2025-01-01"),
                        "type": regularize(normalized.get("doc_type"), "VAN_BAN")[:32],
                        "authority": regularize(normalized.get("authority"), "CO_QUAN_BAN_HANH")[:64],
                        "doc_number": normalized.get("doc_number", ""),
                        "validity_status": normalized.get("validity_status", "ACTIVE")[:32],
                        "project_code": normalized.get("project_code", "GENERIC")[:64],
                        "discipline": normalized.get("discipline", "UNKNOWN")[:32],
                        "doc_status": normalized.get("doc_status", "ACTIVE")[:32],
                        "revision": int(float(normalized.get("revision", 0) or 0))
                    }
                except Exception as e:
                    if attempt == max_retries - 1:
                        logging.error(f"Metadata extraction failed after {max_retries} attempts: {e}")
                        return {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}
                    time.sleep(retry_delay * (2 ** attempt))
        except Exception as e:
            logger.warning(f"Vision metadata extraction failed: {e}")
            return {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}

    def generate_synthetic_queries(self, chunk_text: str) -> str:
        """Phase 2: Generate synthetic queries for better vector grounding."""
        try:
            payload = {
                "model": JSON_MODEL,
                "messages": [
                    {"role": "system", "content": "You are an assistant that generates hypothetical user questions. Output ONLY 3-5 questions separated by newlines that the given text can answer."},
                    {"role": "user", "content": f"Generate 3-5 questions for this text:\n\n{chunk_text}\n\nQuestions:"}
                ],
                "max_tokens": 512,
                "temperature": 0.5,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            }
            headers = {"Authorization": f"Bearer {self.vision.api_key}"}
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    resp = self._http_client.post(self.vision.api_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        time.sleep(5 * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = msg.get("content") or ""
                    return content.strip()[:4000]
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Synthetic queries failed after {max_retries} attempts: {e}")
                        return ""
                    time.sleep(5 * (2 ** attempt))
        except Exception:
            return ""

    def extract_doc_number_regex(self, text):
        """Low-level regex fallback to find formal Vietnamese legal patterns in text."""
        # Matches standards like 123/QD-UBND or 45/2024/TT-BTP
        pattern = r"(?i)Số[:\s]*(\d+(?:/\d+)?/[A-ZĐ]+-[A-Z\d-]+)"
        match = re.search(pattern, text[:3000])
        if match:
            return match.group(1).strip()
        # Fallback for simpler number patterns if no full pattern is found
        fallback_pattern = r"(?i)Số[:\s]*(\d+[\w\d/-]*)"
        match = re.search(fallback_pattern, text[:2000])
        if match:
            return match.group(1).strip()
        return None

    # (logical_legal_chunk has been extracted to ingestion.chunking.DocumentChunker via Strategy Pattern)


    def get_file_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def is_scanned_pdf(self, file_path):
        """Quick check if a PDF is mostly scanned or digital."""
        try:
            doc = fitz.open(file_path)
            if len(doc) == 0:
                return False
            # Check first 3 pages
            text = ""
            for i in range(min(3, len(doc))):
                text += doc[i].get_text()
            doc.close()
            # If less than 100 chars in 3 pages, it's likely scanned
            return len(text.strip()) < 100
        except Exception as e:
            logger.error(f"  Error checking PDF type for {file_path}: {e}")
            return True # Assume scanned to be safe

    def safe_process(self, f):
        INGESTION_WORKERS_ACTIVE.inc()
        start_time = time.time()
        
        try:
            # Use stage-based orchestrator if available (new architecture)
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
            # Ensure we update the DB so it doesn't stay CLAIMED forever
            try:
                rel_path = os.path.relpath(f, SOURCE_DIR)
                self.state_manager.update_status(rel_path, 'FAILED', error=str(e))
            except Exception as inner_e:
                logger.error(f"  Critical: Could not update failure status for {f}: {inner_e}")
        finally:
            INGESTION_WORKERS_ACTIVE.dec()

    def process_file(self, file_path):
        rel_path = os.path.relpath(file_path, SOURCE_DIR)
        
        # FAST SKIP: Check in-memory cache before hashing
        with self._processed_cache_lock:
            if rel_path in self.processed_cache:
                return

        logger.info(f"Evaluating file: {rel_path}")
        file_hash = self.get_file_hash(file_path)
        
        # Incremental Ingest Check (Temporarily disabled for v7 re-indexing)
        # with self.state_lock:
        #     is_done = file_hash in self.state["processed_files"]
        
        # if is_done:
        #     logger.info(f"[Incremental Skip] {rel_path} (Hash matches state. Skipping extraction & indexing.)")
        #     return

        # Distributed Coordination: Try to claim the file
        if not self.claim_file(file_hash, rel_path):
            logger.info(f"[Distributed Skip] {rel_path} (File is already being processed by another worker or already done.)")
            return

        logger.info(f"Processing: {rel_path}")
        ext = os.path.splitext(file_path)[1].lower()
        
        raw_chunks = []
        failed_pages = []
        if ext == '.pdf':
            raw_chunks, failed_pages = self.extract_pdf(file_path)
        
        if failed_pages:
            logger.warning(f"  {rel_path} HAS FAILED PAGES: {failed_pages}. Will NOT mark as completely processed.")
            self.state_manager.update_status(rel_path, 'FAILED', error=f"Failed pages: {failed_pages}")
        
        if not raw_chunks:
            if not failed_pages:
                # Empty PDF with no extraction errors — mark FAILED so operators can investigate
                self.state_manager.update_status(rel_path, 'FAILED', error="No raw chunks extracted — file may be empty or corrupt")
            return

        # Mức độ 0: Refine Metadata, Summary, and Relationships in Parallel
        full_text_head = "\n".join([c["text"] for c in raw_chunks[:2]])
        full_text_summary = "\n".join([c["text"] for c in raw_chunks[:5]])
        head_tail_rels = "\n".join([c["text"] for c in raw_chunks[:5] + raw_chunks[-3:]])
        
        meta = self.parse_metadata(os.path.basename(file_path))
        meta["file_name"] = os.path.basename(file_path)

        with ThreadPoolExecutor(max_workers=3) as llm_executor:
            meta_future = llm_executor.submit(self.parse_metadata_from_text, full_text_head)
            summary_future = llm_executor.submit(self.vision.generate_summary, full_text_summary)
            rels_future = llm_executor.submit(self.parse_relationships_llm, head_tail_rels)

            # Timeout slightly above the HTTP client timeout (300s) to surface hangs early
            _LLM_TIMEOUT = 360
            refined_meta = meta_future.result(timeout=_LLM_TIMEOUT)
            summary = summary_future.result(timeout=_LLM_TIMEOUT)
            relationships = rels_future.result(timeout=_LLM_TIMEOUT)

        if refined_meta:
            # HARDENING: Prevent "Metadata Degradation"
            # Filename metadata is usually higher confidence for formal identifiers (e.g. 123/QD-TTg)
            # than shaky OCR on scanned pages which might just see a page number "2".
            new_num = refined_meta.get("doc_number", "")
            old_num = meta.get("doc_number", "")
            
            # If new is anemic (single digit) and old is robust (legal pattern), reject the refinement
            is_new_suspicious = bool(re.match(r'^\d+$', str(new_num))) and len(str(new_num)) <= 2
            is_old_robust = '/' in str(old_num) or len(str(old_num)) > 4
            
            if is_new_suspicious and is_old_robust:
                logger.warning(f"  Rejected suspicious doc_number refinement: '{new_num}' (LLM) vs '{old_num}' (Filename). Preserving formal identifier.")
                if "doc_number" in refined_meta:
                    del refined_meta["doc_number"]

            # [C4] Validate date format — reject LLM-hallucinated or default dates
            llm_date = refined_meta.get("date") or refined_meta.get("doc_date", "")
            if llm_date and llm_date != "unknown":
                # Only accept dates matching DD/MM/YYYY or DD-MM-YYYY or YYYY-MM-DD patterns
                if not re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$|^\d{4}-\d{2}-\d{2}$', str(llm_date)):
                    logger.warning(f"  Rejected suspicious date from LLM: '{llm_date}'. Removing.")
                    refined_meta.pop("date", None)
                    refined_meta.pop("doc_date", None)
                elif llm_date in ("2025-01-01", "01/01/2025", "01-01-2025"):
                    # Default placeholder date — not real, reject it
                    logger.warning(f"  Rejected default placeholder date: '{llm_date}'. Removing.")
                    refined_meta.pop("date", None)
                    refined_meta.pop("doc_date", None)

            meta.update({k: v for k, v in refined_meta.items() if v and v != "unknown"})

        # Double check doc_number with regex fallback from head
        if not meta.get("doc_number"):
            regex_doc_num = self.extract_doc_number_regex(full_text_head)
            if regex_doc_num:
                meta["doc_number"] = regex_doc_num

        # ── Legal Taxonomy Classification ──
        taxonomy = classify_all(
            doc_number=meta.get("doc_number", ""),
            filename=os.path.basename(file_path),
            authority=meta.get("authority", ""),
            text_head=full_text_head,
        )
        meta["type"] = taxonomy["doc_type"]
        meta["legal_level"] = taxonomy["legal_level"]
        meta["discipline"] = taxonomy["discipline"]

        # [P1-5] Source category from folder structure
        _CATEGORY_MAP = {
            "CP_": "CHINH_PHU", "QH_": "QUOC_HOI", "UBND": "DIA_PHUONG",
            "Linh vuc": "BO_NGANH", "BCD_": "BAN_CHI_DAO", "BCHTW": "DANG",
            "Quy chuan": "QUY_CHUAN", "QCVN": "QUY_CHUAN",
            "Tieu chuan": "TIEU_CHUAN_QT", "TL ": "TAI_LIEU_KT",
            "TL_": "TAI_LIEU_KT", "TT ": "TRUNG_TAM",
        }
        source_cat = "KHAC"
        for prefix, cat in _CATEGORY_MAP.items():
            if prefix in rel_path:
                source_cat = cat
                break
        meta["source_category"] = source_cat

        logger.info(f"  Taxonomy: type={taxonomy['doc_type']}, level={taxonomy['legal_level']}, discipline={taxonomy['discipline']}, category={source_cat}")
        # Standardized ID Strategy
        raw_doc_num = meta.get("doc_number", "").strip()
        
        # Namespace scoping: use the top-level directory name to prevent collisions across regions/departments
        namespace = rel_path.split(os.sep)[0] if os.sep in rel_path else "ROOT"
        
        # Check if it's a formal Vietnamese legal pattern: "Num/Year/Type-Auth" or "Num/Type-Auth"
        # Must start with a number!
        is_legal_pattern = bool(re.match(r'^\d+/', raw_doc_num)) 
        
        if is_legal_pattern:
             # It's a solid legal ID from LLM/text -> Scope it
             doc_id = f"{namespace}/{raw_doc_num}"
        else:
             # LLM output was weak (e.g. "/2025/QD-UBND"). Try filename extraction fallback.
             # Reuse the already-computed filename metadata (parse_metadata is pure regex, result is identical)
             fn_doc_num = meta.get("doc_number", "").strip()
             
             if fn_doc_num and re.match(r'^\d+/', fn_doc_num):
                 doc_id = f"{namespace}/{fn_doc_num}"
             else:
                 # Both text and filename extraction are weak.
                 # Append filename to ensure uniqueness while keeping what we have.
                 clean_fn = os.path.basename(file_path).replace(' ', '_').replace('.pdf', '')
                 if raw_doc_num:
                     doc_id = f"{namespace}/{raw_doc_num}_{clean_fn}"
                 else:
                     doc_id = f"{namespace}/{clean_fn}"
        
        # Final safety check: if doc_id is still empty, use filename
        if not doc_id:
            doc_id = f"{namespace}/{os.path.basename(file_path).replace(' ', '_').replace('.pdf', '')}"
        
        # Ensure doc_id is safe for Neo4j and Postgres
        doc_id = re.sub(r'[^\w\d\-_/.]', '_', doc_id)

        # FAILS_SAFE DE-DUPLICATION: 
        # 1. Check if this doc_id already exists in the system.
        existing_hash = self.state_manager.get_existing_doc_hash(doc_id)
        
        if existing_hash:
            if existing_hash == file_hash:
                # Exact content match -> Secure De-duplication Skip.
                logger.info(f"[Safe Skip] {rel_path} -> doc_id {doc_id} matches existing content hash. Skipping.")
                self.state_manager.update_status(rel_path, 'COMPLETED', doc_id=doc_id, metadata=meta)
                with self._processed_cache_lock:
                    self.processed_cache.add(rel_path)
                return
            else:
                # Collision detected -> Different content sharing the same extracted ID.
                # Action: Append short hash to current doc_id to keep it unique.
                collision_id = f"{doc_id}_{file_hash[:6]}"
                logger.warning(f"[Collision Detected] {rel_path} extracted doc_id {doc_id} which conflicts with a different document. "
                               f"Using collision_id: {collision_id}")
                doc_id = collision_id
        
        # Mức độ 2: Sync to Knowledge Graph (Neo4j)
        self.sync_to_graph(doc_id, meta, relationships)

        # Semantic Chunking (with text normalization at source)
        semantic_chunks = []
        for chunk in raw_chunks:
            text = chunk["text"]

            # Phase 1: Normalize text BEFORE chunking
            # Strip government document boilerplate headers
            text = strip_document_boilerplate(text)
            # [P5-FIX] Strip Nơi nhận distribution + signer blocks
            text = strip_noi_nhan_block(text)
            text = strip_signer_block(text)
            # Rejoin hard-wrapped lines for better embedding quality
            text = rejoin_paragraphs(text)

            # Table detection: original flag + markdown table regex + garbled heuristic
            is_tabular = (
                chunk.get("is_table", False)
                or bool(re.search(r'\|.*\|.*\n\|[-:\s|]+\|', text))
                or detect_garbled_table(text)
            )
            
            if is_tabular:
                semantic_chunks.append({
                    "text": text.strip(),
                    "source": os.path.basename(file_path),
                    "page": chunk["page"],
                    "is_table": True,
                    "chunk_type": "parent",
                    "hierarchy_path": f"[{doc_id} > Table > Page {chunk['page']}]",
                    # [Change 3] Identity fields — previously missing on table chunks
                })
            else:
                doc_chunks = self.chunker.chunk_document(
                    text, 
                    os.path.basename(file_path), 
                    chunk["page"], 
                    doc_id,
                    layout=chunk.get("layout")
                )
                semantic_chunks.extend(doc_chunks)

        # [C1] Deduplicate parent chunks — remove identical content from multi-page overlap
        seen_fingerprints = set()
        deduped_chunks = []
        for c in semantic_chunks:
            if c.get("chunk_type") == "parent":
                # Use full content hash for reliable dedup (300-char prefix was too weak)
                fp = hash(c.get("text", "").strip())
                if fp in seen_fingerprints:
                    continue
                seen_fingerprints.add(fp)
            deduped_chunks.append(c)
        if len(deduped_chunks) < len(semantic_chunks):
            logger.info(f"  [C1] Dedup: {len(semantic_chunks)} → {len(deduped_chunks)} chunks ({len(semantic_chunks) - len(deduped_chunks)} duplicates removed)")
        semantic_chunks = deduped_chunks

        # [Change 2+3] Central identity assignment — Single Source of Truth
        # Set doc_id, doc_number, and chunk_id on ALL chunks uniformly
        raw_doc_number = meta.get("doc_number", "")
        for idx, c in enumerate(semantic_chunks):
            c["doc_id"] = doc_id
            c["doc_number"] = raw_doc_number
            if "chunk_id" not in c:
                c["chunk_id"] = f"{doc_id}::p{c.get('page', 0)}::{c.get('chunk_type', 'parent')}_{idx}"

        # Phase 2: Parallel Synthetic Query Generation for Parent Chunks
        parent_chunks = [c for c in semantic_chunks if c.get("chunk_type") == "parent" and len(c.get("text", "")) > 300]
        
        # Prioritize longer chunks for better query generation
        parent_chunks.sort(key=lambda x: len(x.get("text", "")), reverse=True)
        
        # Increase coverage: process top 30 parent chunks (was 10)
        target_chunks = parent_chunks[:30]
        
        if target_chunks:
            logger.info(f"  Generating synthetic queries for {len(target_chunks)} dense chunks in parallel...")
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
        
        # Initialize empty synthetic_queries for the rest
        for c in semantic_chunks:
            if "synthetic_queries" not in c:
                c["synthetic_queries"] = ""

        if semantic_chunks:
            self.index_chunks(semantic_chunks, summary, meta, file_hash)
            
        if not failed_pages:
            # Mark as completely finished in DB
            self.state_manager.update_status(rel_path, 'COMPLETED', doc_id=doc_id, metadata=meta)
            with self._processed_cache_lock:
                self.processed_cache.add(rel_path)
            
            # Update Neo4j Status to mark the document node as processed
            self.mark_file_done(file_hash)
            
            # EXPORT PROCESSED DATA (JSON/Markdown)
            if self.exporter:
                try:
                    self.exporter.export(rel_path, doc_id, meta, summary, semantic_chunks)
                except Exception as e:
                    logger.error(f"Failed to export data for {doc_id}: {e}")
            
            # TELEGRAM NOTIFICATION: Every 50 documents
            try:
                count, file_list = self.state_manager.check_notification_milestone(milestone_step=50)
                if count and file_list:
                    from core.notifier import notifier
                    import asyncio
                    # Use a new event loop to avoid conflict with potential existing one
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(notifier.notify_milestone(count, file_list))
                        else:
                            loop.run_until_complete(notifier.notify_milestone(count, file_list))
                    except RuntimeError:
                        asyncio.run(notifier.notify_milestone(count, file_list))
                    logger.info(f"Sent Telegram notification for milestone {count}")
            except Exception as e:
                logger.error(f"Failed to check/send Telegram milestone notification: {e}")

    def _process_single_page(self, file_path: str, i: int, total_pages: int):
        """Helper for parallel page processing.

        Each worker opens its own fitz.Document instance — fitz.Document is not
        thread-safe even for reads, so sharing a single instance across threads
        can cause corrupted page data or segfaults.
        """
        try:
            img_bytes = None
            with fitz.open(file_path) as doc:
                page = doc[i]
                text_raw = page.get_text().strip()

                # Skip digital signature metadata pages
                if i == 0 and len(text_raw) < 80 and ("Người ký" in text_raw or "Cơ quan" in text_raw or "Email" in text_raw):
                    logger.info(f"  Skipping page 1 (digital signature metadata only)")
                    return None

                # If digital layout seems solid, use it directly (saves OCR/Vision time entirely)
                # [P1-3] Smart quality check: detect bad text layers (char-separated spacing)
                if len(text_raw) > 100:
                    # Check for OCR spacing issue: count short Vietnamese tokens (1-2 chars)
                    _VN_CHAR_RE = re.compile(r'^[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]+$')
                    tokens = text_raw.split()
                    if len(tokens) > 5:
                        short_vn = sum(1 for t in tokens if len(t) <= 2 and _VN_CHAR_RE.match(t))
                        spacing_ratio = short_vn / len(tokens)
                        if spacing_ratio > 0.30:
                            logger.info(f"  [P1-3] Page {i+1}: spacing_ratio={spacing_ratio:.2f} > 0.30 → forcing OCR (bad text layer)")
                            pix = page.get_pixmap(dpi=150)
                            img_bytes = pix.tobytes("jpeg")
                            # Fall through to OCR path below
                        else:
                            # Digital text quality is good — use fast path
                            dict_text = page.get_text("dict")
                            layout_segments = []
                            full_text_parts = []

                            for block in dict_text.get("blocks", []):
                                if block.get("type") == 0:  # Text block
                                    block_text = ""
                                    for line in block.get("lines", []):
                                        for span in line.get("spans", []):
                                            span_text = span.get("text")
                                            if span_text:
                                                block_text += span_text + " "

                                    block_text = block_text.strip()
                                    if block_text:
                                        full_text_parts.append(block_text)
                                        # [C3] Detect table blocks in digital PDFs
                                        pipe_count = block_text.count('|')
                                        tab_count = block_text.count('\t')
                                        lines_in_block = block_text.split('\n')
                                        short_fields = sum(1 for l in lines_in_block if len(l.strip()) < 15)
                                        has_digit_runs = len(re.findall(r'\d{1,3}(?:[.,]\d{3})*', block_text)) > 3
                                        is_table_block = (
                                            pipe_count >= 3
                                            or tab_count >= 3
                                            or (short_fields > 3 and has_digit_runs)
                                            or bool(re.search(r'\|.*\|.*\n\|[-:\s|]+\|', block_text))
                                        )
                                        label = "table" if is_table_block else "text"
                                        layout_segments.append({
                                            "label": label,
                                            "text": block_text,
                                            "bbox": list(block.get("bbox", [0, 0, 1000, 1000]))
                                        })

                            # [TABLE-FIX] Merge pdfplumber-detected tables into fitz text.
                            # Replaces fragmented cell-per-line output with proper markdown tables.
                            raw_text = "\n".join(full_text_parts)
                            try:
                                from ingestion.table_extraction import extract_and_merge_tables
                                page_h = page.rect.height if hasattr(page, "rect") else 0.0
                                raw_text = extract_and_merge_tables(
                                    pdf_path=file_path,
                                    page_num=i,
                                    fitz_text=raw_text,
                                    page_height=page_h,
                                )
                            except Exception as _te:
                                logger.debug(f"  [TABLE-FIX] skipped page {i+1}: {_te}")

                            # [PARA-FIX] Rejoin hard-wrapped paragraph lines so that
                            # each Milvus chunk gets flowing sentences, not line fragments.
                            try:
                                from ingestion.text_normalizer import rejoin_paragraphs
                                raw_text = rejoin_paragraphs(raw_text)
                            except Exception as _pe:
                                logger.debug(f"  [PARA-FIX] skipped page {i+1}: {_pe}")

                            # [FIGURE-FIX] Describe embedded figure images using vision LLM.
                            # Only triggered for digital PDFs that have embedded images AND
                            # contain "Hình" references in extracted text.
                            try:
                                _has_images = bool(page.get_images(full=True))
                                _has_hinh = bool(re.search(r'Hình\s+\d', raw_text))
                                if _has_images and _has_hinh:
                                    from ingestion.figure_extractor import describe_page_figures
                                    raw_text = describe_page_figures(
                                        doc=doc,
                                        page_num=i,
                                        page_text=raw_text,
                                        pdf_path=file_path,
                                        max_figures_per_page=2,
                                    )
                            except Exception as _fe:
                                logger.debug(f"  [FIGURE-FIX] skipped page {i+1}: {_fe}")

                            return {
                                "text": raw_text,
                                "page": i + 1,
                                "layout": layout_segments,
                                "source": "digital"
                            }

                else:
                    # Page is scanned/image — capture bytes before closing the doc
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("jpeg")
            # doc is now closed; run the vision call outside the fitz context
            if img_bytes is not None:
                res = _llm_extract_page(img_bytes, page_num=i + 1, digital_text=text_raw)

                if res.get("text", ""):
                    return {
                        "text": res["text"],
                        "page": i + 1,
                        "bbox": res.get("bbox", []),
                        "is_table": res.get("is_table", False),
                        "layout": res.get("layout", []),
                        "source": res.get("source", "vision")
                    }
                else:
                    return {"page": i + 1, "error": "No text extracted"}
        except Exception as e:
            logger.error(f"  Error extracting from page {i+1}: {e}")
            return {"page": i + 1, "error": str(e)}

    def extract_pdf(self, file_path):
        """Hybrid extraction: digital text first, Vision OCR fallback page-by-page (Parallel)."""
        chunks = []
        failed_pages = []
        try:
            # Open once just to get the page count, then close.
            # Each worker thread opens its own fitz.Document to avoid thread-safety issues.
            with fitz.open(file_path) as probe:
                total_pages = len(probe)

            concurrency = min(total_pages, MAX_OCR_CONCURRENCY)

            with ThreadPoolExecutor(max_workers=concurrency) as page_executor:
                futures = [
                    page_executor.submit(self._process_single_page, file_path, i, total_pages)
                    for i in range(total_pages)
                ]

                for future in futures:
                    res = future.result()
                    if res is None:
                        continue
                    if "error" in res:
                        failed_pages.append(res["page"])
                    else:
                        chunks.append(res)

            chunks.sort(key=lambda x: x["page"])
            
        except Exception as e:
            logger.error(f"  Critical error: Could not process {file_path}: {e}")
            return [], [0]
            
        return chunks, failed_pages

    def index_chunks(self, chunks, summary, meta, file_hash):
        if not chunks:
            return
            
        chunk_types = [c.get("chunk_type", "parent") for c in chunks]
        logger.info(f"  Preparing to index {len(chunks)} chunks: {chunk_types.count('parent')} parents, {chunk_types.count('child')} children")
        
        # Cleanup existing entries for this file_hash to prevent duplicates from previous failed runs
        # Validate file_hash is a hex string before interpolating into the filter expression
        try:
            if not re.fullmatch(r'[0-9a-fA-F]+', file_hash):
                raise ValueError(f"Unexpected file_hash format: {file_hash!r}")
            self.collection.delete(expr=f"file_hash == '{file_hash}'")
        except Exception as e:
            logger.warning(f"  Cleanup of old chunks for {file_hash} failed (standard if new file): {e}")

        # Batch size for Milvus inserts to prevent gRPC frame size errors
        BATCH_SIZE = 200
        
        # [C5] Quality gate — filter out empty, too-short, or garbled chunks before embedding
        quality_chunks = []
        for c in chunks:
            text = c.get("text", "").strip()
            # Skip empty or very short chunks (noise)
            if len(text) < 20:
                continue
            # Skip garbled OCR chunks
            if detect_garbled_table(text):
                logger.debug(f"  [C5] Skipping garbled chunk (page {c.get('page', '?')}): {text[:60]}...")
                continue
            quality_chunks.append(c)
        if len(quality_chunks) < len(chunks):
            logger.info(f"  [C5] Quality gate: {len(chunks)} → {len(quality_chunks)} chunks ({len(chunks) - len(quality_chunks)} low-quality removed)")
        chunks = quality_chunks
        if not chunks:
            logger.warning(f"  [C5] All chunks filtered by quality gate — nothing to index.")
            return

        for i in range(0, len(chunks), BATCH_SIZE):
            batch_chunks = chunks[i:i + BATCH_SIZE]
            # [P0-FIX] Truncate oversized chunks to prevent Milvus varchar overflow (max_length=15000)
            MAX_TEXT_LEN = 14500
            texts = []
            for c in batch_chunks:
                t = c["text"]
                if len(t) > MAX_TEXT_LEN:
                    logger.warning(f"  [P0] Truncating chunk ({len(t)} → {MAX_TEXT_LEN} chars) on page {c.get('page', '?')}")
                    t = t[:MAX_TEXT_LEN] + "…[truncated]"
                texts.append(t)
            
            # [C2] Strip [doc_id] prefix before embedding for cleaner semantic vectors
            # The prefix is kept in the stored text field but stripped for the embedding model
            texts_for_embedding = [re.sub(r'^\[.*?\]\s*', '', t, count=1) for t in texts]
            # Also strip context inheritance prefix ::: for cleaner embedding
            texts_for_embedding = [re.sub(r'^.*?:::\s*', '', t, count=1) for t in texts_for_embedding]
            
            embeddings = self.model.embed_documents(texts_for_embedding)
            dense_embeddings = embeddings["dense"]
            sparse_vectors = embeddings["sparse"]
            
            summary_bytes = summary.encode('utf-8')
            safe_summary = summary_bytes[:2040].decode('utf-8', 'ignore') if len(summary_bytes) > 2040 else summary

            def safe_trunc(val, limit):
                """Truncate to fit within byte limit without breaking UTF-8 multibyte chars."""
                if not val: return ""
                v_str = str(val)
                v_bytes = v_str.encode('utf-8')
                if len(v_bytes) <= limit: return v_str
                # [I5] Truncate in character space to avoid splitting multibyte UTF-8
                while len(v_str.encode('utf-8')) > limit and v_str:
                    v_str = v_str[:-1]
                return v_str

            data = [
                texts,
                [c["source"] for c in batch_chunks],
                [c.get("page", 1) for c in batch_chunks],
                [safe_summary for _ in batch_chunks],
                [safe_trunc(meta.get("date", "unknown"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("type", "unknown"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("authority", "unknown"), 64) for _ in batch_chunks],
                [file_hash for _ in batch_chunks],
                [c.get("is_table", False) for c in batch_chunks],
                [safe_trunc(c.get("chunk_type", "parent"), 16) for c in batch_chunks],
                [safe_trunc(c.get("parent_id", ""), 256) for c in batch_chunks],
                [safe_trunc(c.get("doc_number", ""), 128) for c in batch_chunks],
                [safe_trunc(c.get("doc_id", ""), 256) for c in batch_chunks],
                [safe_trunc(c.get("chunk_id", ""), 512) for c in batch_chunks],
                [json.dumps(c.get("bbox", [0,0,1000,1000])) for c in batch_chunks],
                [safe_trunc(meta.get("validity_status", "ACTIVE"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("legal_level", "UNKNOWN"), 32) for _ in batch_chunks],
                [safe_trunc(c.get("hierarchy_path", ""), 1024) for c in batch_chunks],
                [0 for _ in batch_chunks], # citation_count
                [safe_trunc(meta.get("project_code", "GENERIC"), 64) for _ in batch_chunks],
                [safe_trunc(meta.get("discipline", "UNKNOWN"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("doc_status", "ACTIVE"), 32) for _ in batch_chunks],
                [meta.get("revision", 0) for _ in batch_chunks],
                [safe_trunc(c.get("synthetic_queries", ""), 4090) for c in batch_chunks],
                [safe_trunc(meta.get("source_category", "KHAC"), 64) for _ in batch_chunks],
                dense_embeddings,
                sparse_vectors
            ]
            
            self.collection.insert(data)
            logger.info(f"  Inserted batch {i//BATCH_SIZE + 1} ({len(batch_chunks)} chunks)")
            
        self.collection.flush()
        logger.info(f"  Successfully Indexed all {len(chunks)} chunks (Hybrid Parent-Child) into Milvus")

    def parse_relationships_llm(self, text):
        """Extract legal relationships using LLM for higher precision with Regex fallback."""
        try:
            payload = {
                "model": JSON_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a Vietnamese legal knowledge graph expert. Extract relationships between documents as JSON. Do NOT include any 'Thinking Process', 'Analysis', or preamble. NO text before or after the JSON block. Start exactly with '{' and end exactly with '}'."},
                    {"role": "user", "content": f"Extract relationship JSON from this text (Respond ONLY with JSON):\n\n{text[:6000]}"}
                ],
                "max_tokens": 4096,
                "temperature": 0.0,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            }
            headers = {"Authorization": f"Bearer {self.vision.api_key}"}
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    resp = self._http_client.post(self.vision.api_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        time.sleep(5 * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    rels = _extract_json_from_response(data)
                    if rels:
                        for key in ["replaces", "amends", "references", "guides"]:
                            if key not in rels or not isinstance(rels[key], list):
                                rels[key] = []
                        logger.info(f"  LLM extracted relationships: {rels}")
                        return rels
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Relationship extraction failed after {max_retries} attempts: {e}")
                        return self.parse_relationships(text)
                    time.sleep(5 * (2 ** attempt))
        except Exception as e:
            logger.warning(f"LLM relationship extraction failed: {e}. Falling back to Regex.")
            return self.parse_relationships(text)

    def parse_relationships(self, text):
        """Extract legal relationships from text."""
        rels = {"replaces": [], "amends": [], "references": [], "guides": []}
        
        # Pattern to capture document numbers: supports Vietnamese Đ and full types
        # e.g., "15/2021/NĐ-CP", "17/2010/TT-BTP", "01/2024"
        doc_pattern = r'(?:số\s+)?(\d+/\d+/[A-ZĐ0-9-]+|\d+/\d+)'
        
        # 1. Thay thế (Replaces)
        replaces = re.findall(rf'(?:thay\s+thế|bãi\s+bỏ)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["replaces"].extend([r.strip() for r in replaces])
        
        # 2. Sửa đổi, bổ sung (Amends)
        amends = re.findall(rf'(?:sửa\s+đổi|bổ\s+sung)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["amends"].extend([r.strip() for r in amends])
        
        # 3. Căn cứ (References)
        refs = re.findall(rf'(?:Căn\s+cứ|Theo|Tại)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["references"].extend([r.strip() for r in refs])

        # 4. Hướng dẫn (Guides) - Often found in Circulars referring to Decrees
        guides = re.findall(rf'(?:Hướng\s+dẫn)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["guides"].extend([r.strip() for r in guides])
        
        # Deduplicate
        for k in rels:
            rels[k] = list(set(rels[k]))
            
        return rels

    def sync_to_graph(self, doc_id, meta, relationships):
        """Sync Document Nodes and Edges to Neo4j."""
        with self.neo4j_driver.session() as session:
            # 1. Create/Merge current Document Node
            session.run(
                """
                MERGE (d:Document {id: $id})
                SET d.doc_type = $type, d.authority = $auth, d.date = $date,
                    d.doc_number = $doc_number,
                    d.status = $status, d.file_name = $file_name,
                    d.validity_status = $validity_status,
                    d.project_code = $project_code,
                    d.discipline = $discipline,
                    d.revision = $revision,
                    d.source_category = $source_category
                """,
                id=doc_id, type=meta.get("type", "unknown"), auth=meta.get("authority", "unknown"),
                date=meta.get("date", "unknown"), file_name=meta.get("file_name", doc_id),
                doc_number=meta.get("doc_number", ""),
                status=meta.get("doc_status", "ACTIVE"),
                validity_status=meta.get("validity_status", "ACTIVE"),
                project_code=meta.get("project_code", "GENERIC"),
                discipline=meta.get("discipline", "UNKNOWN"),
                revision=meta.get("revision", 0),
                source_category=meta.get("source_category", "KHAC")
            )
            
            # 2. Create relationships
            for target_id in relationships["replaces"]:
                # If Doc A replaces Doc B -> mark Doc B as OUTDATED
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    SET target.status = 'OUTDATED'
                    MERGE (source)-[:REPLACES]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )

                # 2.1 Cascading Sync (Triggered by 'REPLACES' relationship)
                try:
                    logger.info(f"  Triggering cascading status sync for replaced doc: {target_id}")
                    # [I2] Use robust async bridge that handles both running and new event loops
                    try:
                        loop = asyncio.get_running_loop()
                        # Already in an async context — schedule as a task
                        asyncio.ensure_future(self.lifecycle_service.sync_document_status(target_id, "OUTDATED"))
                    except RuntimeError:
                        # No running loop — safe to use asyncio.run
                        asyncio.run(self.lifecycle_service.sync_document_status(target_id, "OUTDATED"))
                except Exception as e:
                    logger.error(f"  Automated Lifecycle Sync failed for {target_id}: {e}")
                
            for target_id in relationships["amends"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    MERGE (source)-[:AMENDS]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )
                
            for target_id in relationships["references"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    MERGE (source)-[:REFERENCES]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )

            for target_id in relationships["guides"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    MERGE (source)-[:GUIDES]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )
        logger.info(f"  Synced Graph edges for {doc_id}: {relationships}")

    def run(self):
        """Main entry point: scan → enqueue → consume.
        
        Mode 1 (Redis available): Scan files → push to Redis Stream → consume
        Mode 2 (Fallback):        Scan files → process directly with ThreadPoolExecutor
        """
        # Try to initialize Redis Queue
        try:
            from ingestion.queue import RedisQueue
            self._queue = RedisQueue()
            logger.info("Redis queue connected ✓ — using queue-based ingestion")
        except Exception as e:
            self._queue = None
            logger.warning(f"Redis queue unavailable, using legacy mode: {e}")

        if self._queue:
            self._scan_and_enqueue()
            self._consume_queue()
        else:
            self._run_legacy()

    def _scan_and_enqueue(self):
        """Scan filesystem and push all unprocessed files to Redis Stream."""
        logger.info("Scanning filesystem for PDF files...")
        pdf_files = []
        for root, _, files in os.walk(SOURCE_DIR):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))

        logger.info(f"Found {len(pdf_files)} PDF files. Filtering already-queued...")
        
        # Filter out already-queued files
        to_enqueue = []
        for f in pdf_files:
            rel_path = os.path.relpath(f, SOURCE_DIR)
            # Skip if already in processed cache
            with self._processed_cache_lock:
                if rel_path in self.processed_cache:
                    continue
            # Skip if already queued
            if self._queue.is_file_queued(rel_path):
                continue
            to_enqueue.append({
                "file_path": f,
                "rel_path": rel_path,
                "content_hash": "",  # Hash computed at intake stage
            })

        if to_enqueue:
            # Priority sort: BXD-GTVT and QCVN folders first
            _PRIORITY_PATTERNS = ['BXD-GTVT', 'QCVN']
            def _priority_key(item):
                rp = item["rel_path"]
                for i, pat in enumerate(_PRIORITY_PATTERNS):
                    if pat in rp:
                        return (0, i, rp)  # Priority 0 = first
                return (1, 0, rp)  # Priority 1 = later
            to_enqueue.sort(key=_priority_key)
            logger.info(f"Priority: {sum(1 for x in to_enqueue if any(p in x['rel_path'] for p in _PRIORITY_PATTERNS))} priority files (BXD-GTVT/QCVN) queued first")

            self._queue.enqueue_batch(to_enqueue)
            for f in to_enqueue:
                self._queue.mark_queued(f["rel_path"])
        else:
            logger.info("No new files to enqueue")

    def _consume_queue(self):
        """Consumer loop: claim messages from Redis → process → ack/nack."""
        logger.info(f"Starting consumer loop (worker: {self._queue.consumer_id})...")

        # Start filesystem watcher for new files (enqueues to Redis)
        event_handler = self.QueueWatchHandler(self)
        observer = Observer()
        observer.schedule(event_handler, SOURCE_DIR, recursive=True)
        observer.start()

        try:
            while True:
                messages = self._queue.claim_next(count=1, block_ms=5000)
                if not messages:
                    # Update Prometheus metrics while idle
                    self._queue.update_metrics()
                    continue

                for msg in messages:
                    file_path = msg.get("file_path", "")
                    msg_id = msg.get("msg_id", "")
                    
                    if not file_path or not os.path.exists(file_path):
                        self._queue.ack(msg_id)
                        continue

                    try:
                        self.safe_process(file_path)
                        self._queue.ack(msg_id)
                    except Exception as e:
                        self._queue.nack(msg_id, str(e))

                # Update metrics after batch
                self._queue.update_metrics()

        except KeyboardInterrupt:
            logger.info("Consumer loop interrupted")
            observer.stop()
        observer.join()

    def _run_legacy(self):
        """Legacy mode: direct filesystem polling with ThreadPoolExecutor."""
        logger.info(f"Starting parallel ingestion scan (legacy mode)...")
        pdf_files = []
        for root, _, files in os.walk(SOURCE_DIR):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))
        
        logger.info(f"Found {len(pdf_files)} PDF files. Processing with {MAX_WORKERS} workers...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            executor.map(self.safe_process, pdf_files)
        
        logger.info("Initial scan complete. Starting live watch...")
        event_handler = self.WatchHandler(self)
        observer = Observer()
        observer.schedule(event_handler, SOURCE_DIR, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    class QueueWatchHandler(FileSystemEventHandler):
        """File watcher that enqueues new files to Redis instead of processing directly."""
        def __init__(self, ingestor):
            self.ingestor = ingestor

        def on_created(self, event):
            if not event.is_directory and event.src_path.lower().endswith('.pdf'):
                rel_path = os.path.relpath(event.src_path, SOURCE_DIR)
                logger.info(f"New file detected, enqueuing: {rel_path}")
                time.sleep(2)  # Wait for file to finish writing
                try:
                    self.ingestor._queue.enqueue(event.src_path, "", rel_path)
                    self.ingestor._queue.mark_queued(rel_path)
                except Exception as e:
                    logger.error(f"Failed to enqueue new file: {e}")

    class WatchHandler(FileSystemEventHandler):
        """Legacy file watcher (used when Redis is unavailable)."""
        def __init__(self, ingestor):
            self.ingestor = ingestor
            self._active_threads: set = set()

        def on_created(self, event):
            if not event.is_directory and event.src_path.lower().endswith('.pdf'):
                logger.info(f"New file detected: {event.src_path}")
                def _process(path):
                    time.sleep(2)
                    try:
                        self.ingestor.process_file(path)
                    except Exception as e:
                        logger.error(f"Error processing new file {path}: {e}")
                    finally:
                        self._active_threads.discard(threading.current_thread())
                t = threading.Thread(target=_process, args=(event.src_path,), daemon=True)
                self._active_threads.add(t)
                t.start()

if __name__ == "__main__":
    # Start Prometheus Metrics Server on port 8001
    try:
        start_http_server(8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as e:
        logger.error(f"Could not start prometheus server: {e}")

    # Wait for other services to be healthy
    time.sleep(5)
    ingestor = ProductionIngestor()
    ingestor.run()

