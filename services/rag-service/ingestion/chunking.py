"""Document Chunking Facade.

Maintains 100% backward compatibility while delegating strategy implementations
to the modularized `ingestion.chunkers` package.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
import os

from ingestion.chunkers import (
    ChunkingStrategy,
    MAX_CHUNK_CHARS,
    VietLawArticleChunker,
    VietLawSectionChunker,
    VietLawNumberedSectionChunker,
    LayoutAwareChunker,
    FormFieldChunker,
    GenericFallbackChunker,
    _split_into_children,
    _merge_small_segments,
    _is_noise_chunk,
    _contains_markdown_table,
    _detect_inline_table,
    _get_redis_cache,
    _generate_table_summary,
    _is_broken_ocr_table,
    _correct_broken_table_with_vision,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ChunkingStrategy",
    "MAX_CHUNK_CHARS",
    "VietLawArticleChunker",
    "VietLawSectionChunker",
    "VietLawNumberedSectionChunker",
    "LayoutAwareChunker",
    "FormFieldChunker",
    "GenericFallbackChunker",
    "DocumentChunker",
    "_split_into_children",
    "_merge_small_segments",
    "_is_noise_chunk",
    "_contains_markdown_table",
    "_detect_inline_table",
    "_get_redis_cache",
    "_generate_table_summary",
    "_is_broken_ocr_table",
    "_correct_broken_table_with_vision",
]


class DocumentChunker:
    """Uses strategies sequentially until one succeeds."""

    # Minimum table size (chars) to trigger summarization
    TABLE_SUMMARY_MIN_CHARS = int(os.environ.get("TABLE_SUMMARY_MIN_CHARS", "2000"))
    TABLE_SUMMARY_ENABLED = os.environ.get("TABLE_SUMMARY_ENABLED", "1") == "1"
    TABLE_CORRECT_ENABLED = os.environ.get("TABLE_CORRECT_ENABLED", "1") == "1"

    def __init__(self):
        self.strategies = [
            LayoutAwareChunker(),
            VietLawArticleChunker(),
            VietLawNumberedSectionChunker(),  # Tier 1.5: QCVN numeric sections
            VietLawSectionChunker(),
            FormFieldChunker(),               # Tier 2.5: Form-based documents [P6-FIX]
            GenericFallbackChunker()
        ]

    def chunk_document(self, text: str, source: str, page: int, doc_id: str = "", layout: list = None) -> list[dict]:
        for strategy in self.strategies:
            chunks = strategy.chunk(text, source, page, doc_id, layout=layout)
            if chunks:
                # Filter out noise-only chunks
                filtered = [c for c in chunks if not _is_noise_chunk(c.get("text", ""))]
                result = filtered if filtered else chunks  # Safety: never return empty
                # Auto-correct broken OCR tables using Multimodal Vision
                if self.TABLE_CORRECT_ENABLED:
                    result = self._correct_broken_tables(result, doc_id)
                # Generate summaries for large table chunks
                if self.TABLE_SUMMARY_ENABLED:
                    result = self._add_table_summaries(result, doc_id, source, page)
                # Identity fields (doc_id, doc_number, chunk_id) are set
                # centrally by the pipeline after chunking — not here.
                return result
        return []

    def _correct_broken_tables(self, chunks: list[dict], doc_id: str) -> list[dict]:
        """Iterate over table chunks and apply Multimodal Vision auto-correction for broken OCR tables."""
        for chunk in chunks:
            if chunk.get("is_table"):
                text = chunk.get("text", "")
                if _is_broken_ocr_table(text):
                    img_bytes = chunk.get("image_bytes")
                    corrected = _correct_broken_table_with_vision(text, image_bytes=img_bytes, doc_id=doc_id)
                    if corrected and corrected != text:
                        chunk["text"] = corrected
                        chunk["table_auto_corrected"] = True
        return chunks

    def _add_table_summaries(self, chunks: list[dict], doc_id: str, source: str, page: int) -> list[dict]:
        """Generate concise summary chunks for large tables."""
        augmented = list(chunks)

        table_tasks = []
        for chunk in chunks:
            if not chunk.get("is_table"):
                continue
            text = chunk.get("text", "")
            if len(text) < self.TABLE_SUMMARY_MIN_CHARS:
                continue
            table_tasks.append((chunk, text))

        if not table_tasks:
            return augmented

        def _process_one(item):
            chunk, text = item
            try:
                summary = _generate_table_summary(text, doc_id)
                if summary and len(summary) > 30:
                    return {
                        "text": f"[{doc_id}] [TABLE SUMMARY] {summary}"[:MAX_CHUNK_CHARS],
                        "source": source,
                        "page": page,
                        "is_table": True,
                        "chunk_type": "table_summary",
                        "parent_id": chunk.get("parent_id", f"{source}:{page}:table_sum"),
                        "hierarchy_path": chunk.get("hierarchy_path", "") + " -> [Summary]",
                        "bbox": chunk.get("bbox", [0, 0, 1000, 1000]),
                    }
            except Exception as e:
                logger.debug(f"[TABLE-SUM] Skipped table summary: {e}")
            return None

        # Execute table summarization concurrently across tables
        max_workers = min(5, len(table_tasks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            summaries = list(executor.map(_process_one, table_tasks))

        for sum_chunk in summaries:
            if sum_chunk:
                augmented.append(sum_chunk)

        return augmented
