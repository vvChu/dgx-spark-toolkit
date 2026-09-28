import re
from typing import Any
from .base import (
    ChunkingStrategy,
    MAX_CHUNK_CHARS,
    _contains_markdown_table,
    _detect_inline_table,
    _split_into_children,
)


class VietLawArticleChunker(ChunkingStrategy):
    """Tier 1: Split Vietnamese legal text by 'Điều X' with Context Inheritance."""

    DIEU_PATTERN = r'(?m)^\s*([ĐĐD]i[eề]u\s*\d+[\.:\s])'
    CONTEXT_PATTERN = r'(?m)^\s*(?:Phần|Chương|Mục)\s+[IVX\d]+.*$'

    def _build_article_children(
        self, article_content: str, doc_id: str, source: str, page: int,
        parent_id: str, h_path: str, ctx_prefix: str, article_num: str, bbox: list,
    ) -> list[dict]:
        chunks = []
        child_parts = re.split(r'\n\s*(\d+[\.\)]\s)', article_content)
        if len(child_parts) >= 3:
            for j in range(1, len(child_parts), 2):
                num = child_parts[j].strip()
                body = child_parts[j+1].strip() if j+1 < len(child_parts) else ""
                child_text = f"[{doc_id}] {ctx_prefix}{article_num} > {num} ::: {body}".strip()
                if len(child_text) > 30:
                    chunks.append({
                        "text": child_text[:MAX_CHUNK_CHARS],
                        "source": source, "page": page, "is_table": False,
                        "chunk_type": "child", "parent_id": parent_id,
                        "hierarchy_path": f"{h_path} -> [{num}]",
                        "bbox": bbox,
                    })
        elif len(article_content) > 300:
            chunks.extend(_split_into_children(
                article_content, doc_id, source, page, parent_id, h_path, bbox,
            ))
        return chunks

    def _process_single_article(
        self, article_num: str, article_content: str, idx: int,
        doc_id: str, source: str, page: int, current_context: str, bbox: list,
    ) -> list[dict]:
        parent_id = f"{source}:{page}:art_{idx}"
        ctx_prefix = f"[{current_context}] ::: " if current_context else ""
        h_path = f"[{doc_id}] -> [{current_context}] -> [{article_num}]" if current_context else f"[{doc_id}] -> [{article_num}]"
        is_table = _contains_markdown_table(article_content) or _detect_inline_table(article_content)

        chunks = [{
            "text": f"[{doc_id}] {ctx_prefix}{article_num} {article_content}"[:MAX_CHUNK_CHARS],
            "source": source, "page": page, "is_table": is_table,
            "chunk_type": "parent", "parent_id": parent_id,
            "hierarchy_path": h_path, "bbox": bbox,
        }]
        chunks.extend(self._build_article_children(
            article_content, doc_id, source, page, parent_id, h_path, ctx_prefix, article_num, bbox,
        ))
        return chunks

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        dieu_parts = re.split(self.DIEU_PATTERN, text)
        if len(dieu_parts) < 3:
            return []

        chunks, default_bbox = [], [0, 0, 1000, 1000]
        header = dieu_parts[0].strip()
        ctx_matches = re.findall(self.CONTEXT_PATTERN, header)
        current_context = ctx_matches[-1].strip() if ctx_matches else ""

        if header and len(header) > 30:
            is_preamble = 'Căn cứ' in header or 'căn cứ' in header.lower()
            chunks.append({
                "text": f"[{doc_id}] {header}",
                "source": source, "page": page, "is_table": False,
                "chunk_type": "preamble" if is_preamble else "parent",
                "parent_id": f"{source}:{page}:header",
                "hierarchy_path": f"[{doc_id} > Header]",
                "bbox": default_bbox,
            })

        for i in range(1, len(dieu_parts), 2):
            article_num = dieu_parts[i].strip()
            article_content = dieu_parts[i+1].strip() if i+1 < len(dieu_parts) else ""
            chunks.extend(self._process_single_article(
                article_num, article_content, i // 2, doc_id, source, page, current_context, default_bbox,
            ))
            new_ctx = re.findall(self.CONTEXT_PATTERN, article_content)
            if new_ctx:
                current_context = new_ctx[-1].strip()

        return chunks


class VietLawSectionChunker(ChunkingStrategy):
    """Tier 2: Split by semantic gaps/paragraphs."""

    def _split_into_raw_sections(self, text: str) -> list[str]:
        section_pattern = r'\n\s*\n|\n(?=(?:Mục|Chương|Phần|CHƯƠNG|MỤC|PHẦN)\s)'
        sections = re.split(section_pattern, text)
        if len(sections) > 1:
            return sections
        sections, current = [], []
        for line in text.split('\n'):
            if not line.strip() and current:
                sections.append('\n'.join(current))
                current = []
            else:
                current.append(line)
        if current:
            sections.append('\n'.join(current))
        return sections

    def _merge_short_sections(self, sections: list[str]) -> list[str]:
        merged_sections, buffer = [], ""
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            if len(sec) < 80:
                buffer = sec
            else:
                if buffer:
                    merged_sections.append(buffer + "\n" + sec)
                    buffer = ""
                else:
                    merged_sections.append(sec)
        if buffer:
            if merged_sections:
                merged_sections[-1] += "\n" + buffer
            else:
                merged_sections.append(buffer)
        return merged_sections

    def _build_section_chunks(
        self, section: str, idx: int, source: str, page: int, doc_id: str, bbox: list,
    ) -> list[dict]:
        parent_id = f"{source}:{page}:sec_{idx}"
        h_path = f"[{doc_id} > Section {idx}]"
        chunks = [{
            "text": f"[{doc_id}] {section.strip()}"[:MAX_CHUNK_CHARS],
            "source": source, "page": page,
            "is_table": _contains_markdown_table(section),
            "chunk_type": "parent", "parent_id": parent_id,
            "hierarchy_path": h_path, "bbox": bbox,
        }]
        child_pattern = r'\n\s*(?=\d+[\.\)]\s|[a-zđ]\)\s|- )'
        sub_parts = re.split(child_pattern, section)
        if len(sub_parts) > 1:
            for sp in sub_parts:
                sp = sp.strip()
                if len(sp) > 30:
                    chunks.append({
                        "text": f"[{doc_id}] {sp}"[:MAX_CHUNK_CHARS],
                        "source": source, "page": page,
                        "is_table": _contains_markdown_table(sp),
                        "chunk_type": "child", "parent_id": parent_id,
                        "hierarchy_path": h_path, "bbox": bbox,
                    })
        return chunks

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        raw_sections = self._split_into_raw_sections(text)
        merged = self._merge_short_sections(raw_sections)
        if len(merged) <= 1:
            return []
        chunks, default_bbox = [], [0, 0, 1000, 1000]
        for idx, sec in enumerate(merged):
            if len(sec.strip()) >= 30:
                chunks.extend(self._build_section_chunks(sec, idx, source, page, doc_id, default_bbox))
        return chunks


class VietLawNumberedSectionChunker(ChunkingStrategy):
    """Tier 1.5: Split QCVN/standard documents by numeric section headers."""

    _NUM_SECTION_RE = re.compile(
        r'(?m)^\s*(\d+(?:\.\d+)*\.?)\s+([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ][^\n]{3,})'
    )
    _DIEU_RE = re.compile(r'(?m)^\s*[ĐĐD]i[eề]u\s*\d+')

    def _build_numbered_chunk(
        self, match: Any, next_start: int, text: str, idx: int,
        doc_id: str, source: str, page: int, bbox: list,
    ) -> list[dict]:
        sec_num = match.group(1).rstrip('.')
        sec_title = match.group(2).strip()[:80]
        content = text[match.start():next_start].strip()
        if not content or len(content) < 30:
            return []

        parent_id = f"{source}:{page}:numsec_{idx}"
        h_path = f"[{doc_id}] -> [Article {sec_num}] -> [{sec_title[:50]}]"
        chunks = [{
            "text": f"[{doc_id}] {content}"[:MAX_CHUNK_CHARS],
            "source": source, "page": page,
            "is_table": _contains_markdown_table(content) or _detect_inline_table(content),
            "chunk_type": "parent", "parent_id": parent_id,
            "hierarchy_path": h_path, "bbox": bbox,
        }]
        if len(content) > 300:
            chunks.extend(_split_into_children(
                content, doc_id, source, page, parent_id, h_path, bbox,
            ))
        return chunks

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        if self._DIEU_RE.search(text):
            return []
        matches = list(self._NUM_SECTION_RE.finditer(text))
        if len(matches) < 2:
            return []

        chunks, default_bbox = [], [0, 0, 1000, 1000]
        preamble = text[:matches[0].start()].strip()
        if preamble and len(preamble) > 30:
            chunks.append({
                "text": f"[{doc_id}] {preamble}"[:MAX_CHUNK_CHARS],
                "source": source, "page": page, "is_table": False,
                "chunk_type": "preamble", "parent_id": f"{source}:{page}:preamble",
                "hierarchy_path": f"[{doc_id} > Header]", "bbox": default_bbox,
            })

        for idx, match in enumerate(matches):
            next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            chunks.extend(self._build_numbered_chunk(
                match, next_start, text, idx, doc_id, source, page, default_bbox,
            ))
        return chunks
