"""Stage 7: Embedding — Compute dense + sparse vectors (delegated to index_chunks)."""
import logging

from ingestion.models import ProcessedDocument

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """Embedding is handled inside index_chunks() for batch efficiency.
    
    This stage is a pass-through that validates chunks exist.
    In a future refactor, embedding could be separated from indexing.
    """
    if not doc.chunks:
        logger.warning("  No chunks to embed — skipping")
    else:
        logger.info(f"  {len(doc.chunks)} chunks ready for embedding+indexing")
    return doc
