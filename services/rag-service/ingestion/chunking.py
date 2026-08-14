from abc import ABC, abstractmethod
import os
import re
from typing import Optional


# Configurable chunk size cap (bytes). Documents with very long articles

# (e.g. QCVN specs with 20+ page annexes) need this safety cap.
MAX_CHUNK_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "14500"))


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        """Convert text into parent-child chunks."""
        pass


class VietLawArticleChunker(ChunkingStrategy):
    """Tier 1: Split Vietnamese legal text by 'Điều X' with Context Inheritance."""

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        chunks = []
        # P3: Expanded pattern to match more Điều forms (with/without space, D/Đ/Đ variants)
        dieu_pattern = r'(?m)^\s*([ĐĐD]i[eề]u\s*\d+[\.:\s])'

        # Detect high-level context (Chapter, Section, etc.) in the text before or between Articles
        context_pattern = r'(?m)^\s*(?:Phần|Chương|Mục)\s+[IVX\d]+.*$'

        dieu_parts = re.split(dieu_pattern, text)
        default_bbox = [0, 0, 1000, 1000]

        if len(dieu_parts) >= 3:
            # Persistent context for this page
            current_context = ""
            header = dieu_parts[0].strip()

            # Find last context line in header
            context_matches = re.findall(context_pattern, header)
            if context_matches:
                current_context = context_matches[-1].strip()

            if header and len(header) > 30:
                # Mark preamble chunks (Căn cứ...) differently for retrieval
                is_preamble = 'Căn cứ' in header or 'căn cứ' in header.lower()
                chunks.append({
                    "text": f"[{doc_id}] {header}",
                    "source": source, "page": page, "is_table": False,
                    "chunk_type": "preamble" if is_preamble else "parent",
                    "parent_id": f"{source}:{page}:header",
                    "hierarchy_path": f"[{doc_id} > Header]",
                    "bbox": default_bbox
                })

            for i in range(1, len(dieu_parts), 2):
                article_num = dieu_parts[i].strip()
                article_content = dieu_parts[i+1].strip() if i+1 < len(dieu_parts) else ""

                # Check for any new context defined *just before* this Article in the previous content block
                # (article_content of the PREVIOUS article or the header)
                # But since we split by Điều, any Chương/Mục appears at the END of the previous text block.

                parent_id = f"{source}:{page}:art_{i//2}"

                # Build Structured Context String
                ctx_prefix = f"[{current_context}] ::: " if current_context else ""
                h_path = f"[{doc_id}] -> [{current_context}] -> [{article_num}]" if current_context else f"[{doc_id}] -> [{article_num}]"

                full_text = f"[{doc_id}] {ctx_prefix}{article_num} {article_content}"[:MAX_CHUNK_CHARS]

                chunks.append({
                    "text": full_text, "source": source, "page": page,
                    "is_table": _contains_markdown_table(article_content) or _detect_inline_table(article_content),
                    "chunk_type": "parent", "parent_id": parent_id,
                    "hierarchy_path": h_path,
                    "bbox": default_bbox
                })

                child_parts = re.split(r'\n\s*(\d+[\.\)]\s)', article_content)
                if len(child_parts) >= 3:
                    for j in range(1, len(child_parts), 2):
                        num = child_parts[j].strip()
                        body = child_parts[j+1].strip() if j+1 < len(child_parts) else ""
                        child_text = f"[{doc_id}] {ctx_prefix}{article_num} > {num} ::: {body}".strip()
                        if len(child_text) > 30:
                            child_text = child_text[:MAX_CHUNK_CHARS]
                            chunks.append({
                                "text": child_text,
                                "source": source, "page": page, "is_table": False,
                                "chunk_type": "child", "parent_id": parent_id,
                                "hierarchy_path": f"{h_path} -> [{num}]",
                                "bbox": default_bbox
                            })
                elif len(article_content) > 300:
                    # [FIX-2] Always generate children via sentence splitting
                    children = _split_into_children(
                        article_content, doc_id, source, page,
                        parent_id, h_path, default_bbox
                    )
                    chunks.extend(children)

                # Update context if a new Chương/Mục appears at the end of this article's content
                # (This happens when the next Điều starts on the same page after a new Chapter header)
                new_ctx_matches = re.findall(context_pattern, article_content)
                if new_ctx_matches:
                    current_context = new_ctx_matches[-1].strip()

            return chunks
        return []


class VietLawSectionChunker(ChunkingStrategy):
    """Tier 2: Split by semantic gaps/paragraphs."""

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        chunks = []
        section_pattern = r'\n\s*\n|\n(?=(?:Mục|Chương|Phần|CHƯƠNG|MỤC|PHẦN)\s)'
        sections = re.split(section_pattern, text)
        default_bbox = [0, 0, 1000, 1000]

        if len(sections) <= 1:
            lines = text.split('\n')
            sections = []
            current = []
            for line in lines:
                stripped = line.strip()
                if not stripped and current:
                    sections.append('\n'.join(current))
                    current = []
                else:
                    current.append(line)
            if current:
                sections.append('\n'.join(current))

        merged_sections = []
        buffer = ""
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            if len(sec) < 80 and buffer:
                buffer += "\n" + sec
            elif len(sec) < 80:
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

        if len(merged_sections) > 1:
            for idx, section in enumerate(merged_sections):
                if len(section.strip()) < 30:
                    continue
                parent_id = f"{source}:{page}:sec_{idx}"
                h_path = f"[{doc_id} > Section {idx}]"
                is_sec_table = _contains_markdown_table(section)

                # Milvus safety cap
                section_text = f"[{doc_id}] {section.strip()}"[:MAX_CHUNK_CHARS]

                chunks.append({
                    "text": section_text, "source": source, "page": page, "is_table": is_sec_table,
                    "chunk_type": "parent", "parent_id": parent_id, "hierarchy_path": h_path,
                    "bbox": default_bbox
                })
                child_pattern = r'\n\s*(?=\d+[\.\)]\s|[a-zđ]\)\s|- )'
                sub_parts = re.split(child_pattern, section)
                if len(sub_parts) > 1:
                    for sp in sub_parts:
                        sp = sp.strip()
                        if len(sp) > 30:
                            # Milvus safety cap
                            child_text = f"[{doc_id}] {sp}"[:MAX_CHUNK_CHARS]
                            chunks.append({
                                "text": child_text, "source": source, "page": page,
                                "is_table": _contains_markdown_table(sp),
                                "chunk_type": "child", "parent_id": parent_id, "hierarchy_path": h_path,
                                "bbox": default_bbox
                            })
            return chunks
        return []


class VietLawNumberedSectionChunker(ChunkingStrategy):
    """Tier 1.5: Split QCVN/standard documents by numeric section headers.

    Handles format: '3.1 Định nghĩa', '3.1.2 Yêu cầu', '4. Phạm vi' etc.
    Sets hierarchy_path with 'Article' label so audit counters score correctly.
    Only activates when document has no 'Điều X' pattern (QCVN/standard format).
    """

    # Match lines like: '3.', '3.1', '3.1.2', '4.1.2.3' followed by uppercase/title word
    _NUM_SECTION_RE = re.compile(
        r'(?m)^\s*(\d+(?:\.\d+)*\.?)\s+([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ][^\n]{3,})'
    )
    _DIEU_RE = re.compile(r'(?m)^\s*[ĐĐD]i[eề]u\s*\d+')

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        # Only activate when no Điều pattern present
        if self._DIEU_RE.search(text):
            return []

        matches = list(self._NUM_SECTION_RE.finditer(text))
        if len(matches) < 2:
            return []

        chunks = []
        default_bbox = [0, 0, 1000, 1000]

        # Add preamble (text before first section)
        preamble = text[:matches[0].start()].strip()
        if preamble and len(preamble) > 30:
            chunks.append({
                "text": f"[{doc_id}] {preamble}"[:MAX_CHUNK_CHARS],
                "source": source, "page": page, "is_table": False,
                "chunk_type": "preamble",
                "parent_id": f"{source}:{page}:preamble",
                "hierarchy_path": f"[{doc_id} > Header]",
                "bbox": default_bbox,
            })

        for idx, match in enumerate(matches):
            sec_num = match.group(1).rstrip('.')
            sec_title = match.group(2).strip()[:80]
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            if not content or len(content) < 30:
                continue

            parent_id = f"{source}:{page}:numsec_{idx}"
            # Use 'Article' label in hierarchy_path so audit counters score correctly
            h_path = f"[{doc_id}] -> [Article {sec_num}] -> [{sec_title[:50]}]"

            parent_text = f"[{doc_id}] {content}"[:MAX_CHUNK_CHARS]
            chunks.append({
                "text": parent_text,
                "source": source, "page": page,
                "is_table": _contains_markdown_table(content) or _detect_inline_table(content),
                "chunk_type": "parent",
                "parent_id": parent_id,
                "hierarchy_path": h_path,
                "bbox": default_bbox,
            })

            # Generate children
            if len(content) > 300:
                children = _split_into_children(
                    content, doc_id, source, page,
                    parent_id, h_path, default_bbox
                )
                chunks.extend(children)

        return chunks


# ---------------------------------------------------------------------------
# Utility: Sentence-based child splitting (shared across strategies)
# ---------------------------------------------------------------------------


_SENTENCE_SPLIT_RE = re.compile(
    r'(?<!\d)\.(?!\d)\s+'
    r'|\n(?=[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ])'
    r'|\n(?=\d+[\.\)]\s)'
    r'|\n(?=[a-zđ]\)\s)',
    re.UNICODE,
)


def _split_into_children(text: str, doc_id: str, source: str, page: int,
                         parent_id: str, h_path: str, bbox: list,
                         min_child_length: int = 300) -> list[dict]:
    """Split text into semantically meaningful children using sentence boundaries.

    Unlike the old sliding window approach, each child carries independent meaning.
    Short sentences are merged together until they reach `min_child_length`.
    [QF-6] Increased from 200→300, then to 400, now back to 300 for better child/parent ratio.
    [P4] Raised threshold to reduce noise children < 100 chars.
    """
    parts = _SENTENCE_SPLIT_RE.split(text)
    children = []
    buffer = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        buffer = (buffer + " " + part).strip() if buffer else part
        if len(buffer) >= min_child_length:
            child_text = f"[{doc_id}] {buffer}"[:MAX_CHUNK_CHARS]
            children.append({
                "text": child_text,
                "source": source, "page": page, "is_table": False,
                "chunk_type": "child", "parent_id": parent_id,
                "hierarchy_path": h_path,
                "bbox": bbox,
            })
            buffer = ""

    # Flush remainder — attach to last child or create a new one
    if buffer.strip():
        if children and len(buffer) < min_child_length // 2:
            # Too short to stand alone — merge into last child
            prev = children[-1]
            merged = prev["text"] + " " + buffer
            prev["text"] = merged[:MAX_CHUNK_CHARS]
        elif len(buffer) > 100:
            # [P6-100] Standalone minimum 200→100 for higher ratio
            child_text = f"[{doc_id}] {buffer}"[:MAX_CHUNK_CHARS]
            children.append({
                "text": child_text,
                "source": source, "page": page, "is_table": False,
                "chunk_type": "child", "parent_id": parent_id,
                "hierarchy_path": h_path,
                "bbox": bbox,
            })

    return children


# ---------------------------------------------------------------------------
# Utility: Detect markdown tables injected by TABLE-FIX (pdfplumber)
# ---------------------------------------------------------------------------

_MARKDOWN_TABLE_RE = re.compile(r'\|[-\s|]+\|')


def _contains_markdown_table(text: str) -> bool:
    """Return True if text contains a pdfplumber-generated markdown table."""
    return bool(_MARKDOWN_TABLE_RE.search(text))


def _detect_inline_table(text: str) -> bool:
    """Detect tabular content even when not formatted as markdown table.

    Looks for header keyword patterns like 'Stt', 'STT', 'Đơn vị', 'ĐVT',
    'Khối lượng' that indicate tabular data in flat text.
    [QF-7] Improves is_table detection for VietLawArticleChunker.
    """
    if not text or len(text) < 50:
        return False
    return bool(re.search(
        r'(?:Stt|STT)\s+.+?\s+(?:Đơn\s*vị|ĐVT|Khối\s*lượng|Tỷ\s*lệ|Diện\s*tích)',
        text
    ))


# ---------------------------------------------------------------------------
# Utility: Merge small layout segments into larger blocks
# ---------------------------------------------------------------------------

def _merge_small_segments(segments: list[dict], min_block_size: int = 300) -> list[tuple[str, list]]:
    """Merge consecutive small layout segments into combined blocks.

    Returns list of (merged_text, bbox) tuples.
    [FIX-1] Prevents creation of many tiny parent chunks from layout segments.
    """
    blocks: list[tuple[str, list]] = []
    buffer = ""
    buffer_bbox = [0, 0, 1000, 1000]

    for seg in segments:
        content = seg.get("text", "").strip()
        seg_bbox = seg.get("bbox", [0, 0, 1000, 1000])
        if not content:
            continue

        if not buffer:
            buffer = content
            buffer_bbox = seg_bbox
        elif len(buffer) < min_block_size:
            buffer += "\n" + content
        else:
            blocks.append((buffer, buffer_bbox))
            buffer = content
            buffer_bbox = seg_bbox

    if buffer:
        # Try to merge short trailing buffer into last block
        if blocks and len(buffer) < min_block_size // 2:
            prev_text, prev_bbox = blocks[-1]
            blocks[-1] = (prev_text + "\n" + buffer, prev_bbox)
        else:
            blocks.append((buffer, buffer_bbox))

    return blocks


class FormFieldChunker(ChunkingStrategy):
    """Tier 2.5: Split form-based documents by numbered fields.

    Designed for Vietnamese government application templates (NOXH, Mẫu đơn)
    where content is structured as numbered form fields:
        1. Kính gửi: ...
        2. Họ và tên: ...
        10. Thực trạng về nhà ở: ...

    [P6-FIX] Improves child/parent ratio for form-based documents by using
    each numbered field as a natural child chunk boundary.
    """

    # Match numbered form fields: "1. ", "2. ", "10. ", "11.2. "
    _FORM_FIELD_RE = re.compile(
        r'\n\s*(?=\d+\.(?:\d+\.)*\s)'
    )

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        # Only activate if text has numbered form fields
        fields = self._FORM_FIELD_RE.split(text)
        if len(fields) < 3:  # Need at least 3 numbered fields to be a form
            return []

        # Extra check: at least some fields should have form-like patterns
        form_indicators = sum(
            1 for f in fields
            if re.search(r'(?:Kính gửi|Họ và\s*tên|Căn cước|Nghề nghiệp|Nơi ở|Đăng ký|Thuộc đối tượng|cam đoan|xác nhận|□)', f)
        )
        if form_indicators < 2:
            return []

        chunks = []
        default_bbox = [0, 0, 1000, 1000]
        parent_id = f"{source}:{page}:form"
        h_path = f"[{doc_id} > Form > Page {page}]"

        # Create parent chunk from full text
        parent_text = f"[{doc_id}] {text.strip()}"[:MAX_CHUNK_CHARS]
        chunks.append({
            "text": parent_text, "source": source, "page": page,
            "is_table": False, "chunk_type": "parent",
            "parent_id": parent_id, "hierarchy_path": h_path,
            "bbox": default_bbox
        })

        # Create child chunks from numbered fields
        for idx, field in enumerate(fields):
            field = field.strip()
            if len(field) < 30:
                continue
            # Extract field number for hierarchy
            field_num_match = re.match(r'(\d+\.(?:\d+\.)*)', field)
            field_label = field_num_match.group(1).rstrip('.') if field_num_match else str(idx)

            child_text = f"[{doc_id}] {field}"[:MAX_CHUNK_CHARS]
            chunks.append({
                "text": child_text, "source": source, "page": page,
                "is_table": False, "chunk_type": "child",
                "parent_id": parent_id,
                "hierarchy_path": f"{h_path} -> [Field {field_label}]",
                "bbox": default_bbox
            })

        return chunks


class GenericFallbackChunker(ChunkingStrategy):
    """Tier 3: Sentence-based chunking (replaced fixed sliding window)."""

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        chunks = []
        text = text.strip()
        h_path = f"[{doc_id} > Page {page}]"
        default_bbox = [0, 0, 1000, 1000]
        has_table = _contains_markdown_table(text)

        if len(text) > 300:
            parent_id = f"{source}:{page}:full"
            parent_text = f"[{doc_id}] {text}"[:MAX_CHUNK_CHARS]
            chunks.append({
                "text": parent_text, "source": source, "page": page, "is_table": has_table,
                "chunk_type": "parent", "parent_id": parent_id, "hierarchy_path": h_path,
                "bbox": default_bbox
            })
            # [P6-100] Use aggressive thresholds for higher ratio
            child_min = 100 if len(text) < 800 else 200
            children = _split_into_children(
                text, doc_id, source, page, parent_id, h_path, default_bbox,
                min_child_length=child_min
            )
            chunks.extend(children)
            return chunks

        if len(text) > 30:
            chunks.append({
                "text": f"[{doc_id}] {text}", "source": source, "page": page, "is_table": has_table,
                "chunk_type": "parent", "parent_id": f"{source}:{page}:short", "hierarchy_path": h_path,
                "bbox": default_bbox
            })
        return chunks


class LayoutAwareChunker(ChunkingStrategy):
    """Tier 0: Use layout segments + try VietLawArticleChunker on full page text.

    Three-pass strategy:
    1. Try VietLawArticleChunker on combined non-table text
    2. [FIX-4] Try VietLawSectionChunker if no articles found
    3. [FIX-1] Fall back to merged-segment chunking with child generation
    Table segments always kept as separate parent chunks.
    """
    _law_chunker = VietLawArticleChunker()
    _section_chunker = VietLawSectionChunker()

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        if not layout:
            return []

        # Separate table and non-table segments
        table_segments = []
        text_segments = []
        for seg in layout:
            label = seg.get("label", "text").lower()
            if label == "table":
                table_segments.append(seg)
            else:
                text_segments.append(seg)

        # Assemble full page text from non-table segments
        full_page_text = "\n".join(
            seg.get("text", "").strip()
            for seg in text_segments
            if seg.get("text", "").strip()
        )

        chunks = []

        # Pass 1: Try legal structure chunking on combined text
        # [P3] Always try Article chunker first even with layout segments
        if full_page_text and len(full_page_text) > 80:
            law_chunks = self._law_chunker.chunk(
                full_page_text, source, page, doc_id
            )
            if law_chunks:
                chunks.extend(law_chunks)

        # Pass 1b: [FIX-4] Try section-based chunking before per-segment
        if not chunks and full_page_text and len(full_page_text) > 200:
            section_chunks = self._section_chunker.chunk(
                full_page_text, source, page, doc_id
            )
            if section_chunks:
                chunks.extend(section_chunks)

        # Pass 2: [FIX-1] Merge small segments into larger blocks
        if not chunks:
            merged_blocks = _merge_small_segments(text_segments, min_block_size=300)
            for idx, (content, seg_bbox) in enumerate(merged_blocks):
                if not content.strip():
                    continue

                parent_id = f"{source}:{page}:seg_{idx}"
                h_path = f"[{doc_id} > Block {idx} > Page {page}]"
                has_table = _contains_markdown_table(content)

                parent_text = f"[{doc_id}] {content.strip()}"[:MAX_CHUNK_CHARS]
                chunks.append({
                    "text": parent_text,
                    "source": source, "page": page,
                    "is_table": has_table,
                    "chunk_type": "parent",
                    "parent_id": parent_id,
                    "hierarchy_path": h_path,
                    "bbox": seg_bbox,
                })

                # [FIX-2] Lower threshold from 400→300 for child generation
                if len(content) > 300:
                    children = _split_into_children(
                        content, doc_id, source, page,
                        parent_id, h_path, seg_bbox,
                    )
                    chunks.extend(children)

        # Always add table segments as separate parent chunks
        for t_idx, seg in enumerate(table_segments):
            content = seg.get("text", "").strip()
            seg_bbox = seg.get("bbox", [0, 0, 1000, 1000])
            if content:
                chunks.append({
                    "text": f"[{doc_id}] {content}"[:MAX_CHUNK_CHARS],
                    "source": source, "page": page,
                    "is_table": True,
                    "chunk_type": "parent",
                    "parent_id": f"{source}:{page}:table_{t_idx}",
                    "hierarchy_path": f"[{doc_id} > Table > Page {page}]",
                    "bbox": seg_bbox,
                })

        return chunks

# ---------------------------------------------------------------------------
# Chunk Quality Filter — reject noise-only chunks
# ---------------------------------------------------------------------------


# Signer prefix patterns — must be at START of chunk text (after doc_id prefix)
_SIGNER_PREFIX_RE = re.compile(
    r'(?:^\[.*?\]\s*)?'  # Optional [doc_id] prefix
    r'(?:KT\.|TM\.|Ký thay\.?|Q\.)\s*'
    r'(?:THỦ TƯỚNG|CHỦ TỊCH|BỘ TRƯỞNG|CHÍNH PHỦ|GIÁM ĐỐC)',
    re.IGNORECASE
)

# Archive / filing code
_ARCHIVE_RE = re.compile(r'(?:^\[.*?\]\s*)?(?:Lưu\s*:|VT\s*,)', re.IGNORECASE)

# [FIX-3] Government header boilerplate patterns
_BOILERPLATE_PREFIX_RE = re.compile(
    r'(?:^\[.*?\]\s*)?'
    r'(?:CỘNG HÒA XÃ HỘI|Độc lập\s*-\s*Tự do|'
    r'Số\s*:\s*[/\s\d]*[A-ZĐ]{2}|'
    r'Hà Nội\s*,\s*ngày|'
    r'Kính gửi\s*:)',
    re.IGNORECASE
)


def _is_noise_chunk(text: str) -> bool:
    """Reject chunks that contain only noise (not substantive legal content).

    SAFETY: Only rejects when BOTH conditions are met:
    1. Matches a known noise pattern (signer prefix, archive code, boilerplate)
    2. Text is short enough to be ONLY noise

    This prevents false positives like "Thủ tướng Chính phủ ban hành..."
    which is body content that happens to mention 'Thủ tướng'.
    """
    stripped = text.strip()

    # Too short to be meaningful content
    if len(stripped) < 40:
        return True

    # Short + signer prefix → noise
    if len(stripped) < 120 and _SIGNER_PREFIX_RE.match(stripped):
        return True

    # Short + archive code → noise
    if len(stripped) < 80 and _ARCHIVE_RE.match(stripped):
        return True

    # [FIX-3] Short + boilerplate header → noise
    if len(stripped) < 150 and _BOILERPLATE_PREFIX_RE.match(stripped):
        return True

    return False


def _is_broken_ocr_table(text: str) -> bool:
    """Detect if a table text has broken OCR structure (misaligned columns, missing pipes, noise)."""
    if not text:
        return False
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    pipe_count = text.count("|")
    if pipe_count > 2:
        pipe_counts = [line.count("|") for line in lines]
        if max(pipe_counts) != min(pipe_counts) and min(pipe_counts) == 0:
            return True
    if re.search(r'\.{4,}|\s{5,}\d+', text):
        return True
    return False


def _correct_broken_table_with_vision(table_text: str, image_bytes: Optional[bytes] = None, doc_id: str = "") -> str:
    """Auto-correct broken OCR tables using Multimodal Vision (Gemini 3.5 Flash Lite)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from core.ai_gateway_client import AIGatewayClient
        client = AIGatewayClient()

        prompt = (
            "Dưới đây là nội dung một bảng biểu trong văn bản pháp luật bị lỗi OCR (mất cột, vỡ cấu trúc dòng).\n"
            "Hãy dựng lại bảng này dưới dạng Markdown Table chuẩn hóa, giữ nguyên toàn bộ số liệu và văn bản chính xác.\n"
            "Chỉ trả về Markdown Table, không kèm theo văn bản dẫn dắt khác.\n\n"
            f"Dữ liệu bảng thô:\n{table_text[:3500]}"
        )

        if image_bytes:
            reconstructed = client.complete_vision_sync(
                image_bytes,
                prompt=prompt,
                model="gemini-3.5-flash-lite",
            )
        else:
            reconstructed = client.complete_sync(
                [{"role": "user", "content": prompt}],
                model="gemini-3.5-flash-lite",
                model_chain=["gemini-3.5-flash-lite", "openai/gemma-4-26b-a4b-it", "rag-core"],
            )

        if reconstructed and "|" in reconstructed and len(reconstructed) > 20:
            return reconstructed.strip()
    except Exception as e:
        logger.debug(f"[TABLE-VISION-CORRECT] Vision table correction skipped: {e}")

    return table_text


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

        """Generate concise summary chunks for large tables.

        For each table chunk exceeding TABLE_SUMMARY_MIN_CHARS, creates an
        additional 'table_summary' chunk that captures the table's purpose,
        columns, and key data points. This improves RAG recall for general
        questions about tables without requiring full table retrieval.

        Summary generation uses ThreadPoolExecutor for concurrent batch calls
        and Redis caching for MD5-hashed table contents.
        """
        import logging
        from concurrent.futures import ThreadPoolExecutor

        logger = logging.getLogger(__name__)
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


_redis_table_cache = None


def _get_redis_cache():
    global _redis_table_cache
    if _redis_table_cache is not None:
        return _redis_table_cache
    try:
        import os
        import redis
        url = os.environ.get("REDIS_URL", "redis://litellm-redis:6379/1")
        _redis_table_cache = redis.from_url(url, decode_responses=True, socket_timeout=2.0)
        return _redis_table_cache
    except Exception:
        return None


def _generate_table_summary(table_text: str, doc_id: str) -> str:
    """Generate a concise summary of a large table via LLM with Redis caching.

    Uses the AI Gateway (Gemini Flash) for fast, cost-free summarization.
    Falls back gracefully if the gateway is unavailable.

    Returns:
        Summary string, or empty string on failure.
    """
    import os
    import logging
    import hashlib
    logger = logging.getLogger(__name__)

    # Check Redis cache first
    content_hash = hashlib.md5(table_text[:3000].encode("utf-8")).hexdigest()
    cache_key = f"cache:table_summary:{content_hash}"
    r = _get_redis_cache()
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                logger.debug(f"[TABLE-SUM] Redis cache hit for table hash {content_hash[:8]}")
                return cached
        except Exception:
            pass

    model = os.environ.get("TABLE_SUMMARY_MODEL", "gemini-flash")
    prompt = (
        "Tóm tắt bảng dữ liệu sau bằng tiếng Việt. "
        "Nêu rõ: (1) Mục đích của bảng, (2) Tên các cột chính, "
        "(3) Số dòng/mục dữ liệu, (4) Các giá trị nổi bật. "
        "Trả lời ngắn gọn trong 2-3 câu.\n\n"
        f"Bảng:\n{table_text[:3000]}"  # Cap input to avoid token overflow
    )

    from core.ai_gateway_client import get_ai_gateway_client
    client = get_ai_gateway_client()
    try:
        content = client.complete_sync(
            [{"role": "user", "content": prompt}],
            model=model,
            max_tokens=200,
            temperature=0.1,
        )
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if r and content:
            try:
                r.setex(cache_key, 604800, content)
            except Exception:
                pass
        return content
    except Exception as e:
        logger.debug(f"[TABLE-SUM] LLM call failed: {e}")
        return ""
