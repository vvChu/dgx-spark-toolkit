"""Stage 2: OCR — PDF/DOCX/Image extraction with smart routing."""
import logging
import os

from ingestion.models import ProcessedDocument, RawPage

logger = logging.getLogger(__name__)

# Supported file extensions mapped to extraction methods
_EXT_MAP = {
    '.pdf': 'extract_pdf',
    '.docx': 'extract_docx',
    '.doc': 'extract_doc',
    '.jpg': 'extract_image',
    '.jpeg': 'extract_image',
    '.png': 'extract_image',
    '.xls': 'extract_spreadsheet',
    '.xlsx': 'extract_spreadsheet',
}


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument | None:
    """Extract raw text pages from PDF/DOCX/Image using ctx (ProductionIngestor).

    Routes to the appropriate extraction method based on file extension.
    """
    ext = os.path.splitext(doc.file_path)[1].lower()
    method_name = _EXT_MAP.get(ext)

    if method_name is None:
        logger.warning(f"  Unsupported file format: {ext} for {doc.identity.rel_path}")
        ctx.state_manager.update_status(
            doc.identity.rel_path, 'FAILED',
            error=f"Unsupported file format: {ext}"
        )
        return None

    # Get the extraction method from ctx (ProductionIngestor)
    extract_fn = getattr(ctx, method_name, None)

    # DOC files need special handling (convert_doc_to_docx → extract_docx)
    if ext == '.doc' and extract_fn is None:
        try:
            from ingestion.doc_converter import extract_doc
            raw_chunks, failed_pages = extract_doc(doc.file_path)
        except Exception as e:
            logger.error(f"  DOC extraction failed: {e}")
            raw_chunks, failed_pages = [], [0]
    elif extract_fn is not None:
        raw_chunks, failed_pages = extract_fn(doc.file_path)
    else:
        logger.warning(f"  No extraction method '{method_name}' on ctx for {ext}")
        ctx.state_manager.update_status(
            doc.identity.rel_path, 'FAILED',
            error=f"Extraction method '{method_name}' not available"
        )
        return None

    if failed_pages:
        logger.warning(f"  {doc.identity.rel_path} HAS FAILED PAGES: {failed_pages}")
        doc.failed_pages = failed_pages
        # Only mark as FAILED if we have NO successfully extracted content
        # (retry escalation in extraction.py has already run by this point)
        if not raw_chunks:
            ctx.state_manager.update_status(
                doc.identity.rel_path, 'FAILED',
                error=f"Failed pages: {failed_pages} (no content extracted)"
            )
            return None

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
