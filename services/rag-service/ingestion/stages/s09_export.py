"""Stage 9: Export — Write processed data to JSON/Markdown."""
import logging

from ingestion.models import ProcessedDocument
from ingestion.stages.s04_identity import get_final_doc_id

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """Export processed document to JSON and Markdown files."""
    if not ctx.exporter:
        return doc

    if doc.failed_pages:
        logger.info("  Skipping export — document has failed pages")
        return doc

    doc_id = get_final_doc_id(doc)
    meta = doc.metadata.to_dict()
    chunk_dicts = [c.to_dict() for c in doc.chunks]

    try:
        ctx.exporter.export(doc.identity.rel_path, doc_id, meta, doc.summary, chunk_dicts)
    except Exception as e:
        logger.error(f"Failed to export data for {doc_id}: {e}")

    return doc
