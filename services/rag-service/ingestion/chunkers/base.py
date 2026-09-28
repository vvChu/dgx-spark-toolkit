from abc import ABC, abstractmethod
import os
import re

# Configurable chunk size cap (bytes). Documents with very long articles
# (e.g. QCVN specs with 20+ page annexes) need this safety cap.
MAX_CHUNK_CHARS = int(os.environ.get("CHUNK_MAX_CHARS", "14500"))


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        """Convert text into parent-child chunks."""
        pass


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
                "source": source,
                "page": page,
                "is_table": False,
                "chunk_type": "child",
                "parent_id": parent_id,
                "hierarchy_path": f"{h_path} -> [Clause]",
                "bbox": bbox,
            })
            buffer = ""

    _flush_child_remainder(
        buffer=buffer,
        children=children,
        doc_id=doc_id,
        source=source,
        page=page,
        parent_id=parent_id,
        h_path=h_path,
        bbox=bbox,
        min_child_length=min_child_length,
    )
    return children


def _flush_child_remainder(
    buffer: str,
    children: list[dict],
    doc_id: str,
    source: str,
    page: int,
    parent_id: str,
    h_path: str,
    bbox: list,
    min_child_length: int,
) -> None:
    """Flush trailing sentence buffer into the last child or a new child."""
    if not buffer.strip():
        return
    if children and len(buffer) < min_child_length // 2:
        prev = children[-1]
        merged = prev["text"] + " " + buffer
        prev["text"] = merged[:MAX_CHUNK_CHARS]
    elif len(buffer) > 100:
        child_text = f"[{doc_id}] {buffer}"[:MAX_CHUNK_CHARS]
        children.append({
            "text": child_text,
            "source": source,
            "page": page,
            "is_table": False,
            "chunk_type": "child",
            "parent_id": parent_id,
            "hierarchy_path": f"{h_path} -> [Clause]",
            "bbox": bbox,
        })


_MARKDOWN_TABLE_RE = re.compile(r'\|[-\s|]+\|')


def _contains_markdown_table(text: str) -> bool:
    """Return True if text contains a pdfplumber-generated markdown table."""
    return bool(_MARKDOWN_TABLE_RE.search(text))


def _detect_inline_table(text: str) -> bool:
    """Detect tabular content even when not formatted as markdown table.

    Looks for header keyword patterns like 'Stt', 'STT', 'Đơn vị', 'ĐVT',
    'Khối lượng' that indicate tabular data in flat text.
    """
    if not text or len(text) < 50:
        return False
    return bool(re.search(
        r'(?:Stt|STT)\s+.+?\s+(?:Đơn\s*vị|ĐVT|Khối\s*lượng|Tỷ\s*lệ|Diện\s*tích)',
        text
    ))


def _merge_small_segments(segments: list[dict], min_block_size: int = 300) -> list[tuple[str, list]]:
    """Merge consecutive small layout segments into combined blocks.

    Returns list of (merged_text, bbox) tuples.
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


# Signer prefix patterns — must be at START of chunk text (after doc_id prefix)
_SIGNER_PREFIX_RE = re.compile(
    r'(?:^\[.*?\]\s*)?'  # Optional [doc_id] prefix
    r'(?:KT\.|TM\.|Ký thay\.?|Q\.)\s*'
    r'(?:THỦ TƯỚNG|CHỦ TỊCH|BỘ TRƯỞNG|CHÍNH PHỦ|GIÁM ĐỐC)',
    re.IGNORECASE
)

# Archive / filing code
_ARCHIVE_RE = re.compile(r'(?:^\[.*?\]\s*)?(?:Lưu\s*:|VT\s*,)', re.IGNORECASE)

# Government header boilerplate patterns
_BOILERPLATE_PREFIX_RE = re.compile(
    r'(?:^\[.*?\]\s*)?'
    r'(?:CỘNG HÒA XÃ HỘI|Độc lập\s*-\s*Tự do|'
    r'Số\s*:\s*[/\s\d]*[A-ZĐ]{2}|'
    r'Hà Nội\s*,\s*ngày|'
    r'Kính gửi\s*:)',
    re.IGNORECASE
)


def _is_noise_chunk(text: str) -> bool:
    """Reject chunks that contain only noise (not substantive legal content)."""
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

    # Short + boilerplate header → noise
    if len(stripped) < 150 and _BOILERPLATE_PREFIX_RE.match(stripped):
        return True

    return False
