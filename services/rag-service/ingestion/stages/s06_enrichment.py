"""Stage 6: Enrichment — Summary, synthetic queries, graph sync."""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ingestion.models import ProcessedDocument
from ingestion.stages.s04_identity import get_final_doc_id

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """Generate synthetic queries for parent chunks + sync to Neo4j graph."""
    doc_id = get_final_doc_id(doc)

    # Sync to Knowledge Graph (Neo4j)
    ctx.sync_to_graph(doc_id, doc.metadata.to_dict(), doc.relationships.to_dict())

    # Parallel Synthetic Query Generation for parent chunks
    # [P2] Lowered threshold from 300→150 and cap from 30→60 for broader coverage
    parent_chunks = [c for c in doc.chunks if c.chunk_type == "parent" and len(c.text) > 150]
    parent_chunks.sort(key=lambda x: len(x.text), reverse=True)
    target_chunks = parent_chunks[:60]

    if target_chunks:
        logger.info(f"  Generating synthetic queries for {len(target_chunks)} dense chunks...")
        with ThreadPoolExecutor(max_workers=min(len(target_chunks), 8)) as executor:
            futures = {executor.submit(ctx.generate_synthetic_queries, c.text): c for c in target_chunks}
            for future in as_completed(futures):
                chunk = futures[future]
                try:
                    chunk.synthetic_queries = future.result()
                except Exception as e:
                    logger.error(f"  Synthetic query generation failed: {e}")
                    chunk.synthetic_queries = ""

    # Initialize empty synthetic_queries for the rest
    for c in doc.chunks:
        if not c.synthetic_queries:
            c.synthetic_queries = ""

    return doc
