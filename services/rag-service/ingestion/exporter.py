import os
import json
import re
import logging
from typing import List, Dict, Any

from ingestion.text_normalizer import normalize_chunk_text, detect_garbled_table

logger = logging.getLogger(__name__)

# ── P5: Boilerplate patterns to strip from Content section ───────────────
# [P5-FIX] Tolerant of OCR word-merges: "HỘICHỦ" instead of "HỘI CHỦ"
_CONTENT_BOILERPLATE_RE = re.compile(
    r'(?:^|\n)'
    r'(?:CỘNG\s*HÒA\s*XÃ\s*HỘI\s*CHỦ\s*NGHĨA\s*VIỆT\s*NAM\s*'
    r'(?:Độc\s*lập\s*[-–—]\s*Tự\s*do\s*[-–—]\s*Hạnh\s*phúc)?'
    r'|Độc\s*lập\s*[-–—]\s*Tự\s*do\s*[-–—]\s*Hạnh\s*phúc)'
    r'\s*(?:\n|$)',
    re.IGNORECASE | re.MULTILINE
)


class DataExporter:
    def __init__(self, export_dir: str = "/app/exports"):
        self.export_dir = export_dir
        self.json_dir = os.path.join(export_dir, "json")
        self.md_dir = os.path.join(export_dir, "markdown")

        # Create directories if they don't exist
        try:
            os.makedirs(self.json_dir, exist_ok=True)
            os.makedirs(self.md_dir, exist_ok=True)
            logger.info(f"Initialized DataExporter at {export_dir}")
        except Exception as e:
            logger.error(f"Failed to create export directories: {e}")

    def export(self, rel_path: str, doc_id: str, meta: Dict[str, Any], summary: str, chunks: List[Dict[str, Any]]):
        """Export processed document data to JSON and Markdown."""
        try:
            # Sanitize doc_id for filename (replace / and other chars)
            safe_filename = doc_id.replace('/', '_').replace('\\', '_').replace(':', '_').replace(' ', '_')

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
        except Exception as e:
            logger.error(f"Failed to export data for {doc_id}: {e}")

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
        """[P1] Fix broken GFM table markup by inserting missing separator rows.

        A valid GFM table requires a separator row (|---|---|) immediately
        after the header row. This method detects header-like pipe rows
        NOT followed by a separator and inserts one.

        Header heuristic refinements (v2):
        - Reject rows where the first cell is a plain number (data row, not header)
        - Reject rows where ALL cells are short words/abbreviations like "B", "K", ""
          (compliance checkmark rows)
        - Reset table state on blank-line gaps between consecutive tables
        """
        if '|' not in text:
            return text

        lines = text.split('\n')
        fixed: list[str] = []
        in_table = False  # Track if we've already seen/inserted a separator

        for i, line in enumerate(lines):
            stripped = line.strip()
            is_pipe_row = (
                stripped.startswith('|') and stripped.endswith('|')
                and stripped.count('|') >= 3
            )

            if not is_pipe_row:
                # Reset table state on non-pipe lines (gap between tables)
                in_table = False
                fixed.append(line)
                continue

            # Check if the NEXT line is already a separator
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
            is_next_sep = bool(re.match(r'^\|[\s:-]+\|', next_line))

            if is_next_sep:
                in_table = True  # Existing separator found
                fixed.append(line)
                continue

            if in_table:
                # Already inside a table (separator was seen/inserted) — data row
                fixed.append(line)
                continue

            # First pipe row without a following separator — header detection
            cells = [c.strip() for c in stripped.split('|')[1:-1]]

            # Reject: first cell is a plain number (data row like "| 1 | Name | XX |")
            first_cell = cells[0] if cells else ''
            first_cell_is_number = bool(re.match(r'^\d+\.?$', first_cell.strip()))

            # Reject: all cells are empty or single-char abbreviations
            all_trivial = all(len(c) <= 2 for c in cells)

            is_header = (
                cells
                and not first_cell_is_number
                and not all_trivial
                and all(len(c) < 60 for c in cells)
                and any(re.search(r'[a-zA-Z\u00c0-\u1ef9]', c) for c in cells)
                and not all(re.match(r'^[\d.,\s%]+$', c) for c in cells if c)
            )
            if is_header:
                sep = '| ' + ' | '.join('---' for _ in cells) + ' |'
                fixed.append(line)
                fixed.append(sep)
                in_table = True
            else:
                fixed.append(line)

        return '\n'.join(fixed)

    @staticmethod
    def _strip_content_boilerplate(text: str) -> str:
        """[P5] Strip government header boilerplate from content text."""
        text = _CONTENT_BOILERPLATE_RE.sub('\n', text)
        # Also strip standalone "Số: xxx/QĐ-BXD" lines that leak into content
        text = re.sub(
            r'(?:^|\n)\s*Số\s*:\s*[\d/]+\s*[A-ZĐ]{2,}[-][A-ZĐ]+\s*(?:\n|$)',
            '\n', text
        )
        return text.strip()

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

    # ── [P2-FIX] Vietnamese word-merge spacing correction ─────────────
    # OCR output often strips spaces between Vietnamese words, producing
    # artifacts like: "vềcải cách", "doBộ trưởng", "làcơ sở".
    # This regex detects lowercase-to-uppercase transitions and inserts a space.
    _VN_LOWER = (
        r'a-zàáạảãăắằẳẵặâấầẩẫậđèéẹẻẽêếềểễệìíịỉĩ'
        r'òóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹ'
    )
    _VN_UPPER = (
        r'A-ZÀÁẠẢÃĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẸẺẼÊẾỀỂỄỆÌÍỊỈĨ'
        r'ÒÓỌỎÕÔỐỒỔỖỘƠỚỜỞỠỢÙÚỤỦŨƯỨỪỬỮỰỲÝỴỶỸ'
    )
    _SPACING_RE = re.compile(
        rf'([{_VN_LOWER}])([{_VN_UPPER}])'
    )
    # Also fix ALL-CAPS merges like "ĐÔTHỊVÀ" → "ĐÔ THỊ VÀ"
    _ALLCAPS_MERGE_RE = re.compile(
        rf'([{_VN_UPPER}]{{2,}})([{_VN_UPPER}][{_VN_LOWER}])'
    )

    # [P2-FIX-v2] Common Vietnamese word-merge patterns (lowercase→lowercase)
    # that the regex approach cannot detect reliably.
    # These are high-frequency merge artifacts found in OCR output of legal docs.
    _WORD_MERGE_FIXES = [
        # Preposition/conjunction merges (sorted longest first to avoid partial matches)
        ('vềcác', 'về các'), ('vềcán', 'về cán'), ('vềcác', 'về các'),
        ('vềnhà', 'về nhà'), ('vền hà', 'về nhà'),  # split-merge artifact
        ('docơ', 'do cơ'), ('của', 'của'), ('vàtên', 'và tên'),
        ('vàtài', 'và tài'), ('vàmối', 'và mối'), ('vàmức', 'và mức'),
        ('đãkê', 'đã kê'), ('đãkế', 'đã kế'),
        ('cócấp', 'có cấp'), ('cóảnh', 'có ảnh'),
        ('cón hà', 'có nhà'),  # split-merge artifact
        ('đầy đủcác', 'đầy đủ các'),
        ('sở hữucủa', 'sở hữu của'), ('ởcủa', 'ở của'),
        ('củatôi', 'của tôi'), ('têncủa', 'tên của'), ('cáccon', 'các con'),
        ('mẹcủa', 'mẹ của'),
        ('hợp lệc ho', 'hợp lệ cho'), ('nhà ởc ho', 'nhà ở cho'),
        ('mởc ho', 'mở cho'),
        ('phục vụtại', 'phục vụ tại'),
        ('đăng kýtạm', 'đăng ký tạm'), ('đăng kýtại', 'đăng ký tại'),
        ('nghề nghiệp3', 'nghề nghiệp'), ('đối tượng5', 'đối tượng'),
        ('đơn vịnơi', 'đơn vị nơi'),
        ('yêucầu', 'yêu cầu'), ('đápứng', 'đáp ứng'),
        ('Đạitá', 'Đại tá'), ('phụcấp', 'phụ cấp'),
        ('tổ chức cơ yếu hưởng', 'tổ chức cơ yếu hưởng'),
        ('thiết kếkỹ', 'thiết kế kỹ'), ('thiết kếcơ', 'thiết kế cơ'),
        ('quản lýn hà', 'quản lý nhà'), ('quản lýc hi', 'quản lý chi'),
        ('XÃHỘI', 'XÃ HỘI'), ('HỘICHỦ', 'HỘI CHỦ'), ('BỐHỢP', 'BỐ HỢP'),
        ('dovi phạm', 'do vi phạm'), ('phá dỡn hà', 'phá dỡ nhà'),
        ('hỗ trợn hà', 'hỗ trợ nhà'), ('hỗ trợcải', 'hỗ trợ cải'),
        ('bịảnh', 'bị ảnh'),
        ('cấp xãnơi', 'cấp xã nơi'),
        ('làcơ', 'là cơ'), ('làtài', 'là tài'), ('làkế', 'là kế'),
        ('làcác', 'là các'), ('làmcơ', 'làm cơ'),
        ('vớiquy', 'với quy'),
        ('đápứngcác', 'đáp ứng các'), ('đápứngcácmục', 'đáp ứng các mục'),
        ('yêucầucủa', 'yêu cầu của'),
        ('Hồ sơYêu', 'Hồ sơ Yêu'), ('sơYêu', 'sơ Yêu'),
    ]

    @classmethod
    def _fix_vietnamese_spacing(cls, text: str) -> str:
        """Fix OCR word-merge artifacts by inserting missing spaces."""
        if not text:
            return text
        # Don't modify table rows or markdown headings with REGEX fix
        # but DO apply dictionary fixes to all lines (safe exact replacements)
        lines = text.split('\n')
        fixed = []
        for line in lines:
            s = line.strip()
            # [P2-FIX-v2] Apply dictionary fixes to ALL lines (safe for tables)
            for wrong, correct in cls._WORD_MERGE_FIXES:
                if wrong in line:
                    line = line.replace(wrong, correct)
            # Skip regex fix for table rows and markdown headings
            if s.startswith('|') or s.startswith('#'):
                fixed.append(line)
                continue
            # Fix lowercase→uppercase transitions: "vềcải" → "về cải"
            line = cls._SPACING_RE.sub(r'\1 \2', line)
            fixed.append(line)
        return '\n'.join(fixed)

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
