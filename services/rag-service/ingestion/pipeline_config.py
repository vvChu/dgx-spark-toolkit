"""Shared configuration constants for the ingestion pipeline.

Centralizes config that was previously scattered across pipeline.py,
so mixins and stages can import from here without circular dependencies.

NOTE: Settings-dependent values are loaded lazily via _load() to avoid
module-level get_settings() calls that crash without env vars (e.g. in CI).
Pure env-var reads are safe at module level.
"""
import os

# Pure env-var reads (no Settings dependency) — safe at module level
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
MAX_DIGITAL_WORKERS = int(os.getenv("MAX_DIGITAL_WORKERS", "10"))
SOURCE_DIR = os.getenv("SOURCE_DIR", "/app/data/legal_docs_source")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j-graph:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS", "")
JSON_MODEL = os.getenv("JSON_MODEL", "rag-core")
# Free-tier-first models: use Google Direct API free quota, fallback to rag-core when exhausted
SYNTHETIC_QUERY_MODEL = os.getenv("SYNTHETIC_QUERY_MODEL", "gemma-3-27b")       # ~56K RPD free (4 keys)
TEXT_METADATA_MODEL = os.getenv("TEXT_METADATA_MODEL", "gemini-3.1-flash-lite")  # ~4K RPD free, 2.8s latency
RELATIONSHIP_MODEL = os.getenv("RELATIONSHIP_MODEL", "gemma-3-27b")             # ~84K RPD free, text-only (no competition with OCR)

# Image preprocessing & OCR rendering
IMAGE_PREPROCESS = os.getenv("IMAGE_PREPROCESS", "1") == "1"
OCR_RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "300"))

# Settings-dependent values — populated on first access
MILVUS_HOST: str = ""
MILVUS_PORT: str = ""
MAX_OCR_CONCURRENCY: int = 4
COLLECTION_NAME: str = ""

_loaded = False


def _load():
    """Lazy-load settings-dependent values."""
    global MILVUS_HOST, MILVUS_PORT, MAX_OCR_CONCURRENCY, COLLECTION_NAME, _loaded
    if _loaded:
        return
    from core.config import get_settings
    settings = get_settings()
    MILVUS_HOST = os.getenv("MILVUS_HOST", settings.MILVUS_HOST)
    MILVUS_PORT = os.getenv("MILVUS_PORT", settings.MILVUS_PORT)
    MAX_OCR_CONCURRENCY = settings.MAX_OCR_CONCURRENCY
    COLLECTION_NAME = settings.MILVUS_COLLECTION
    _loaded = True
