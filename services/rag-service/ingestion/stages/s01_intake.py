"""Stage 1: Intake — File discovery, hashing, and distributed claim."""
import hashlib
import logging
import os
import threading

from ingestion.models import ProcessedDocument, DocumentIdentity

logger = logging.getLogger(__name__)

SOURCE_DIR = "/app/data/legal_docs_source"


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument | None:
    """Check cache, compute hash, claim file for processing.
    
    Returns None if file should be skipped.
    """
    rel_path = doc.identity.rel_path

    # FAST SKIP: Check in-memory cache before hashing
    with ctx._processed_cache_lock:
        if rel_path in ctx.processed_cache:
            return None

    logger.info(f"Evaluating file: {rel_path}")
    file_hash = _get_file_hash(doc.file_path)
    doc.identity.content_hash = file_hash

    # Namespace scoping
    doc.identity.namespace = rel_path.split(os.sep)[0] if os.sep in rel_path else "ROOT"

    # Distributed Coordination: Try to claim the file
    if not ctx.claim_file(file_hash, rel_path):
        logger.info(f"[Distributed Skip] {rel_path} (already being processed or done)")
        return None

    logger.info(f"Processing: {rel_path}")
    return doc


def _get_file_hash(file_path: str) -> str:
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
