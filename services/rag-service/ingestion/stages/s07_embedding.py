"""Stage 7: Embedding — DEPRECATED pass-through.

Embedding is handled inside s08_indexing's ``index_chunks()`` for batch
efficiency.  This stage exists only so the 9-stage orchestrator numbering
is preserved; it does no work.
"""
import logging

from ingestion.models import ProcessedDocument

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """No-op pass-through — embedding is done inside s08_indexing."""
    return doc
