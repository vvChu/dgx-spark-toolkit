"""Stage 8: Indexing — Insert chunks into Milvus + mark done in PostgreSQL."""
import logging

from ingestion.models import ProcessedDocument
from ingestion.stages.s04_identity import get_final_doc_id

logger = logging.getLogger(__name__)


def run(doc: ProcessedDocument, ctx) -> ProcessedDocument:
    """Index chunks into Milvus and update PostgreSQL state."""
    if not doc.chunks:
        logger.warning("  No chunks to index — skipping")
        return doc

    logger.info(f"  {len(doc.chunks)} chunks ready for embedding+indexing")

    doc_id = get_final_doc_id(doc)
    meta = doc.metadata.to_dict()

    # Convert Chunk models back to dicts for existing index_chunks()
    chunk_dicts = [c.to_dict() for c in doc.chunks]

    ctx.index_chunks(chunk_dicts, doc.summary, meta, doc.identity.content_hash)

    # Mark as done if no failed pages
    if not doc.failed_pages:
        ctx.state_manager.update_status(
            doc.identity.rel_path, 'COMPLETED',
            doc_id=doc_id, metadata=meta
        )
        import threading
        with ctx._processed_cache_lock:
            ctx.processed_cache.add(doc.identity.rel_path)
        ctx.mark_file_done(doc.identity.content_hash)

        # Telegram notification
        _send_milestone_notification(ctx)

    return doc


def _send_milestone_notification(ctx):
    """Send Telegram notification every 50 documents."""
    try:
        count, file_list = ctx.state_manager.check_notification_milestone(milestone_step=50)
        if count and file_list:
            from core.notifier import notifier
            import asyncio
            asyncio.run(notifier.notify_milestone(count, file_list))
            logger.info(f"Sent Telegram notification for milestone {count}")
    except Exception as e:
        logger.error(f"Failed to send milestone notification: {e}")

