"""Chunkers package for legal and layout-aware document chunking."""

from .base import (
    ChunkingStrategy,
    MAX_CHUNK_CHARS,
    _split_into_children,
    _merge_small_segments,
    _is_noise_chunk,
    _contains_markdown_table,
    _detect_inline_table,
)
from .legal import (
    VietLawArticleChunker,
    VietLawSectionChunker,
    VietLawNumberedSectionChunker,
)
from .layout import LayoutAwareChunker
from .fallback import (
    FormFieldChunker,
    GenericFallbackChunker,
)
from .table import (
    _get_redis_cache,
    _generate_table_summary,
    _is_broken_ocr_table,
    _correct_broken_table_with_vision,
)

__all__ = [
    "ChunkingStrategy",
    "MAX_CHUNK_CHARS",
    "VietLawArticleChunker",
    "VietLawSectionChunker",
    "VietLawNumberedSectionChunker",
    "LayoutAwareChunker",
    "FormFieldChunker",
    "GenericFallbackChunker",
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
