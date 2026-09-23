from dataclasses import asdict, is_dataclass
import glob
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional

from ingestion.text_normalizer import (
    detect_garbled_table,
    fix_common_ocr_typos,
    fix_generic_stuck_words,
    fix_stuck_vietnamese_words,
    fix_table_gfm_v2,
    fix_vietnamese_syllable_boundaries,
    normalize_chunk_text,
    normalize_ocr_spacing,
    strip_ai_monologue,
    strip_digital_signature,
    strip_document_boilerplate,
    strip_noi_nhan_block,
    strip_random_emojis,
)

logger = logging.getLogger(__name__)

# QCVN pattern: QCVN_01_2021_BXD → QCVN 01:2021/BXD
# Legal document filename patterns for doc_number extraction
_QCVN_FILENAME_RE = re.compile(
    r"QCVN[_\s-]?(\d+)[_\s-](\d{4})[_\s-]([A-Za-z]+)"
)

# Luat doc pattern: Luat_50-2014-QH13 → 50/2014/QH13
_LUAT_FILENAME_RE = re.compile(
    r"Luat_(\d+)[-_](\d{4})[-_]QH(\d+)", re.IGNORECASE
)

# Standard doc pattern: TT01-2023-BTP → 01/2023/TT-BTP, QD08-2023-TTg → 08/2023/QĐ-TTg
_DOC_NUM_FILENAME_RE = re.compile(
    r"([A-Z]{2,4})(\d+)[-_/](\d{4})[-_/]([A-Za-z]+)"
)

# Simpler pattern: QD08-TTg → 08/QĐ-TTg
_DOC_NUM_SIMPLE_RE = re.compile(
    r"([A-Z]{2,4})(\d+)[-_/]([A-Za-z]+)"
)

_DOC_TYPE_MAP = {
    "QD": "QĐ",
    "ND": "NĐ",
    "CD": "CĐ",
}


def extract_doc_number_from_path(filepath: str) -> Optional[str]:
    """[P4] Extract doc_number from filename/path when missing from content.

    Handles QCVN patterns and standard Vietnamese legal document IDs.
    """
    if not filepath:
        return None
    basename = re.sub(r"(\.json|\.md|\.bak)+$", "", os.path.basename(filepath))

    # QCVN special handling
    m = _QCVN_FILENAME_RE.search(basename)
    if m:
        return f"QCVN {m.group(1)}:{m.group(2)}/{m.group(3)}"

    # Luat pattern: Luat_50-2014-QH13... -> 50/2014/QH13
    m = _LUAT_FILENAME_RE.search(basename)
    if m:
        return f"{m.group(1)}/{m.group(2)}/QH{m.group(3)}"

    # Standard full pattern: TT01-2023-BTP → 01/2023/TT-BTP, QD08-2023-TTg → 08/2023/QĐ-TTg
    m = _DOC_NUM_FILENAME_RE.search(basename)
    if m:
        doc_type = _DOC_TYPE_MAP.get(m.group(1), m.group(1))
        return f"{m.group(2)}/{m.group(3)}/{doc_type}-{m.group(4)}"

    # Simple pattern: QD08-TTg → 08/QĐ-TTg
    m = _DOC_NUM_SIMPLE_RE.search(basename)
    if m:
        doc_type = _DOC_TYPE_MAP.get(m.group(1), m.group(1))
        return f"{m.group(2)}/{doc_type}-{m.group(3)}"

    return None


class DataExporter:
    def __init__(self, export_dir: Optional[str] = None):
        self.export_dir = export_dir or os.environ.get("EXPORT_DIR", "/app/exports")
        self.json_dir = os.path.join(self.export_dir, "json")
        self.md_dir = os.path.join(self.export_dir, "markdown")

        # Create directories if possible
        try:
            os.makedirs(self.json_dir, exist_ok=True)
            os.makedirs(self.md_dir, exist_ok=True)
            logger.info(f"Initialized DataExporter at {self.export_dir}")
        except Exception as e:
            logger.debug(f"Could not create export directories ({self.export_dir}): {e}")

    def export(
        self,
        rel_path: str,
        doc_id: str,
        meta: Dict[str, Any],
        summary: str,
        chunks: List[Dict[str, Any]],
    ) -> tuple[Optional[Path], Optional[Path]]:
        """Export processed document data to JSON and Markdown."""
        try:
            # Sanitize doc_id for filename (replace / and other chars)
            safe_filename = doc_id.replace('/', '_').replace('\\', '_').replace(':', '_').replace(' ', '_').lstrip('.')

            # 1. Export JSON
            json_path = os.path.join(self.json_dir, f"{safe_filename}.json")
            json_data = {
                "doc_id": doc_id,
                "original_path": rel_path,
                "metadata": meta,
                "summary": summary,
                "chunks": chunks
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)

            # 2. Export Markdown
            md_path = os.path.join(self.md_dir, f"{safe_filename}.md")
            md_content = self._generate_markdown(rel_path, doc_id, meta, summary, chunks)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            logger.info(f"Successfully exported data for {doc_id} to {self.export_dir}")
            return Path(json_path), Path(md_path)
        except Exception as e:
            logger.error(f"Failed to export data for {doc_id}: {e}")
            return None, None

    def export_document(self, doc: Any) -> tuple[Optional[Path], Optional[Path]]:
        """Wrapper mapping ProcessedDocument or dict-like doc to export method."""
        rel_path = getattr(doc, "file_path", None) or getattr(doc, "source_path", None) or "unknown"

        # Resolve doc_id from identity (dataclass or dict) or doc_id attribute
        doc_id = "unknown"
        identity = getattr(doc, "identity", None)
        if identity is not None:
            if hasattr(identity, "doc_id"):
                doc_id = getattr(identity, "doc_id", "unknown") or "unknown"
            elif isinstance(identity, dict):
                doc_id = identity.get("doc_id", "unknown") or "unknown"
        if doc_id == "unknown":
            doc_id = getattr(doc, "doc_id", "unknown") or "unknown"

        # Resolve metadata dictionary safely
        raw_meta = getattr(doc, "metadata", None)
        if raw_meta is not None and hasattr(raw_meta, "to_dict"):
            meta = raw_meta.to_dict()
        elif isinstance(raw_meta, dict):
            meta = raw_meta
        elif is_dataclass(raw_meta) and not isinstance(raw_meta, type):
            meta = asdict(raw_meta)
        else:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}

        summary = getattr(doc, "summary", "") or ""

        # Resolve chunks list safely
        raw_chunks = getattr(doc, "chunks", None) or []
        chunks = []
        for c in raw_chunks:
            if hasattr(c, "to_dict"):
                chunks.append(c.to_dict())
            elif is_dataclass(c) and not isinstance(c, type):
                chunks.append(asdict(c))
            elif isinstance(c, dict):
                chunks.append(c)
            elif hasattr(c, "__dict__"):
                chunks.append(vars(c))
            else:
                chunks.append(c)

        return self.export(rel_path=rel_path, doc_id=doc_id, meta=meta, summary=summary, chunks=chunks)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_heading_from_hierarchy(hierarchy_path: str, doc_id: str) -> str | None:
        """Try to derive a meaningful heading from the chunk's hierarchy_path.

        Examples of hierarchy_path values produced by the chunker:
            "[doc_id] -> [Chương I …] -> [Điều 1. …]"
            "[doc_id > Section 3]"
            "[doc_id > Table > Page 5]"
            "[doc_id > Header]"
        """
        if not hierarchy_path:
            return None

        # Extract the last segment after the final " -> " or " > "
        parts = re.split(r'\s*(?:->|>)\s*', hierarchy_path)
        if not parts:
            return None

        last = parts[-1].strip().strip("[]")
        # Skip noise-only segments
        if not last or last == doc_id or last.lower() in ("header", "table"):
            return None

        # [P2] Handle numbered section format from VietLawNumberedSectionChunker
        # e.g. "Article 3.2.1" -> "#### 3.2.1" or "Article 8.2.1.2" -> "#### 8.2.1.2"
        article_match = re.match(r'Article\s+(\d+(?:\.\d+)*)', last, re.IGNORECASE)
        if article_match:
            section_num = article_match.group(1)
            depth = section_num.count('.')
            hashes = '####' if depth >= 1 else '###'
            return f"{hashes} {section_num}"  # Return with hashes prefix for caller to use directly

        # If it looks like a legal marker, extract ONLY the marker part
        # Prevent body text from leaking into the heading
        legal_match = re.match(
            r'((?:[ĐÐ]iều\s+\d+\.?[^.]*?(?:\.\s+\S+(?:\s+\S+){0,8})?)'  # Điều X. Short Title
            r'|(?:(?:Chương|CHƯƠNG)\s+[IVX\d]+[^.]*)'    # Chương X...
            r'|(?:(?:Mục|MỤC)\s+[IVX\d]+[^.]*)'          # Mục X...
            r'|(?:(?:Phần|PHẦN)\s+[IVX\d]+[^.]*))',       # Phần X...
            last
        )
        if legal_match:
            heading = legal_match.group(1).strip()
            # Truncate heading if it's too long (body text leaked in)
            if len(heading) > 80:
                # Cut at the last word boundary before 80 chars
                heading = heading[:80].rsplit(' ', 1)[0]
            return heading

        # "Section N" or "Table > Page N" — leave to default page heading
        return None

    @staticmethod
    def _fix_table_gfm(text: str) -> str:
        """[P1] Fix broken GFM table markup by delegating to fix_table_gfm_v2."""
        return fix_table_gfm_v2(text)

    @staticmethod
    def _strip_content_boilerplate(text: str) -> str:
        """[P5] Strip government header boilerplate by delegating to strip_document_boilerplate."""
        return strip_document_boilerplate(text)

    @staticmethod
    def _dedup_parent_chunks(parent_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate parent chunks that have the same text content.
        
        The chunker may produce multiple parent chunks with identical text
        for the same article (e.g. art_0, art_1, art_2 on the same page).
        We keep only the first occurrence based on a content hash.
        """
        seen = set()
        unique = []
        for chunk in parent_chunks:
            text = chunk.get("text", "").strip()
            # Use full content hash for reliable dedup (300-char prefix was too weak)
            fingerprint = hash(text)
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique.append(chunk)
        return unique

    @staticmethod
    def _is_garbled_chunk(text: str) -> bool:
        """Check if a chunk's text is garbled OCR output (tables or corrupted data).
        
        Extends detect_garbled_table with additional heuristics specific to
        Markdown export quality.
        """
        if not text or len(text) < 30:
            return False

        # Check 1: Use existing heuristic
        if detect_garbled_table(text):
            return True

        # Check 2: High ratio of non-Vietnamese Unicode garbage chars
        garbage_chars = set('ŧĖΧŲġşŷįďŕŝ')
        garbage_count = sum(1 for c in text if c in garbage_chars)
        if garbage_count > 5:
            return True

        # Check 3: Contains HTML/LaTeX math or br tags (OCR artifacts)
        if '<math>' in text or '<br>' in text or '<sup>' in text:
            html_tag_count = text.count('<math>') + text.count('<br>') + text.count('<sup>')
            if html_tag_count >= 2:
                return True

        # Check 4: Very high repetition ratio — same large block repeats
        if len(text) > 500:
            # Check if first 200 chars repeat later
            sample = text[:200]
            occurrences = text.count(sample)
            if occurrences >= 3:
                return True

        return False

    @classmethod
    def _fix_vietnamese_spacing(cls, text: str) -> str:
        """Fix OCR word-merge artifacts by delegating to TextNormalizer."""
        return fix_vietnamese_syllable_boundaries(fix_stuck_vietnamese_words(text))

    @staticmethod
    def _wrap_xml_blocks(text: str) -> str:
        """[Fix #5b] Detect XML/code content and wrap in a fenced code block.

        Applicable to technical annexes (Phụ lục) containing XML examples (edXML)
        or structured data that should not be rendered as prose.
        """
        import re as _re
        # Already wrapped?
        if '```xml' in text or '```json' in text:
            return text
        # Detect XML: starts with <?xml or contains edXML namespace tags
        if _re.search(r'<\?xml|<edXML|<edXMLEnvelope|xmlns:edXML', text):
            xml_match = _re.search(r'(<\?xml|<edXML)', text)
            if xml_match:
                pre = text[:xml_match.start()].rstrip()
                xml_body = text[xml_match.start():]
                # Clean up any BASE64_DATA placeholders for readability
                xml_body = xml_body.replace('[BASE64_DATA]', '... [base64 binary data] ...')
                result = f"{pre}\n\n```xml\n{xml_body.strip()}\n```" if pre else f"```xml\n{xml_body.strip()}\n```"
                return result
        return text

    def _generate_markdown(self, rel_path: str, doc_id: str, meta: Dict[str, Any],
                           summary: str, chunks: List[Dict[str, Any]]) -> str:
        """Generate a formatted markdown string with natural document flow."""
        lines: list[str] = [f"# Document: {doc_id}\n"]

        # Metadata section — clean presentation
        lines.append("## Metadata")
        meta_display_order = [
            ('date', 'Date'), ('type', 'Type'), ('authority', 'Authority'),
            ('doc_number', 'Doc Number'), ('validity_status', 'Validity Status'),
            ('project_code', 'Project Code'), ('discipline', 'Discipline'),
            ('doc_status', 'Doc Status'), ('legal_level', 'Legal Level'),
        ]
        for key, label in meta_display_order:
            val = meta.get(key, '')
            if val and val not in ('unknown', 'UNKNOWN', ''):
                lines.append(f"- **{label}:** {val}")
        # Add filename and path at the end
        fn = meta.get('filename', os.path.basename(rel_path))
        lines.append(f"- **File Name:** {fn}")
        lines.append(f"- **Original Path:** {rel_path}\n")

        # Summary section
        lines.append("## Summary")
        lines.append(f"{summary}\n")

        # ------------------------------------------------------------------
        # Full content reconstruction from parent chunks
        # ------------------------------------------------------------------
        lines.append("## Content")

        # Sort parent chunks to reconstruct the flow
        parent_chunks = sorted(
            [c for c in chunks if c.get("chunk_type") == "parent"],
            key=lambda x: (x.get("page", 0), x.get("chunk_index", 0)),
        )

        if not parent_chunks:
            parent_chunks = chunks

        # ── Fix 1: Dedup parent chunks ──
        parent_chunks = self._dedup_parent_chunks(parent_chunks)

        current_page = None
        prev_heading = None

        for chunk in parent_chunks:
            page = chunk.get("page")

            # ── Fix 2: Skip garbled table chunks ──
            text = chunk.get("text", "")
            if self._is_garbled_chunk(text):
                # Only render a placeholder once per page for garbled content
                if page != current_page or not any("Bảng biểu gốc" in l for l in lines[-5:]):
                    lines.append("")
                    lines.append(f"> ⚠️ *Trang {page}: Bảng biểu gốc — dữ liệu OCR không thể chuyển đổi sang văn bản*")
                    lines.append("")
                current_page = page
                continue

            # ── Normalize chunk text ──
            text = normalize_chunk_text(text, strip_doc_id_prefix=doc_id)

            # ── Fix 6: Strip standalone page numbers from OCR (e.g. "2\n", "3\n") ──
            text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE).strip()

            # ── QF-5: Strip hierarchy context prefix from display text ──
            # e.g. "[Chương I] ::: Điều 1. Phạm vi" → "Điều 1. Phạm vi"
            text = re.sub(r'^\[(?:Chương|CHƯƠNG|Mục|MỤC|Phần|PHẦN)\s+[^\]]*\]\s*:::\s*', '', text)

            # ── P5: Strip government boilerplate from body text ──
            text = self._strip_content_boilerplate(text)

            # ── P1: Fix broken GFM table formatting ──
            text = self._fix_table_gfm(text)

            # ── P2: Fix Vietnamese word-merge spacing from OCR ──
            text = self._fix_vietnamese_spacing(text)

            if not text.strip():
                continue

            # ── Page transition ──
            if page != current_page and page is not None:
                if current_page is not None:
                    lines.append("")  # breathing room between pages

                # ── Fix 3: Build heading from hierarchy_path with truncation ──
                h_path = chunk.get("hierarchy_path", "")
                heading = self._extract_heading_from_hierarchy(h_path, doc_id)

                # Avoid duplicate consecutive headings
                if heading and heading != prev_heading:
                    lines.append(f"### {heading}")
                    prev_heading = heading
                elif not heading:
                    lines.append(f"<!-- Trang {page} -->")

                current_page = page

            # ── Fix 5: Preserve paragraph structure from chunk text ──
            # The chunk text already contains proper \n formatting from OCR/digital extraction.
            # We preserve this structure instead of collapsing into single lines.

            # ── Fix 4a: Strip leading heading from body that duplicates emitted heading ──
            # e.g. if we emitted "### Điều 2. Giải thích..." and the chunk text starts
            # with "Điều 2. Giải thích..." — remove the duplicate from body text.
            if prev_heading and text.lstrip().startswith(prev_heading.split('.')[0]):
                # Try to strip the full heading line from the beginning of text
                heading_pattern = re.escape(prev_heading)
                text = re.sub(rf'^\s*{heading_pattern}\s*', '', text, count=1).lstrip()

            # ── QF-4: Separate heading from body text ──
            # If text starts with "Điều X. Title Body text...", split into:
            #   "### Điều X. Title" (heading) + "Body text..." (body)
            # Only when no heading was emitted from hierarchy_path for this chunk
            dieu_inline = re.match(
                r'^([ĐÐ]iều\s+\d+\.?\s*[^\n]{0,80}?(?:\.|\s*$))\s*(.+)',
                text, re.DOTALL
            )
            if dieu_inline and not (prev_heading and prev_heading.startswith(('Điều', 'Đ'))):
                title_part = dieu_inline.group(1).strip()
                body_part = dieu_inline.group(2).strip()
                if title_part and len(title_part) <= 120:
                    lines.append(f"### {title_part}")
                    prev_heading = title_part
                    if body_part:
                        lines.append(body_part)
                    lines.append("")
                    continue

            # [P2-QCVN] ALL-CAPS numbered section heading detection
            # e.g. "1. QUY ĐỊNH CHUNG\nCác từ ngữ..." or "3. TỔ CHỨC THỰC HIỆN\n..."
            qcvn_section_match = re.match(
                r'^(\d+\.)\s+([A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]'
                r'[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s,]+)'
                r'(?:\n(.+))?$',
                text, re.DOTALL
            )
            if qcvn_section_match:
                sec_num = qcvn_section_match.group(1).rstrip('.')
                sec_title = qcvn_section_match.group(2).strip()
                body_part = (qcvn_section_match.group(3) or '').strip()
                heading_line = f"### {sec_num}. {sec_title}"
                if len(heading_line) <= 120:
                    lines.append(heading_line)
                    prev_heading = f"{sec_num}. {sec_title}"
                    if body_part:
                        lines.append(body_part)
                    lines.append("")
                    continue

            # [P2-QCVN] Phụ lục heading detection
            # e.g. "Phụ lục A\n(Quy định)\n..." or "PHỤ LỤC B\n..."
            phuluc_match = re.match(
                r'^((?:Phụ lục|PHỤ LỤC)\s+[A-Z](?:\.\d+)?(?:\s*[-–—]\s*[^\n]{0,60})?)\s*(?:\n(.+))?$',
                text, re.DOTALL
            )
            if phuluc_match:
                phuluc_title = phuluc_match.group(1).strip()
                body_part = (phuluc_match.group(2) or '').strip()
                heading_line = f"### {phuluc_title}"
                if len(heading_line) <= 120 and phuluc_title != prev_heading:
                    lines.append(heading_line)
                    prev_heading = phuluc_title
                    if body_part:
                        lines.append(body_part)
                    lines.append("")
                    continue

            # [P2] Numbered section inline detection (1.1., 3.2.4. at start of text)
            # Emit #### heading for numbered sections without Điều/Chương prefix
            num_section_match = re.match(
                r'^(\d+\.(?:\d+\.)*\d*\.?)\s+([^\n]{3,80})\n(.+)',
                text, re.DOTALL
            )
            if num_section_match:
                sec_num = num_section_match.group(1).rstrip('.')
                sec_title = num_section_match.group(2).strip()
                body_part = num_section_match.group(3).strip()
                depth = sec_num.count('.')
                hashes = '#####' if depth >= 2 else '####'
                heading_line = f"{hashes} {sec_num}. {sec_title}"
                if len(heading_line) <= 120:
                    lines.append(heading_line)
                    prev_heading = f"{sec_num}. {sec_title}"
                    if body_part:
                        lines.append(body_part)
                    lines.append("")
                    continue

            # [Fix #5b] Detect XML/code blocks and wrap in code fence
            text = self._wrap_xml_blocks(text)

            lines.append(text)
            lines.append("")

        # ── Fix 4b: Post-process — dedup consecutive headings ──
        # Remove "### Điều X." when "### Điều X. Full Title" appears within 5 lines
        final_lines: list[str] = []
        for idx, line in enumerate(lines):
            if line.startswith("### "):
                short_match = re.match(r'###\s+([ĐÐ]iều\s+\d+|(?:Chương|CHƯƠNG)\s+[IVX\d]+)', line)
                if short_match:
                    prefix = short_match.group(1)
                    # Scan ahead up to 10 lines for a longer heading with same prefix
                    found_longer = False
                    for j in range(idx + 1, min(idx + 10, len(lines))):
                        if lines[j].startswith("### "):
                            long_match = re.match(r'###\s+([ĐÐ]iều\s+\d+|(?:Chương|CHƯƠNG)\s+[IVX\d]+)', lines[j])
                            if long_match and long_match.group(1) == prefix and len(lines[j]) > len(line):
                                found_longer = True
                                break
                    if found_longer:
                        continue  # Skip this shorter heading
            final_lines.append(line)

        return "\n".join(final_lines)

    extract_doc_number_from_path = staticmethod(extract_doc_number_from_path)

    def reprocess_exports(self, action: str = "apply", export_dir: Optional[str] = None) -> dict:
        """Reprocess exported JSON and Markdown files in-place or dry-run/revert.

        Args:
            action: One of 'apply', 'dry-run', 'revert'.
            export_dir: Directory containing 'json' and 'markdown' folders. Defaults to self.export_dir.

        Returns:
            Dict summarizing statistics: {action, md_changed, json_changed, md_total, json_total}.
        """
        if action not in ("apply", "dry-run", "revert"):
            raise ValueError(f"Invalid action '{action}'. Must be 'apply', 'dry-run', or 'revert'.")

        base_dir = export_dir or self.export_dir
        md_dir = os.path.join(base_dir, "markdown")
        json_dir = os.path.join(base_dir, "json")

        md_files = sorted(glob.glob(os.path.join(md_dir, "*.md"))) if os.path.exists(md_dir) else []
        json_files = sorted(glob.glob(os.path.join(json_dir, "*.json"))) if os.path.exists(json_dir) else []

        # Filter out .bak files from file lists
        md_files = [f for f in md_files if not f.endswith(".bak")]
        json_files = [f for f in json_files if not f.endswith(".bak")]

        if action == "revert":
            md_restored = 0
            json_restored = 0
            if os.path.exists(md_dir):
                for bak in glob.glob(os.path.join(md_dir, "*.bak")):
                    orig = bak[:-4] if bak.endswith(".bak") else bak
                    if orig.endswith(".md"):
                        shutil.copy2(bak, orig)
                        md_restored += 1
            if os.path.exists(json_dir):
                for bak in glob.glob(os.path.join(json_dir, "*.bak")):
                    orig = bak[:-4] if bak.endswith(".bak") else bak
                    if orig.endswith(".json"):
                        shutil.copy2(bak, orig)
                        json_restored += 1
            logger.info(f"Reverted {md_restored} markdown and {json_restored} JSON files from backups.")
            return {
                "action": "revert",
                "md_changed": md_restored,
                "json_changed": json_restored,
                "md_total": len(md_files),
                "json_total": len(json_files),
            }

        # Backup files if action == "apply"
        if action == "apply":
            for f in md_files + json_files:
                bak = f + ".bak"
                if not os.path.exists(bak):
                    shutil.copy2(f, bak)

        md_changed = 0
        json_changed = 0

        # Process Markdown files
        for f in md_files:
            try:
                text = Path(f).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"Error reading {f}: {e}")
                continue

            original = text

            # Isolate ## Content section to protect Metadata and Summary sections
            content_match = re.search(r"(## Content\s*\n)(.*)", text, re.DOTALL)
            if content_match:
                pre = text[: content_match.start(2)]
                content = content_match.group(2)

                content = strip_random_emojis(content)
                content = strip_ai_monologue(content)
                content = fix_table_gfm_v2(content)
                content = normalize_ocr_spacing(content)
                content = fix_common_ocr_typos(content)
                content = fix_stuck_vietnamese_words(content)
                content = fix_generic_stuck_words(content)
                content = fix_vietnamese_syllable_boundaries(content)
                content = strip_noi_nhan_block(content)
                content = strip_digital_signature(content)
                content = strip_document_boilerplate(content)

                new_text = pre + content
            else:
                new_text = strip_random_emojis(text)
                new_text = strip_ai_monologue(new_text)
                new_text = fix_table_gfm_v2(new_text)

            if new_text != original:
                md_changed += 1
                if action == "apply":
                    Path(f).write_text(new_text, encoding="utf-8")

        # Process JSON files
        for f in json_files:
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8", errors="replace"))
            except Exception as e:
                logger.warning(f"Error parsing JSON {f}: {e}")
                continue

            if not isinstance(data, dict):
                continue

            changed = False
            meta = data.get("metadata")
            if not isinstance(meta, dict):
                meta = {}
                data["metadata"] = meta

            current_dn = meta.get("doc_number", "")
            if not current_dn or not str(current_dn).strip():
                extracted = extract_doc_number_from_path(f)
                if extracted:
                    meta["doc_number"] = extracted
                    for c in (data.get("chunks") or []):
                        if isinstance(c, dict):
                            c["doc_number"] = extracted
                    changed = True

            for c in (data.get("chunks") or []):
                if not isinstance(c, dict):
                    continue
                old_text = c.get("text", "")
                if not old_text:
                    continue
                new_text = strip_random_emojis(old_text)
                new_text = strip_ai_monologue(new_text)
                new_text = strip_document_boilerplate(new_text)
                new_text = strip_noi_nhan_block(new_text)
                new_text = strip_digital_signature(new_text)
                if new_text != old_text:
                    c["text"] = new_text
                    changed = True

            if changed:
                json_changed += 1
                if action == "apply":
                    with open(f, "w", encoding="utf-8") as jf:
                        json.dump(data, jf, ensure_ascii=False, indent=2)

        action_label = "Would fix" if action == "dry-run" else "Fixed"
        logger.info(f"{action_label} {md_changed}/{len(md_files)} markdown files")
        logger.info(f"{action_label} {json_changed}/{len(json_files)} JSON files")

        return {
            "action": action,
            "md_changed": md_changed,
            "json_changed": json_changed,
            "md_total": len(md_files),
            "json_total": len(json_files),
        }

