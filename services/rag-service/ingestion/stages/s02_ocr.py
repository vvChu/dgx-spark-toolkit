"""Stage 2: OCR — PDF extraction (digital + Vision OCR fallback)."""
import logging

from ingestion.models import ProcessedDocument, RawPage

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument | None:
    """Extract raw text pages from PDF using ctx (ProductionIngestor)."""
    raw_chunks, failed_pages = ctx.extract_pdf(doc.file_path)

    if failed_pages:
        logger.warning(f"  {doc.identity.rel_path} HAS FAILED PAGES: {failed_pages}")
        ctx.state_manager.update_status(doc.identity.rel_path, 'FAILED', error=f"Failed pages: {failed_pages}")
        doc.failed_pages = failed_pages

    if not raw_chunks:
        if not failed_pages:
            ctx.state_manager.update_status(
                doc.identity.rel_path, 'FAILED',
                error="No raw chunks extracted — file may be empty or corrupt"
            )
        return None  # Nothing to process

    # Convert dict chunks to RawPage models
    doc.raw_pages = [
        RawPage(
            text=c.get("text", ""),
            page=c.get("page", 0),
            is_table=c.get("is_table", False),
            layout=c.get("layout", []),
            bbox=c.get("bbox", []),
            source=c.get("source", "digital"),
        )
        for c in raw_chunks
    ]
    return doc
