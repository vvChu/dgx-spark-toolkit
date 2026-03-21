"""
Text Normalizer for Markdown Export.

Post-processing utilities that transform raw chunk text into clean,
readable Markdown without altering the Milvus-indexed data.

Functions:
    rejoin_paragraphs  — Merge hard-wrapped lines while preserving structure.
    format_legal_structure — Convert Điều/Chương/Mục markers into Markdown headings.
    detect_garbled_table — Heuristic check for OCR-garbled table text.
"""
import re
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# -1. OCR Spacing Normalization (for scanned PDFs with char-separated text)
# ---------------------------------------------------------------------------

# Vietnamese characters that may appear space-separated in broken OCR
_VN_CHARS = r'[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴa-zđàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]'

# Pattern: single Vietnamese char + 1-3 spaces + single Vietnamese char (repeated)
_SPACED_CHAR_RE = re.compile(
    rf'({_VN_CHARS})\s{{1,3}}(?={_VN_CHARS}(?:\s{{1,3}}{_VN_CHARS}))'
)

def normalize_ocr_spacing(text: str) -> str:
    """Fix character-separated Vietnamese text from scanned PDFs.

    Detects lines where Vietnamese characters are separated by excessive spaces
    (e.g. 'B Ộ  XÂY D Ự NG' → 'BỘ XÂY DỰNG') and collapses them.

    Only applies to lines where >30% of tokens are single characters,
    to avoid collapsing normal spaced text.
    """
    if not text:
        return text

    lines = text.split('\n')
    fixed_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            fixed_lines.append(line)
            continue

        # Count short tokens (1-2 chars) that are Vietnamese letters
        # Vietnamese composed chars like ƯỞ, ĐỊ, ẤT are 2 code points
        tokens = stripped.split()
        if len(tokens) < 3:
            fixed_lines.append(line)
            continue

        short_vn_tokens = sum(1 for t in tokens if len(t) <= 2 and re.match(rf'^{_VN_CHARS}+$', t))
        ratio = short_vn_tokens / len(tokens)

        if ratio > 0.30:
            # This line has excessive spacing — collapse short-char runs
            # Strategy: join runs of 1-2 char Vietnamese tokens
            result = []
            i = 0
            while i < len(tokens):
                if len(tokens[i]) <= 2 and re.match(rf'^{_VN_CHARS}+$', tokens[i]):
                    # Start of a short-char run — collect consecutive short VN tokens
                    run = [tokens[i]]
                    j = i + 1
                    while j < len(tokens) and len(tokens[j]) <= 2 and re.match(rf'^{_VN_CHARS}+$', tokens[j]):
                        run.append(tokens[j])
                        j += 1
                    result.append(''.join(run))
                    i = j
                else:
                    result.append(tokens[i])
                    i += 1

            fixed_line = ' '.join(result)
            fixed_lines.append(fixed_line)
        else:
            fixed_lines.append(line)

    return '\n'.join(fixed_lines)


# ---------------------------------------------------------------------------
# 0. Boilerplate / Header Noise Removal
# ---------------------------------------------------------------------------

# Exact substrings to strip (case-insensitive matching via .upper())
_BOILERPLATE_EXACT = [
    'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
    'CONG HOA XA HOI CHU NGHIA VIET NAM',
    'ĐỘC LẬP - TỰ DO - HẠNH PHÚC',
    'Độc lập - Tự do - Hạnh phúc',
    'DOC LAP - TU DO - HANH PHUC',
    '---oOo---',
    '———',
    '----',
]
_BOILERPLATE_UPPER = [s.upper() for s in _BOILERPLATE_EXACT]

# Regex patterns for structured noise lines
_BOILERPLATE_REGEX = [
    re.compile(r'(?i)^\s*Số\s*:\s*\d+.*$'),                   # Số: 05/2024/TT-BTP
    re.compile(r'(?i)^\s*V/v\s*:.*$'),                         # V/v: Về việc...
    re.compile(r'(?i)^\s*(?:Hà Nội|Đà Nẵng|TP\.?\s*Hồ Chí Minh|Thành phố\s+\w+),?\s*ngày.*$'),
    re.compile(r'(?i)^\s*Kính gửi\s*:.*$'),                    # Kính gửi:
    re.compile(r'(?i)^\s*Nơi nhận\s*:.*$'),                    # Nơi nhận:
    re.compile(r'(?i)^\s*(?:BỘ|UBND|ỦY BAN|SỞ|PHÒNG|HỘI ĐỒNG)\s+[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s]+$'),
    re.compile(r'(?i)^\s*CHÍNH PHỦ\s*$'),
    re.compile(r'(?i)^\s*THỦ TƯỚNG CHÍNH PHỦ\s*$'),
    re.compile(r'(?i)^\s*QUỐC HỘI\s*$'),
    # Digital signature metadata
    re.compile(r'(?i)^\s*Người ký\s*:.*$'),
    re.compile(r'(?i)^\s*Thời gian ký\s*:.*$'),
    re.compile(r'(?i)^\s*Email\s*:.*@.*$'),
    re.compile(r'(?i)^\s*Cơ quan\s*:.*$'),
    # Distribution list items ending with ; or ,
    re.compile(r'^\s*-\s*(?:UBND|Văn phòng|Hội đồng|Viện|Ủy ban|Ngân hàng|Cơ quan|VPCP|Các Vụ|Cổng|Lưu).*[;,:]\s*$'),
    # VGP / Electronic portal header noise
    re.compile(r'(?i)^.*CỔNG\s+THÔNG\s+TIN\s+ĐIỆN\s+TỬ.*$'),
    re.compile(r'(?i)^.*chinhphu\.vn.*$'),
    re.compile(r'(?i)^.*thongtinchinhphu@.*$'),
    re.compile(r'(?i)^\s*VGP\s*$'),
    re.compile(r'(?i)^.*CHINHPHU\.VN.*$'),
    # Handwritten annotations (e.g. TTĐT(2), TT(2))
    re.compile(r'^\s*[A-ZĐTTBHCN]{2,8}\s*\(\s*\d+\s*\)\s*$'),
    # Archive codes
    re.compile(r'(?i)^\s*-?\s*Lưu\s*:.*$'),
    # Combined date + signer line (e.g. "Hà Nội, ngày 09/9/2025 KT. BỘ TRƯỞNG")
    re.compile(r'(?i)^.*ngày.*(?:KT\.|TM\.|Ký thay)\s*(?:THỦ TƯỚNG|BỘ TRƯỞNG|CHỦ TỊCH).*$'),
    # Combined single-line digital signature block
    # e.g. "Ký bởi: Cổng Thông tin ... Email: xxx@yyy Cơ quan: ... Thời gian ký: ..."
    re.compile(r'(?i)^\s*(?:Ký bởi|Người ký)\s*:.*(?:Email|Cơ quan|Thời gian ký).*$'),
]


def strip_document_boilerplate(text: str) -> str:
    """Remove Vietnamese government document header boilerplate from text.

    Only processes the first ~600 chars to avoid stripping legitimate content
    deeper in the document.
    """
    if not text or len(text) < 20:
        return text

    lines = text.split('\n')
    cleaned_lines = []
    chars_seen = 0
    boilerplate_zone = True  # We're in the header zone until we see real content

    for line in lines:
        stripped = line.strip()
        chars_seen += len(line) + 1  # +1 for newline

        # Stop filtering after 600 chars — rest is content for sure
        if chars_seen > 600:
            boilerplate_zone = False

        if boilerplate_zone and stripped:
            upper = stripped.upper()

            # Check exact match
            if any(bp in upper for bp in _BOILERPLATE_UPPER):
                continue

            # Check regex patterns
            if any(rx.match(stripped) for rx in _BOILERPLATE_REGEX):
                continue

            # Skip very short ALL-CAPS lines in header zone (likely org names)
            if len(stripped) < 60 and stripped == stripped.upper() and not any(c.isdigit() for c in stripped):
                # But don't skip if it looks like an article title (Điều, Chương)
                if not re.match(r'^[ĐÐ]iều|^Chương|^Mục|^Phần', stripped):
                    continue

        # Keep blank lines in header zone (they collapse later)
        if not stripped and boilerplate_zone:
            continue

        cleaned_lines.append(line)

    result = '\n'.join(cleaned_lines).strip()

    if result:
        return result
    # Safety: if we stripped everything, return original
    return text


def strip_noi_nhan_block(text: str) -> str:
    """Remove 'Nơi nhận:' distribution list block from anywhere in text.

    These blocks appear as:
        Nơi nhận:
        - Như trên;
        - UBND các tỉnh, thành phố;
        - Lưu: VT, KSTT.
    """
    if not text or 'Nơi nhận' not in text and 'nơi nhận' not in text.lower():
        return text

    lines = text.split('\n')
    result = []
    in_noi_nhan = False

    for line in lines:
        stripped = line.strip()

        # Detect start of Nơi nhận block
        if re.match(r'(?i)^\s*Nơi nhận\s*:', stripped):
            in_noi_nhan = True
            continue

        if in_noi_nhan:
            # Distribution list items: "- Xxx;" or "- Lưu: VT, KSTT."
            if re.match(r'^\s*-\s+', stripped) and (stripped.endswith(';') or stripped.endswith(',') or stripped.endswith('.') or 'Lưu' in stripped):
                continue
            # Still short lines that look like continuation
            if len(stripped) < 80 and stripped.endswith(';'):
                continue
            # Short lines with semi-colons or commas (dist list continuation)
            if len(stripped) < 80 and re.match(r'^\s*-\s+', stripped):
                continue
            # Exit block: real content resumes
            in_noi_nhan = False

        result.append(line)

    return '\n'.join(result)


def strip_signer_block(text: str) -> str:
    """Remove signer block (KT./TM./PHÓ THỦ TƯỚNG + name) from end of text.

    SAFETY: Only operates on the LAST 500 chars to avoid stripping body content
    that mentions 'Thủ tướng Chính phủ ban hành...'

    Detects patterns like:
        KT. THỦ TƯỚNG
        PHÓ THỦ TƯỚNG
        Lê Thành Long
    Or:
        TM. CHÍNH PHỦ
        THỦ TƯỚNG
        Nguyễn Xuân Phúc
    """
    if not text or len(text) < 100:
        return text

    # Only look at the tail of the text (last 500 chars)
    TAIL_SIZE = 500
    if len(text) <= TAIL_SIZE:
        head = ''
        tail = text
    else:
        # Find a safe split point (at a newline boundary)
        split_pos = text.rfind('\n', len(text) - TAIL_SIZE, len(text) - 200)
        if split_pos == -1:
            split_pos = len(text) - TAIL_SIZE
        head = text[:split_pos]
        tail = text[split_pos:]

    # Signer block start markers (spacing-aware for scanned PDFs)
    _SIGNER_START = re.compile(
        r'^\s*(?:KT\.|TM\.|Ký thay\.?|Q\.)\s*'
        r'(?:TH\s*Ủ\s*T\s*Ư\s*Ớ\s*NG|CH\s*Ủ\s*T\s*Ị\s*CH|B\s*Ộ\s*TR\s*Ư\s*Ở\s*NG|CH\s*Í\s*NH\s*PH\s*Ủ|'
        r'THỦ TƯỚNG|CHỦ TỊCH|BỘ TRƯỞNG|CHÍNH PHỦ)',
        re.MULTILINE | re.IGNORECASE
    )

    match = _SIGNER_START.search(tail)
    if match:
        # Strip from signer marker to end
        tail = tail[:match.start()].rstrip()
        logger.info(f"  Stripped signer block from end of text ({len(text) - len(head) - len(tail)} chars removed)")

    return (head + tail).strip()


# Regex for combined digital signature blocks (may span 1-2 lines due to OCR wrapping)
# Must match from "Ký bởi:" through the final timezone like "+07:00"
# Real example: "Ký bởi: Cổng ... Email: x@y Cơ quan: Z Thời gian \nký: 16.03.2015 11:02:35 +07:00"
_DIGITAL_SIGNATURE_RE = re.compile(
    r'(?:Ký bởi|Người ký)\s*:.+?(?:\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\s*[+\-]\d{2}:\d{2})',
    re.IGNORECASE | re.DOTALL
)


def strip_digital_signature(text: str) -> str:
    """Strip combined digital signature metadata from anywhere in text.

    Unlike strip_document_boilerplate which only operates on the first 600 chars,
    this function targets the very specific 'Ký bởi: ... Email: ... Thời gian ký: ...'
    pattern which is unambiguous and safe to strip from any position.

    Handles line breaks within the signature block (e.g. OCR wrapping
    'Thời gian \\nký:' onto two lines).
    """
    if not text:
        return text
    cleaned = _DIGITAL_SIGNATURE_RE.sub('', text)
    # Collapse excess blank lines left behind
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip() if cleaned.strip() else text


# ---------------------------------------------------------------------------
# 0b. OCR Typo Correction
# ---------------------------------------------------------------------------

_OCR_TYPO_MAP = [
    # (wrong, correct) — common Vietnamese OCR errors
    ('NGHÈ', 'NGHỀ'),
    ('Nghè', 'Nghề'),
    ('nghè', 'nghề'),
    ('Tỳ lệ', 'Tỷ lệ'),
    ('tỳ lệ', 'tỷ lệ'),
    ('hổ sơ', 'hồ sơ'),
    ('Hổ sơ', 'Hồ sơ'),
    ('bố sung', 'bổ sung'),
    ('Bố sung', 'Bổ sung'),
    ('tính,', 'tỉnh,'),  # tính → tỉnh before comma
    ('tính.', 'tỉnh.'),
    ('họp đồng', 'hợp đồng'),
    ('Họp đồng', 'Hợp đồng'),
    ('trưởng họp', 'trường hợp'),
    ('Trưởng họp', 'Trường hợp'),
    ('trực thuộc trung ượng', 'trực thuộc trung ương'),
]


def fix_common_ocr_typos(text: str) -> str:
    """Fix frequent Vietnamese OCR misrecognitions."""
    if not text:
        return text
    for wrong, correct in _OCR_TYPO_MAP:
        if wrong in text:
            text = text.replace(wrong, correct)
    return text


# ---------------------------------------------------------------------------
# 0c2. Stuck Vietnamese Word Fix (OCR word-joining)
# ---------------------------------------------------------------------------

# Common Vietnamese word pairs that OCR sticks together (no space between)
_STUCK_WORD_FIXES = [
    # Pattern, Replacement — sorted by frequency of occurrence
    ('hồsơ', 'hồ sơ'),
    ('Hồsơ', 'Hồ sơ'),
    ('vàcó', 'và có'),
    ('vàxử', 'và xử'),
    ('vàcác', 'và các'),
    ('vàvị', 'và vị'),
    ('vàrà', 'và rà'),
    ('sựcố', 'sự cố'),
    ('cơsở', 'cơ sở'),
    ('Cơsở', 'Cơ sở'),
    ('chiếutới', 'chiếu tới'),
    ('đođộ', 'đo độ'),
    ('Ápkế', 'Áp kế'),
    ('épôm', 'ép ôm'),
    ('éprô', 'ép rô'),
    ('Xảáp', 'Xả áp'),
    ('thểhiện', 'thể hiện'),
    ('quảlý', 'quả lý'),
    ('nhàở', 'nhà ở'),
    ('trờicó', 'trời có'),
    # Additional from corpus analysis (quality evaluation 2025-03)
    # IMPORTANT: Longer patterns MUST come before shorter ones to avoid partial matching
    ('đãcóhạ', 'đã có hạ'),
    ('đãcóphương', 'đã có phương'),
    ('đãcó', 'đã có'),
    ('mởra', 'mở ra'),
    ('kểtừ', 'kể từ'),
    ('sốvà', 'số và'),
    ('dựán', 'dự án'),
    ('Dựán', 'Dự án'),
    ('sởdữ', 'sở dữ'),
    ('lývàrà', 'lý và rà'),
    ('lývà', 'lý và'),
    ('ánđã', 'án đã'),
    ('đánh sốvà', 'đánh số và'),
    ('quản lývàrà', 'quản lý và rà'),
    ('quản lývà', 'quản lý và'),
    ('Xửlý', 'Xử lý'),
    ('xửlý', 'xử lý'),
    ('đầu tưdự', 'đầu tư dự'),
    ('phương ánđã', 'phương án đã'),
    ('thiết kếđã', 'thiết kế đã'),
]


def fix_stuck_vietnamese_words(text: str) -> str:
    """Fix common Vietnamese words stuck together by OCR (no space between).

    Examples: 'hồsơ' → 'hồ sơ', 'vàcó' → 'và có'
    """
    if not text:
        return text
    for wrong, correct in _STUCK_WORD_FIXES:
        if wrong in text:
            text = text.replace(wrong, correct)
    return text


# ---------------------------------------------------------------------------
# 0c3. Generic Stuck Word Detection (regex-based)
# ---------------------------------------------------------------------------

# Vietnamese diacritic-ending lowercase chars that strongly signal word-end
_VN_DIACRITIC_LOWER = r'[àáảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]'
# Vietnamese uppercase chars that signal word-start
_VN_UPPER_START = r'[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]'

# Pattern: diacritic-ending lowercase immediately followed by uppercase = word boundary
_STUCK_GENERIC_RE = re.compile(
    rf'({_VN_DIACRITIC_LOWER})({_VN_UPPER_START})'
)


def fix_generic_stuck_words(text: str) -> str:
    """Insert space between Vietnamese words stuck together by OCR.

    Uses regex to detect patterns where a lowercase Vietnamese character
    with diacritics is immediately followed by an uppercase character,
    which strongly signals a missing word boundary.

    Examples: 'đãCó' → 'đã Có', 'kểTừ' → 'kể Từ'
    """
    if not text:
        return text
    return _STUCK_GENERIC_RE.sub(r'\1 \2', text)


# ---------------------------------------------------------------------------
# 0c4. Date/Page Metadata Noise Stripping
# ---------------------------------------------------------------------------

_DATE_PAGE_NOISE_PATTERNS = [
    # Fragmented date metadata: "01 06 01 2025 2025" or "03 14 04"
    re.compile(r'\n\s*\d{2}\s+\d{2}\s+\d{2}\s+\d{4}\s+\d{4}\s*$'),
    re.compile(r'\n\s*\d{2}\s+\d{2}\s+\d{2}\s*$'),
    # Standalone page numbers on their own line ("2" between pages)
    re.compile(r'^\s*\d{1,3}\s*$', re.MULTILINE),
]


def strip_date_page_noise(text: str) -> str:
    """Strip fragmented date/page number metadata from chunk text.

    Removes patterns like '01 06 01 2025 2025' (split date metadata)
    and standalone page numbers.
    """
    if not text:
        return text
    for pat in _DATE_PAGE_NOISE_PATTERNS:
        text = pat.sub('', text)
    return text.strip()


# ---------------------------------------------------------------------------
# 0c5. Template Dotted Line Stripping
# ---------------------------------------------------------------------------

def strip_template_dots(text: str) -> str:
    """Strip form template fill patterns (repeated dots/periods).

    Removes patterns like '. . . . . . . . . .' which appear in
    government form templates and annexes.
    """
    if not text:
        return text
    # 20+ consecutive dots (with optional spaces)
    text = re.sub(r'(?:\.\s*){20,}', '', text)
    # 10+ spaced dots pattern
    text = re.sub(r'(?:\.\s){10,}', '', text)
    return text


# ---------------------------------------------------------------------------
# 0c. Broken Heading Rejoin
# ---------------------------------------------------------------------------

def rejoin_broken_headings(text: str) -> str:
    """Rejoin ALL-CAPS headings broken across lines.

    Fixes patterns like:
        **II. QUY ĐỊNH VỀ YÊU CẦU, ĐIỀU KIỆN TRONG HOẠT**
        ĐỘNG KINH DOANH:
    Into:
        **II. QUY ĐỊNH VỀ YÊU CẦU, ĐIỀU KIỆN TRONG HOẠT ĐỘNG KINH DOANH:**
    """
    if not text:
        return text

    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if line ends with bold-wrapped truncated text: ends with **
        if stripped.endswith('**') and i + 1 < len(lines):
            next_stripped = lines[i + 1].strip()
            # Next line is ALL-CAPS continuation
            alpha_next = [c for c in next_stripped if c.isalpha()]
            if alpha_next and sum(1 for c in alpha_next if c.isupper()) / len(alpha_next) > 0.7:
                # Merge: remove trailing ** from current, add next line, close **
                merged = stripped[:-2].rstrip() + ' ' + next_stripped
                if not merged.endswith('**'):
                    merged += '**'
                result.append(merged)
                i += 2
                continue

        result.append(line)
        i += 1

    return '\n'.join(result)


# ---------------------------------------------------------------------------
# 1. Paragraph Rejoining
# ---------------------------------------------------------------------------

# Patterns that signal a new logical block (should NOT be merged with prev line)
_BLOCK_START_PATTERNS = [
    re.compile(r'^\s*[ĐÐ]iều\s+\d+'),               # Điều X
    re.compile(r'^\s*(?:Chương|CHƯƠNG)\s+[IVX\d]+'),  # Chương
    re.compile(r'^\s*(?:Mục|MỤC)\s+[IVX\d]+'),       # Mục
    re.compile(r'^\s*(?:Phần|PHẦN)\s+[IVX\d]+'),      # Phần
    re.compile(r'^\s*(?:Bảng|BẢNG)\s+\S+'),           # Bảng X.Y — table label, never merge
    re.compile(r'^\s*(?:Phụ lục|PHỤ LỤC)\s+\S+'),    # Phụ lục A — annex label
    re.compile(r'^\s*\d+\.\s'),                       # Numbered clause: "1. "
    re.compile(r'^\s*[a-zđ]\)\s'),                    # Lettered sub-clause: "a) "
    re.compile(r'^\s*-\s'),                           # Dash list item
    re.compile(r'^\s*\+\s'),                          # Plus list item
    re.compile(r'^\s*\*\s'),                          # Bullet list item
    re.compile(r'^\s*[IVX]+\.\s'),                    # Roman numeral section
    re.compile(r'^\s*#{1,4}\s'),                      # Markdown heading
    re.compile(r'^\s*\|'),                            # Table row
    re.compile(r'^\s*>'),                             # Blockquote
]



def _is_block_start(line: str) -> bool:
    """Check if a line starts a new structural block."""
    return any(p.match(line) for p in _BLOCK_START_PATTERNS)

# A line that is "continuation-friendly": ends with a lowercase letter, comma,
# digit (common in area/population data), opening paren, or Vietnamese
# diacritical character — strong signal the sentence continues on the next line.
_CONTINUATION_END_RE = re.compile(
    r"""[a-zàáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệ"""
    r"""ìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữự"""
    r"""ỳýỷỹỵ0-9,;:\-–²³]\s*$""",
    re.UNICODE,
)

# A line that starts with a lowercase/digit continuation character (not a block start)
_CONTINUATION_START_RE = re.compile(
    r'^[a-zàáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệ'
    r'ìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữự'
    r'ỳýỷỹỵ]',
    re.UNICODE,
)


def rejoin_paragraphs(text: str) -> str:
    """Merge hard-wrapped lines back into flowing paragraphs.

    Rules:
    * If the current line ends mid-sentence (lowercase/comma) AND the next line
      does NOT start a new structural block → merge with a single space.
    * Blank lines are preserved as paragraph breaks.
    * Lines starting with structural markers (Điều, Chương, list items, etc.)
      always start a new paragraph.
    """
    if not text:
        return ""

    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Preserve blank lines as paragraph separators
        if not line.strip():
            result.append("")
            i += 1
            continue

        # Start accumulating a paragraph
        paragraph_parts = [line.rstrip()]
        i += 1

        while i < len(lines):
            next_line = lines[i]

            # Blank line → end of this paragraph
            if not next_line.strip():
                break

            # Next line starts a new structural block → end of this paragraph
            if _is_block_start(next_line):
                break

            # Merge if EITHER:
            # (a) Current line ends continuation-friendly (lowercase, digit, comma)
            # (b) Next line starts with lowercase (strong continuation signal)
            current_tail = paragraph_parts[-1]
            ends_continuation = _CONTINUATION_END_RE.search(current_tail)
            starts_continuation = _CONTINUATION_START_RE.match(next_line.strip())

            if ends_continuation or starts_continuation:
                paragraph_parts.append(next_line.strip())
                i += 1
            else:
                # Current line ends with punctuation (period, colon, etc.)
                # AND next line doesn't start lowercase — don't merge
                break

        result.append(" ".join(paragraph_parts))

    return "\n".join(result)


# ---------------------------------------------------------------------------
# 2. Legal Structure Formatting
# ---------------------------------------------------------------------------

def format_legal_structure(text: str) -> str:
    """Convert Vietnamese legal structure markers into Markdown headings.

    Transforms:
        Điều X. Title  →  ### Điều X. Title
        Chương X        →  ## Chương X
        Mục X           →  ## Mục X
        Phần X          →  ## Phần X
        I. SECTION TITLE → **I. SECTION TITLE**
    """
    if not text:
        return ""

    lines = text.split("\n")
    result: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip already-formatted headings
        if stripped.startswith("#"):
            result.append(line)
            continue

        # Chương / CHƯƠNG
        if re.match(r'^(?:Chương|CHƯƠNG)\s+[IVX\d]+', stripped):
            result.append(f"\n## {stripped}")
            continue

        # Mục / MỤC
        if re.match(r'^(?:Mục|MỤC)\s+[IVX\d]+', stripped):
            result.append(f"\n## {stripped}")
            continue

        # Phần / PHẦN
        if re.match(r'^(?:Phần|PHẦN)\s+[IVX\d]+', stripped):
            result.append(f"\n## {stripped}")
            continue

        # Điều X. / Điều X:
        if re.match(r'^[ĐÐ]iều\s+\d+[\.\s:]', stripped):
            result.append(f"\n### {stripped}")
            continue

        # Roman numeral section headers (I. UPPERCASE TITLE)
        if re.match(r'^[IVX]+\.\s+[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ]', stripped):
            # Only bold if the rest is mostly uppercase (section title, not content)
            alpha_chars = [c for c in stripped if c.isalpha()]
            if alpha_chars:
                upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
                if upper_ratio > 0.6:
                    result.append(f"\n**{stripped}**")
                    continue

        result.append(line)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# 3. Garbled Table Detection
# ---------------------------------------------------------------------------

def detect_garbled_table(text: str) -> bool:
    """Heuristic: detect if text is likely a garbled OCR table.

    Indicators:
    * Many very short lines (< 25 chars)
    * Presence of isolated markers like "X", "Χ" (Greek Chi), "x"
    * Keywords like "Vốn NĐT", "NSNN", "NSTP", "NSTW"
    * High ratio of lines with only 1–3 words
    * Unicode garbage characters (ŧ, Ė, ΧŲ, etc.)
    * HTML/LaTeX tags (<math>, <br>, <sup>)
    * Highly repetitive text blocks
    """
    if not text or len(text) < 50:
        return False

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 3:
        return False

    short_lines = sum(1 for l in lines if len(l) < 25)
    short_ratio = short_lines / len(lines) if lines else 0

    # Check for table-related keywords
    table_keywords = ["Vốn NĐT", "NSNN", "NSTP", "NSTW", "NSTƯ"]
    keyword_count = sum(1 for kw in table_keywords if kw in text)

    # Check for isolated single-char marks (common in garbled table cells)
    isolated_marks = sum(1 for l in lines if l in ("X", "Χ", "Х", "x", ".", "-", "_", "*"))
    mark_ratio = isolated_marks / len(lines) if lines else 0

    # Decision: high short-line ratio + (keywords or marks)
    if short_ratio > 0.5 and (keyword_count >= 2 or mark_ratio > 0.1):
        return True

    # Ultra-short lines with isolated numbers/marks
    if short_ratio > 0.7 and mark_ratio > 0.05:
        return True

    # ── Additional heuristics for legal document OCR failures ──

    # Check for Unicode garbage characters (non-Vietnamese, non-standard)
    _GARBAGE_CHARS = set('ŧĖΧŲġşŷįďŕŝΈΊϐ')
    garbage_count = sum(1 for c in text if c in _GARBAGE_CHARS)
    if garbage_count > 5:
        return True

    # Check for HTML/LaTeX tags that indicate OCR artifacts
    html_tag_count = (
        text.count('<math>') + text.count('</math>')
        + text.count('<br>') + text.count('<br/>')
        + text.count('<sup>') + text.count('</sup>')
    )
    if html_tag_count >= 3:
        return True

    # Check for highly repetitive text blocks (common when OCR reads
    # the same table header cells across multiple rows/columns)
    if len(text) > 500:
        sample = text[:200].strip()
        if sample and text.count(sample) >= 3:
            return True

    return False


# ---------------------------------------------------------------------------
# 3b. Raw Pipe Table Normalizer (P1 fix)
# ---------------------------------------------------------------------------

def fix_raw_pipe_tables(text: str) -> str:
    """Fix pipe-delimited tables that lack Markdown separator rows.

    Many tables extracted by fitz arrive as lines like:
        | Header1 | Header2 | Header3 |
        | data1   | data2   | data3   |
    without the required `|---|---|---|` separator after the header row.

    This function detects contiguous blocks of pipe-delimited lines and
    inserts separator rows after the first row in each block.

    SAFETY:
    - Only modifies blocks with ≥2 consecutive pipe rows
    - Never touches blocks that already have separators
    - Preserves single pipe occurrences (e.g. "A | B" in prose)
    """
    if not text or '|' not in text:
        return text

    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this line is a pipe-delimited row (starts and ends with |)
        if stripped.startswith('|') and stripped.endswith('|') and stripped.count('|') >= 3:
            # Collect contiguous pipe rows
            pipe_block = [line]
            j = i + 1
            has_separator = bool(re.match(r'^\s*\|[\s\-:|]+\|\s*$', stripped))

            while j < len(lines):
                next_stripped = lines[j].strip()
                if next_stripped.startswith('|') and next_stripped.endswith('|') and next_stripped.count('|') >= 3:
                    pipe_block.append(lines[j])
                    if re.match(r'^\s*\|[\s\-:|]+\|\s*$', next_stripped):
                        has_separator = True
                    j += 1
                elif not next_stripped:
                    # Allow 1 blank line within a table block
                    if j + 1 < len(lines) and lines[j + 1].strip().startswith('|'):
                        pipe_block.append(lines[j])
                        j += 1
                    else:
                        break
                else:
                    break

            if len(pipe_block) >= 2 and not has_separator:
                # Insert separator after first pipe row
                header = pipe_block[0]
                col_count = header.count('|') - 1  # number of columns
                separator = '| ' + ' | '.join(['---'] * col_count) + ' |'
                result.append(pipe_block[0])
                result.append(separator)
                result.extend(pipe_block[1:])
                logger.info(f"  [P1] Fixed raw pipe table: inserted separator ({col_count} cols, {len(pipe_block)} rows)")
            else:
                result.extend(pipe_block)

            i = j
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


# ---------------------------------------------------------------------------
# 4. Composite: Full normalization pipeline
# ---------------------------------------------------------------------------

def normalize_chunk_text(text: str, strip_doc_id_prefix: str = "") -> str:
    """Apply the full normalization chain to a chunk's text.

    Args:
        text: Raw chunk text.
        strip_doc_id_prefix: If provided, strip this prefix pattern from the text
                             (e.g. "[UBND_DaNang-QNam/1287/QĐ-TTg] ").

    Returns:
        Cleaned, formatted markdown text.
    """
    if not text:
        return ""

    # Step 0: Strip doc_id prefix
    if strip_doc_id_prefix:
        prefix = f"[{strip_doc_id_prefix}] "
        if text.startswith(prefix):
            text = text[len(prefix):]

    # Step 0a: Normalize OCR spacing (must be FIRST, before any regex)
    text = normalize_ocr_spacing(text)

    # Step 0b: Fix OCR typos early (before any structure detection)
    text = fix_common_ocr_typos(text)

    # Step 0b2: Fix stuck Vietnamese words (hồsơ → hồ sơ)
    text = fix_stuck_vietnamese_words(text)

    # Step 0b3: Fix generic stuck words via regex (diacritic+uppercase boundary)
    text = fix_generic_stuck_words(text)

    # Step 0b4: Strip date/page metadata noise (e.g. '01 06 01 2025 2025')
    text = strip_date_page_noise(text)

    # Step 0b5: Strip template dotted-line patterns from form annexes
    text = strip_template_dots(text)

    # Step 0c: Strip government document boilerplate headers
    text = strip_document_boilerplate(text)

    # Step 0d: Strip Nơi nhận distribution blocks
    text = strip_noi_nhan_block(text)

    # Step 0e: Strip signer block at end of text (KT./TM. + name)
    text = strip_signer_block(text)

    # Step 0f: Strip digital signature metadata (Ký bởi:...Email:...)
    text = strip_digital_signature(text)

    # Step 1: Detect garbled table — return with warning if garbled
    if detect_garbled_table(text):
        return f"> ⚠️ *Bảng biểu gốc — dữ liệu OCR cần kiểm tra thủ công*\n\n{text}"

    # Step 2: Rejoin hard-wrapped paragraphs
    text = rejoin_paragraphs(text)

    # Step 2b: [P1-FIX] Fix raw pipe tables missing separator rows
    text = fix_raw_pipe_tables(text)

    # Step 3: Rejoin broken ALL-CAPS headings
    text = rejoin_broken_headings(text)

    # Step 4: Format legal structure markers as headings
    text = format_legal_structure(text)

    return text
