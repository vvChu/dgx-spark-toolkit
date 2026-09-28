from .base import (
    ChunkingStrategy,
    MAX_CHUNK_CHARS,
    _contains_markdown_table,
    _merge_small_segments,
    _split_into_children,
)
from .legal import VietLawArticleChunker, VietLawSectionChunker


class LayoutAwareChunker(ChunkingStrategy):
    """Tier 0: Use layout segments + try VietLawArticleChunker on full page text.

    Three-pass strategy:
    1. Try VietLawArticleChunker on combined non-table text
    2. Try VietLawSectionChunker if no articles found
    3. Fall back to merged-segment chunking with child generation
    Table segments always kept as separate parent chunks.
    """
    _law_chunker = VietLawArticleChunker()
    _section_chunker = VietLawSectionChunker()

    def _separate_segments(self, layout: list) -> tuple[list, list, str]:
        table_segments, text_segments = [], []
        for seg in layout:
            label = seg.get("label", "text").lower()
            if label == "table":
                table_segments.append(seg)
            else:
                text_segments.append(seg)
        full_text = "\n".join(
            s.get("text", "").strip() for s in text_segments if s.get("text", "").strip()
        )
        return table_segments, text_segments, full_text

    def _try_legal_chunking(self, full_text: str, source: str, page: int, doc_id: str) -> list[dict]:
        if full_text and len(full_text) > 80:
            law_chunks = self._law_chunker.chunk(full_text, source, page, doc_id)
            if law_chunks:
                return law_chunks
        if full_text and len(full_text) > 200:
            section_chunks = self._section_chunker.chunk(full_text, source, page, doc_id)
            if section_chunks:
                return section_chunks
        return []

    def _chunk_merged_blocks(self, segments: list, source: str, page: int, doc_id: str) -> list[dict]:
        chunks = []
        merged_blocks = _merge_small_segments(segments, min_block_size=300)
        for idx, (content, seg_bbox) in enumerate(merged_blocks):
            if not content.strip():
                continue
            parent_id = f"{source}:{page}:seg_{idx}"
            h_path = f"[{doc_id} > Block {idx} > Page {page}]"
            chunks.append({
                "text": f"[{doc_id}] {content.strip()}"[:MAX_CHUNK_CHARS],
                "source": source, "page": page,
                "is_table": _contains_markdown_table(content),
                "chunk_type": "parent",
                "parent_id": parent_id,
                "hierarchy_path": h_path,
                "bbox": seg_bbox,
            })
            if len(content) > 300:
                chunks.extend(_split_into_children(
                    content, doc_id, source, page, parent_id, h_path, seg_bbox,
                ))
        return chunks

    def _chunk_table_segments(self, table_segments: list, source: str, page: int, doc_id: str) -> list[dict]:
        chunks = []
        for t_idx, seg in enumerate(table_segments):
            content = seg.get("text", "").strip()
            if content:
                chunks.append({
                    "text": f"[{doc_id}] {content}"[:MAX_CHUNK_CHARS],
                    "source": source, "page": page,
                    "is_table": True,
                    "chunk_type": "parent",
                    "parent_id": f"{source}:{page}:table_{t_idx}",
                    "hierarchy_path": f"[{doc_id} > Table > Page {page}]",
                    "bbox": seg.get("bbox", [0, 0, 1000, 1000]),
                })
        return chunks

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        if not layout:
            return []
        table_segs, text_segs, full_page_text = self._separate_segments(layout)
        chunks = self._try_legal_chunking(full_page_text, source, page, doc_id)
        if not chunks:
            chunks = self._chunk_merged_blocks(text_segs, source, page, doc_id)
        chunks.extend(self._chunk_table_segments(table_segs, source, page, doc_id))
        return chunks
