import re
from .base import (
    ChunkingStrategy,
    MAX_CHUNK_CHARS,
    _contains_markdown_table,
    _split_into_children,
)


class FormFieldChunker(ChunkingStrategy):
    """Tier 2.5: Split form-based documents by numbered fields.

    Designed for Vietnamese government application templates (NOXH, Mẫu đơn)
    where content is structured as numbered form fields.
    """

    _FORM_FIELD_RE = re.compile(
        r'\n\s*(?=\d+\.(?:\d+\.)*\s)'
    )

    def chunk(self, text: str, source: str, page: int, doc_id: str, layout: list = None) -> list[dict]:
        fields = self._FORM_FIELD_RE.split(text)
        if len(fields) < 3:
            return []

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

        parent_text = f"[{doc_id}] {text.strip()}"[:MAX_CHUNK_CHARS]
        chunks.append({
            "text": parent_text, "source": source, "page": page,
            "is_table": False, "chunk_type": "parent",
            "parent_id": parent_id, "hierarchy_path": h_path,
            "bbox": default_bbox
        })

        for idx, field in enumerate(fields):
            field = field.strip()
            if len(field) < 30:
                continue
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
    """Tier 3: Sentence-based chunking."""

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
