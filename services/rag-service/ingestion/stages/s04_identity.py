"""Stage 4: Identity — Resolve doc_id with dedup + collision detection."""
import logging
import os
import re

from ingestion.models import ProcessedDocument

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument | None:
    """Finalize doc_id using namespace + doc_number, handle collisions."""
    identity = doc.identity
    identity.doc_number = doc.metadata.doc_number or ""

    doc_id = identity.doc_id  # Computed property

    # DE-DUPLICATION: Check if this doc_id already exists
    existing_hash = ctx.state_manager.get_existing_doc_hash(doc_id)
    if existing_hash:
        if existing_hash == identity.content_hash:
            # Exact content match → secure skip
            logger.info(f"[Safe Skip] {identity.rel_path} → doc_id {doc_id} matches existing hash")
            ctx.state_manager.update_status(
                identity.rel_path, 'COMPLETED',
                doc_id=doc_id, metadata=doc.metadata.to_dict()
            )
            import threading
            with ctx._processed_cache_lock:
                ctx.processed_cache.add(identity.rel_path)
            return None
        else:
            # Collision → append hash suffix
            collision_id = f"{doc_id}_{identity.content_hash[:6]}"
            logger.warning(f"[Collision] {identity.rel_path}: {doc_id} conflicts. Using: {collision_id}")
            # Override the doc_number to force the computed doc_id to include the suffix
            identity.doc_number = ""  # Clear so doc_id uses fallback
            # Manually set a patched doc_id by updating namespace path
            doc._collision_doc_id = collision_id

    return doc


def get_final_doc_id(doc: ProcessedDocument) -> str:
    """Get the final doc_id, accounting for collisions."""
    return getattr(doc, '_collision_doc_id', None) or doc.identity.doc_id
