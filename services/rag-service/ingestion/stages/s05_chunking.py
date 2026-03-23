"""Stage 5: Chunking — Semantic chunking + dedup + central identity assignment."""
import logging
import os

from ingestion.models import ProcessedDocument, Chunk
from ingestion.chunking import DocumentChunker
from ingestion.text_normalizer import rejoin_paragraphs, is_table_chunk, strip_document_boilerplate
from ingestion.stages.s04_identity import get_final_doc_id
from ingestion.doc_boundary import strip_issuing_document

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """Chunk raw pages into semantic chunks with identity assignment."""
    doc_id = get_final_doc_id(doc)
    chunker = ctx.chunker

    # [doc_boundary] Strip issuing Thông tư/QĐ pages for QCVN/TCVN/tiêu chuẩn ngành
    doc_type = doc.metadata.type if doc.metadata else None
    doc.raw_pages = strip_issuing_document(doc.raw_pages, doc_type=doc_type)

    semantic_chunks = []

    for page in doc.raw_pages:
        text = page.text

        # Normalize text before chunking
        text = strip_document_boilerplate(text)
        text = rejoin_paragraphs(text)

        # Table detection
        is_tabular = is_table_chunk(text, page_is_table=page.is_table)

        if is_tabular:
            semantic_chunks.append({
                "text": text.strip(),
                "source": os.path.basename(doc.file_path),
                "page": page.page,
                "is_table": True,
                "chunk_type": "parent",
                "hierarchy_path": f"[{doc_id} > Table > Page {page.page}]",
            })
        else:
            doc_chunks = chunker.chunk_document(
                text, os.path.basename(doc.file_path),
                page.page, doc_id,
                layout=page.layout
            )
            semantic_chunks.extend(doc_chunks)

    # [P7] Dedup parent chunks (use full hash instead of 300-char prefix)
    seen_fps = set()
    deduped = []
    for c in semantic_chunks:
        if c.get("chunk_type") == "parent":
            fp = hash(c.get("text", "").strip())
            if fp in seen_fps:
                continue
            seen_fps.add(fp)
        deduped.append(c)
    if len(deduped) < len(semantic_chunks):
        logger.info(f"  [C1] Dedup: {len(semantic_chunks)} → {len(deduped)} chunks")
    semantic_chunks = deduped

    # Central identity assignment — Single Source of Truth
    raw_doc_number = doc.metadata.doc_number or ""
    for idx, c in enumerate(semantic_chunks):
        c["doc_id"] = doc_id
        c["doc_number"] = raw_doc_number
        if "chunk_id" not in c:
            c["chunk_id"] = f"{doc_id}::p{c.get('page', 0)}::{c.get('chunk_type', 'parent')}_{idx}"

    # Convert to Chunk models
    doc.chunks = [
        Chunk(
            text=c.get("text", ""),
            source=c.get("source", ""),
            page=c.get("page", 0),
            chunk_type=c.get("chunk_type", "parent"),
            is_table=c.get("is_table", False),
            parent_id=c.get("parent_id", ""),
            hierarchy_path=c.get("hierarchy_path", ""),
            bbox=c.get("bbox", [0, 0, 1000, 1000]),
            doc_id=c.get("doc_id", ""),
            doc_number=c.get("doc_number", ""),
            chunk_id=c.get("chunk_id", ""),
        )
        for c in semantic_chunks
    ]

    return doc
